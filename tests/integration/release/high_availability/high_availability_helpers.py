#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

from collections.abc import Callable

import jubilant_backports
from jubilant_backports import Juju
from jubilant_backports.statustypes import Status, UnitStatus
from tenacity import (
    Retrying,
    retry,
    stop_after_attempt,
    stop_after_delay,
    wait_fixed,
)

from constants import SERVER_CONFIG_USERNAME

from ...helpers import execute_queries_on_unit

MINUTE_SECS = 60
TEST_DATABASE_NAME = "testing"

JujuModelStatusFn = Callable[[Status], bool]
JujuAppsStatusFn = Callable[[Status, str], bool]


async def check_mysql_units_writes_increment(
    juju: Juju, app_name: str, app_units: list[str] | None = None
) -> None:
    """Ensure that continuous writes is incrementing on all units.

    Also, ensure that all continuous writes up to the max written value is available
    on all units (ensure that no committed data is lost).
    """
    if not app_units:
        app_units = get_app_units(juju, app_name)

    app_primary = get_mysql_primary_unit(juju, app_name)
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


def get_app_units(juju: Juju, app_name: str) -> dict[str, UnitStatus]:
    """Get the units for the given application."""
    model_status = juju.status()
    app_status = model_status.apps[app_name]
    return app_status.units


def get_unit_ip(juju: Juju, app_name: str, unit_name: str) -> str:
    """Get the application unit IP."""
    model_status = juju.status()
    app_status = model_status.apps[app_name]
    for name, status in app_status.units.items():
        if name == unit_name:
            return status.public_address

    raise Exception("No application unit found")


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


async def get_mysql_max_written_value(juju: Juju, app_name: str, unit_name: str) -> int:
    """Retrieve the max written value in the MySQL database.

    Args:
        juju: The Juju model.
        app_name: The application name.
        unit_name: The unit name.
    """
    credentials_task = juju.run(
        unit=unit_name,
        action="get-password",
        params={"username": SERVER_CONFIG_USERNAME},
    )
    credentials_task.raise_on_failure()

    output = await execute_queries_on_unit(
        get_unit_ip(juju, app_name, unit_name),
        credentials_task.results["username"],
        credentials_task.results["password"],
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
    credentials_task = juju.run(
        unit=unit_name,
        action="get-password",
        params={"username": SERVER_CONFIG_USERNAME},
    )
    credentials_task.raise_on_failure()

    output = await execute_queries_on_unit(
        get_unit_ip(juju, app_name, unit_name),
        credentials_task.results["username"],
        credentials_task.results["password"],
        [f"SELECT @@{variable_name};"],
    )
    return output[0]


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
