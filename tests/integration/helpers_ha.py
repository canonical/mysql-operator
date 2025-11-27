#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import subprocess
from collections.abc import Callable, Generator
from contextlib import contextmanager
from pathlib import Path

import jubilant_backports
import yaml
from jubilant_backports import Juju
from jubilant_backports.statustypes import Status
from tenacity import (
    Retrying,
    retry,
    stop_after_attempt,
    stop_after_delay,
    wait_fixed,
)

from constants import ROOT_USERNAME, SERVER_CONFIG_USERNAME

from .helpers import execute_queries_on_unit

CHARM_METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())

MINUTE_SECS = 60
TEST_DATABASE_NAME = "testing"

JujuModelStatusFn = Callable[[Status], bool]
JujuAppsStatusFn = Callable[[Status, str], bool]


def check_mysql_instances_online(
    juju: Juju,
    app_name: str,
    app_units: list[str] | None = None,
) -> bool:
    """Checks whether all MySQL cluster instances are online.

    Args:
        juju: The Juju instance
        app_name: The name of the application
        app_units: The list of application units to check
    """
    if not app_units:
        app_units = get_app_units(juju, app_name)

    mysql_cluster_status = get_mysql_cluster_status(juju, app_units[0])
    mysql_cluster_topology = mysql_cluster_status["defaultreplicaset"]["topology"]

    for unit_name in app_units:
        unit_label = get_mysql_instance_label(unit_name)
        if mysql_cluster_topology[unit_label]["status"] != "online":
            return False

    return True


async def check_mysql_units_writes_increment(
    juju: Juju, app_name: str, app_units: list[str] | None = None
) -> None:
    """Ensure that continuous writes is incrementing on all units.

    Also, ensure that all continuous writes up to the max written value is available
    on all units (ensure that no committed data is lost).
    """
    if not app_units:
        app_units = get_app_units(juju, app_name)

    app_primary = get_mysql_primary_unit(juju, app_name, app_units[0])
    app_max_value = await get_mysql_max_written_value(juju, app_name, app_primary)

    for unit_name in app_units:
        for attempt in Retrying(
            reraise=True,
            stop=stop_after_delay(5 * MINUTE_SECS),
            wait=wait_fixed(10),
        ):
            with attempt:
                unit_max_value = await get_mysql_max_written_value(juju, app_name, unit_name)
                assert unit_max_value > app_max_value, "Writes not incrementing"
                app_max_value = unit_max_value


def get_app_leader(juju: Juju, app_name: str) -> str:
    """Get the leader unit for the given application."""
    model_status = juju.status()
    app_status = model_status.apps[app_name]
    for name, status in app_status.units.items():
        if status.leader:
            return name

    raise Exception("No leader unit found")


def remove_leader_unit(juju: Juju, app_name: str) -> None:
    """Removes the leader unit of a specified application.

    Args:
        juju: The Juju instance
        app_name: The name of the application
    """
    leader_unit = get_app_leader(juju, app_name)
    juju.remove_unit(leader_unit)


def get_app_name(juju: Juju, charm_name: str) -> str | None:
    """Get the application name for the given charm."""
    model_status = juju.status()
    app_statuses = model_status.apps
    for name, status in app_statuses.items():
        if status.charm_name == charm_name:
            return name

    raise Exception("No application name found")


def get_app_units(juju: Juju, app_name: str) -> list[str]:
    """Get the units for the given application."""
    model_status = juju.status()
    app_status = model_status.apps[app_name]
    return list(app_status.units)


def scale_app_units(juju: Juju, app_name: str, num_units: int) -> None:
    """Scale a given application to a number of units."""
    app_units = get_app_units(juju, app_name)
    app_units_diff = num_units - len(app_units)

    if app_units_diff > 0:
        juju.add_unit(app_name, num_units=app_units_diff)
    if app_units_diff < 0:
        juju.remove_unit(*app_units[app_units_diff:])
    if app_units_diff == 0:
        return

    juju.wait(
        ready=lambda status: len(status.apps[app_name].units) == num_units,
        timeout=20 * MINUTE_SECS,
    )

    juju.wait(
        ready=wait_for_apps_status(jubilant_backports.all_active, app_name),
        timeout=20 * MINUTE_SECS,
    )


def get_unit_by_number(juju: Juju, app_name: str, unit_number: int) -> str:
    """Get unit by number."""
    model_status = juju.status()
    app_status = model_status.apps[app_name]
    for name in app_status.units:
        if name == f"{app_name}/{unit_number}":
            return name

    raise Exception("No application unit found")


def get_unit_ip(juju: Juju, app_name: str, unit_name: str) -> str:
    """Get the application unit IP."""
    model_status = juju.status()
    app_status = model_status.apps[app_name]
    for name, status in app_status.units.items():
        if name == unit_name:
            return status.public_address

    raise Exception("No application unit found")


def get_unit_info(juju: Juju, unit_name: str) -> dict:
    """Return a dictionary with the show-unit data."""
    output = subprocess.check_output(
        ["juju", "show-unit", f"--model={juju.model}", "--format=json", unit_name],
        text=True,
    )

    return json.loads(output)


def get_unit_process_id(juju: Juju, unit_name: str, process_name: str) -> int | None:
    """Return the pid of a process running in a given unit."""
    try:
        task = juju.exec(f"pgrep -x {process_name}", unit=unit_name)
        task.raise_on_failure()

        return int(task.stdout.strip())
    except Exception:
        return None


def get_unit_status_log(juju: Juju, unit_name: str, log_lines: int = 0) -> list[dict]:
    """Get the status log for a unit.

    Args:
        juju: The juju instance to use.
        unit_name: The name of the unit to retrieve the status log for
        log_lines: The number of status logs to retrieve (optional)
    """
    # fmt: off
    output = subprocess.check_output(
        ["juju", "show-status-log", f"--model={juju.model}", "--format=json", unit_name, "-n", f"{log_lines}"],
        text=True,
    )

    return json.loads(output)


def get_relation_data(juju: Juju, app_name: str, rel_name: str) -> list[dict]:
    """Returns a list that contains the relation-data.

    Args:
        juju: The juju instance to use.
        app_name: The name of the application
        rel_name: name of the relation to get connection data from

    Returns:
        A list that contains the relation-data
    """
    app_leader = get_app_leader(juju, app_name)
    app_leader_info = get_unit_info(juju, app_leader)
    if not app_leader_info:
        raise ValueError(f"No unit info could be grabbed for unit {app_leader}")

    relation_data = [
        value
        for value in app_leader_info[app_leader]["relation-info"]
        if value["endpoint"] == rel_name
    ]
    if not relation_data:
        raise ValueError(f"No relation data could be grabbed for relation {rel_name}")

    return relation_data


@retry(stop=stop_after_attempt(30), wait=wait_fixed(5), reraise=True)
def get_mysql_cluster_status(juju: Juju, unit: str, cluster_set: bool = False) -> dict:
    """Get the cluster status by running the get-cluster-status action.

    Args:
        juju: The juju instance to use.
        unit: The unit on which to execute the action on
        cluster_set: Whether to get the cluster-set instead (optional)

    Returns:
        A dictionary representing the cluster status
    """
    task = juju.run(
        unit=unit,
        action="get-cluster-status",
        params={"cluster-set": cluster_set},
        wait=5 * MINUTE_SECS,
    )
    task.raise_on_failure()

    return task.results["status"]


def get_mysql_instance_label(unit_name: str) -> str:
    """Builds a MySQL instance label out of a Juju unit name."""
    return "-".join(unit_name.rsplit("/", 1))


def get_mysql_unit_name(instance_label: str) -> str:
    """Builds a Juju unit name out of a MySQL instance label."""
    return "/".join(instance_label.rsplit("-", 1))


def get_mysql_primary_unit(juju: Juju, app_name: str, unit_name: str | None = None) -> str:
    """Get the current primary node of the cluster."""
    if unit_name is None:
        unit_name = get_app_leader(juju, app_name)

    mysql_cluster_status = get_mysql_cluster_status(juju, unit_name)
    mysql_cluster_topology = mysql_cluster_status["defaultreplicaset"]["topology"]

    for label, value in mysql_cluster_topology.items():
        if value["memberrole"] == "primary":
            return get_mysql_unit_name(label)

    raise Exception("No MySQL primary node found")


def get_mysql_server_credentials(
    juju: Juju, unit_name: str, username: str = SERVER_CONFIG_USERNAME
) -> dict[str, str]:
    """Helper that runs an action to retrieve credentials for given username on mysql-test-app.

    Args:
        juju: The Juju model
        unit_name: The juju unit on which to run the get-password action for server-config credentials
        username: The username to use

    Returns:
        A dictionary with the server config username and password
    """
    credentials_task = juju.run(
        unit=unit_name,
        action="get-password",
        params={"username": username},
    )
    credentials_task.raise_on_failure()

    return credentials_task.results


def get_legacy_mysql_credentials(
    juju: Juju, unit_name: str, username: str = ROOT_USERNAME
) -> dict[str, str]:
    """Helper that runs an action to retrieve legacy credentials for given username on mysql-test-app.

    Args:
        juju: The Juju model
        unit_name: The juju unit on which to run the get-password action for server-config credentials
        username: The username to use

    Returns:
        A dictionary with the server config username and password
    """
    credentials_task = juju.run(
        unit=unit_name,
        action="get-legacy-mysql-credentials",
        params={"username": username},
    )
    credentials_task.raise_on_failure()

    return credentials_task.results


async def get_mysql_max_written_value(juju: Juju, app_name: str, unit_name: str) -> int:
    """Retrieve the max written value in the MySQL database.

    Args:
        juju: The Juju model.
        app_name: The application name.
        unit_name: The unit name.
    """
    credentials = get_mysql_server_credentials(juju, unit_name)

    output = await execute_queries_on_unit(
        get_unit_ip(juju, app_name, unit_name),
        credentials["username"],
        credentials["password"],
        ["SELECT MAX(number) FROM `continuous_writes`.`data`;"],
    )
    return output[0]


async def get_mysql_variable_value(
    juju: Juju, app_name: str, unit_name: str, variable_name: str
) -> str:
    """Retrieve a database variable value as a string.

    Args:
        juju: The Juju model.
        app_name: The application name.
        unit_name: The unit name.
        variable_name: The variable name.
    """
    credentials = get_mysql_server_credentials(juju, unit_name)

    output = await execute_queries_on_unit(
        get_unit_ip(juju, app_name, unit_name),
        credentials["username"],
        credentials["password"],
        [f"SELECT @@{variable_name};"],
    )
    return output[0]


def start_mysql_process_gracefully(juju: Juju, unit_name: str) -> None:
    """Start a MySQL process within a machine."""
    juju.ssh(
        command="sudo snap start charmed-mysql.mysqld",
        target=unit_name,
    )

    # Hold execution until process is started
    for attempt in Retrying(stop=stop_after_attempt(10), wait=wait_fixed(5)):
        with attempt:
            if get_unit_process_id(juju, unit_name, "mysqld") is None:
                raise Exception("Failed to start the mysqld process")


def stop_mysql_process_gracefully(juju: Juju, unit_name: str) -> None:
    """Gracefully stop MySQL process."""
    juju.ssh(
        command="sudo pkill mysqld --signal SIGTERM",
        target=unit_name,
    )

    # Hold execution until process is stopped
    for attempt in Retrying(stop=stop_after_attempt(10), wait=wait_fixed(5)):
        with attempt:
            if get_unit_process_id(juju, unit_name, "mysqld") is not None:
                raise Exception("Failed to stop the mysqld process")


@contextmanager
def update_interval(juju: Juju, interval: str) -> Generator:
    """Temporarily speed up update-status firing rate for the current model."""
    update_interval_key = "update-status-hook-interval"
    update_interval_val = juju.model_config()[update_interval_key]

    juju.model_config({update_interval_key: interval})
    try:
        yield
    finally:
        juju.model_config({update_interval_key: update_interval_val})


async def insert_mysql_test_data(juju: Juju, app_name: str, table_name: str, value: str) -> None:
    """Insert data into the MySQL database.

    Args:
        juju: The Juju model.
        app_name: The application name.
        table_name: The database table name.
        value: The value to insert.
    """
    mysql_leader = get_app_leader(juju, app_name)
    mysql_primary = get_mysql_primary_unit(juju, app_name)

    credentials = get_mysql_server_credentials(juju, mysql_leader)

    insert_queries = [
        f"CREATE DATABASE IF NOT EXISTS `{TEST_DATABASE_NAME}`",
        f"CREATE TABLE IF NOT EXISTS `{TEST_DATABASE_NAME}`.`{table_name}` (id VARCHAR(255), PRIMARY KEY (id))",
        f"INSERT INTO `{TEST_DATABASE_NAME}`.`{table_name}` (id) VALUES ('{value}')",
    ]

    await execute_queries_on_unit(
        get_unit_ip(juju, app_name, mysql_primary),
        credentials["username"],
        credentials["password"],
        insert_queries,
        commit=True,
    )


async def remove_mysql_test_data(juju: Juju, app_name: str, table_name: str) -> None:
    """Remove data into the MySQL database.

    Args:
        juju: The Juju model.
        app_name: The application name.
        table_name: The database table name.
    """
    mysql_leader = get_app_leader(juju, app_name)
    mysql_primary = get_mysql_primary_unit(juju, app_name)

    credentials = get_mysql_server_credentials(juju, mysql_leader)

    remove_queries = [
        f"DROP TABLE IF EXISTS `{TEST_DATABASE_NAME}`.`{table_name}`",
        f"DROP DATABASE IF EXISTS `{TEST_DATABASE_NAME}`",
    ]

    await execute_queries_on_unit(
        get_unit_ip(juju, app_name, mysql_primary),
        credentials["username"],
        credentials["password"],
        remove_queries,
        commit=True,
    )


async def verify_mysql_test_data(juju: Juju, app_name: str, table_name: str, value: str) -> None:
    """Verifies data into the MySQL database.

    Args:
        juju: The Juju model.
        app_name: The application name.
        table_name: The database table name.
        value: The value to check against.
    """
    mysql_app_leader = get_app_leader(juju, app_name)
    mysql_app_units = get_app_units(juju, app_name)

    credentials = get_mysql_server_credentials(juju, mysql_app_leader)

    select_queries = [
        f"SELECT id FROM `{TEST_DATABASE_NAME}`.`{table_name}` WHERE id = '{value}'",
    ]

    for unit_name in mysql_app_units:
        for attempt in Retrying(
            reraise=True,
            stop=stop_after_delay(5 * MINUTE_SECS),
            wait=wait_fixed(10),
        ):
            with attempt:
                output = await execute_queries_on_unit(
                    get_unit_ip(juju, app_name, unit_name),
                    credentials["username"],
                    credentials["password"],
                    select_queries,
                )
                assert output[0] == value


def wait_for_apps_status(jubilant_status_func: JujuAppsStatusFn, *apps: str) -> JujuModelStatusFn:
    """Waits for Juju agents to be idle, and for applications to reach a certain status.

    Args:
        jubilant_status_func: The Juju apps status function to wait for.
        apps: The applications to wait for.

    Returns:
        Juju model status function.
    """
    return lambda status: all((
        jubilant_backports.all_agents_idle(status, *apps),
        jubilant_status_func(status, *apps),
    ))


def wait_for_app_status(app_name: str, app_status: str) -> JujuModelStatusFn:
    """Returns whether a Juju app has a specific status."""
    return lambda status: (status.apps[app_name].app_status.current == app_status)


def wait_for_unit_status(app_name: str, unit_name: str, unit_status: str) -> JujuModelStatusFn:
    """Returns whether a Juju unit to have a specific status."""
    return lambda status: (
        status.apps[app_name].units[unit_name].workload_status.current == unit_status
    )


def wait_for_unit_message(app_name: str, unit_name: str, unit_message: str) -> JujuModelStatusFn:
    """Returns whether a Juju unit to have a specific message."""
    return lambda status: (
        status.apps[app_name].units[unit_name].workload_status.message == unit_message
    )


async def check_keystone_users_existence(
    juju: Juju,
    app_name: str,
    server_config_credentials: dict[str, str],
    users_that_should_exist: list[str],
    users_that_should_not_exist: list[str],
) -> None:
    """Checks that keystone users exist in the database.

    Args:
        juju: The Juju instance
        app_name: The name of the application
        server_config_credentials: The credentials for the server config user
        users_that_should_exist: List of users that should exist in the database
        users_that_should_not_exist: List of users that should not exist in the database
    """
    random_unit = get_app_units(juju, app_name)[0]
    server_config_credentials = get_mysql_server_credentials(juju, random_unit)

    select_users_sql = [
        "SELECT CONCAT(user, '@', host) FROM mysql.user",
    ]

    unit_name = get_app_units(juju, app_name)[0]
    unit_address = get_unit_ip(juju, app_name, unit_name)

    # Retrieve all users in the database
    output = await execute_queries_on_unit(
        unit_address,
        server_config_credentials["username"],
        server_config_credentials["password"],
        select_users_sql,
    )

    # Assert users that should exist
    for user in users_that_should_exist:
        assert user in output, "User(s) that should exist are not in the database"

    # Assert users that should not exist
    for user in users_that_should_not_exist:
        assert user not in output, "User(s) that should not exist are in the database"


async def check_successful_keystone_migration(
    juju: Juju, app_name: str, server_config_credentials: dict
) -> None:
    """Checks that the keystone application is successfully migrated in mysql.

    Args:
        juju: The Juju instance
        server_config_credentials: The credentials for the server config user
    """
    show_tables_sql = ["SHOW DATABASES"]
    get_count_keystone_tables_sql = [
        "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'keystone'",
    ]

    for unit_name in get_app_units(juju, app_name):
        unit_address = get_unit_ip(juju, app_name, unit_name)

        # Ensure 'keystone' database exists in mysql
        output = await execute_queries_on_unit(
            unit_address,
            server_config_credentials["username"],
            server_config_credentials["password"],
            show_tables_sql,
        )
        assert "keystone" in output, "keystone database not found in mysql"

        # Ensure that keystone tables exist in the 'keystone' database
        output = await execute_queries_on_unit(
            unit_address,
            server_config_credentials["username"],
            server_config_credentials["password"],
            get_count_keystone_tables_sql,
        )
        assert output[0] > 0, "No keystone tables found in the 'keystone' database"
