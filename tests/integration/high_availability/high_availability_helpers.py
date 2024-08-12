# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from pathlib import Path
from typing import List, Optional

import yaml
from juju.unit import Unit
from pytest_operator.plugin import OpsTest
from tenacity import RetryError, Retrying, stop_after_delay, wait_fixed

from ..helpers import (
    execute_queries_on_unit,
    generate_random_string,
    get_cluster_status,
    get_primary_unit_wrapper,
    get_server_config_credentials,
    get_unit_ip,
    is_relation_joined,
    scale_application,
)

# Copied these values from high_availability.application_charm.src.charm
DATABASE_NAME = "continuous_writes_database"
TABLE_NAME = "data"

CLUSTER_NAME = "test_cluster"
METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
MYSQL_DEFAULT_APP_NAME = METADATA["name"]
APPLICATION_DEFAULT_APP_NAME = "mysql-test-app"
TIMEOUT = 20 * 60

mysql_charm, application_charm = None, None

logger = logging.getLogger(__name__)


async def get_max_written_value_in_database(
    ops_test: OpsTest, unit: Unit, credentials: dict
) -> int:
    """Retrieve the max written value in the MySQL database.

    Args:
        ops_test: The ops test framework
        unit: The MySQL unit on which to execute queries on
        credentials: Database credentials to use
    """
    unit_address = await get_unit_ip(ops_test, unit.name)

    select_max_written_value_sql = [f"SELECT MAX(number) FROM `{DATABASE_NAME}`.`{TABLE_NAME}`;"]

    output = await execute_queries_on_unit(
        unit_address,
        credentials["username"],
        credentials["password"],
        select_max_written_value_sql,
    )

    return output[0]


def get_application_name(ops_test: OpsTest, application_name_substring: str) -> str:
    """Returns the name of the application with the provided application name.

    This enables us to retrieve the name of the deployed application in an existing model.

    Note: if multiple applications with the application name exist,
    the first one found will be returned.
    """
    for application in ops_test.model.applications:
        if application_name_substring == application:
            return application

    return ""


async def ensure_n_online_mysql_members(
    ops_test: OpsTest, number_online_members: int, mysql_units: Optional[List[Unit]] = None
) -> bool:
    """Waits until N mysql cluster members are online.

    Args:
        ops_test: The ops test framework
        number_online_members: Number of online members to wait for
        mysql_units: Expected online mysql units
    """
    logger.info(f"Ensure {number_online_members} units are online")
    mysql_application = get_application_name(ops_test, "mysql")

    if not mysql_units:
        mysql_units = ops_test.model.applications[mysql_application].units
    mysql_unit = mysql_units[0]

    try:
        for attempt in Retrying(stop=stop_after_delay(10 * 60), wait=wait_fixed(10)):
            with attempt:
                cluster_status = await get_cluster_status(mysql_unit)
                online_members = [
                    label
                    for label, member in cluster_status["defaultreplicaset"]["topology"].items()
                    if member["status"] == "online"
                ]
                assert len(online_members) == number_online_members
                return True
    except RetryError:
        pass
    return False


async def deploy_and_scale_mysql(
    ops_test: OpsTest,
    check_for_existing_application: bool = True,
    mysql_application_name: str = MYSQL_DEFAULT_APP_NAME,
    num_units: int = 3,
) -> str:
    """Deploys and scales the mysql application charm.

    Args:
        ops_test: The ops test framework
        check_for_existing_application: Whether to check for existing mysql applications
            in the model
        mysql_application_name: The name of the mysql application if it is to be deployed
        num_units: The number of units to deploy
    """
    application_name = get_application_name(ops_test, "mysql")

    if check_for_existing_application and application_name:
        if len(ops_test.model.applications[application_name].units) != num_units:
            async with ops_test.fast_forward():
                await scale_application(ops_test, application_name, num_units)

        return application_name

    charm = await ops_test.build_charm(".")

    config = {"cluster-name": CLUSTER_NAME, "profile": "testing"}

    async with ops_test.fast_forward("60s"):
        await ops_test.model.deploy(
            charm,
            application_name=mysql_application_name,
            config=config,
            num_units=num_units,
            series="jammy",
        )

        await ops_test.model.wait_for_idle(
            apps=[mysql_application_name],
            status="active",
            timeout=TIMEOUT,
        )

        assert len(ops_test.model.applications[mysql_application_name].units) == num_units

    return mysql_application_name


async def deploy_and_scale_application(ops_test: OpsTest) -> str:
    """Deploys and scales the test application charm.

    Args:
        ops_test: The ops test framework
    """
    application_name = get_application_name(ops_test, APPLICATION_DEFAULT_APP_NAME)

    if application_name:
        if len(ops_test.model.applications[application_name].units) != 1:
            async with ops_test.fast_forward():
                await scale_application(ops_test, application_name, 1)

        return application_name

    async with ops_test.fast_forward("60s"):
        await ops_test.model.deploy(
            APPLICATION_DEFAULT_APP_NAME,
            application_name=APPLICATION_DEFAULT_APP_NAME,
            num_units=1,
            channel="latest/edge",
        )

        await ops_test.model.wait_for_idle(
            apps=[APPLICATION_DEFAULT_APP_NAME],
            status="waiting",
            raise_on_blocked=True,
            timeout=TIMEOUT,
        )

        assert len(ops_test.model.applications[APPLICATION_DEFAULT_APP_NAME].units) == 1

    return APPLICATION_DEFAULT_APP_NAME


async def relate_mysql_and_application(
    ops_test: OpsTest, mysql_application_name: str, application_name: str
) -> None:
    """Relates the mysql and application charms.

    Args:
        ops_test: The ops test framework
        mysql_application_name: The mysql charm application name
        application_name: The continuous writes test charm application name
    """
    if is_relation_joined(ops_test, "database", "database"):
        return

    await ops_test.model.relate(
        f"{application_name}:database", f"{mysql_application_name}:database"
    )
    await ops_test.model.block_until(lambda: is_relation_joined(ops_test, "database", "database"))

    await ops_test.model.wait_for_idle(
        apps=[mysql_application_name, application_name],
        status="active",
        raise_on_blocked=True,
        timeout=TIMEOUT,
    )


async def get_process_stat(ops_test: OpsTest, unit_name: str, process: str) -> str:
    """Retrieve the STAT column of a process on a unit.

    Args:
        ops_test: The ops test framework
        unit_name: The name of the unit for the process
        process: The name of the process to get the STAT for
    """
    get_stat_commands = [
        "ssh",
        unit_name,
        f"ps -eo comm,stat | grep {process} | awk '{{print $2}}'",
    ]
    return_code, stat, _ = await ops_test.juju(*get_stat_commands)

    assert return_code == 0, f"Failed to get STAT, unit_name={unit_name}, process={process}"

    return stat


async def insert_data_into_mysql_and_validate_replication(
    ops_test: OpsTest,
    database_name: str,
    table_name: str,
    mysql_application_substring: Optional[str] = "mysql",
    mysql_units: Optional[List[Unit]] = None,
) -> str:
    """Inserts data into the mysql cluster and validates its replication.

    database_name: The name of the database to create
    table_name: The name of the table to create and insert data into
    """
    mysql_application_name = get_application_name(ops_test, mysql_application_substring)

    if not mysql_units:
        mysql_units = ops_test.model.applications[mysql_application_name].units

    primary = await get_primary_unit_wrapper(ops_test, mysql_application_name)

    # insert some data into the new primary and ensure that the writes get replicated
    server_config_credentials = await get_server_config_credentials(primary)
    primary_address = await get_unit_ip(ops_test, primary.name)

    value = generate_random_string(255)
    insert_value_sql = [
        f"CREATE DATABASE IF NOT EXISTS `{database_name}`",
        f"CREATE TABLE IF NOT EXISTS `{database_name}`.`{table_name}` (id varchar(255), primary key (id))",
        f"INSERT INTO `{database_name}`.`{table_name}` (id) VALUES ('{value}')",
    ]

    await execute_queries_on_unit(
        primary_address,
        server_config_credentials["username"],
        server_config_credentials["password"],
        insert_value_sql,
        commit=True,
    )

    select_value_sql = [
        f"SELECT id FROM `{database_name}`.`{table_name}` WHERE id = '{value}'",
    ]

    try:
        for attempt in Retrying(stop=stop_after_delay(5 * 60), wait=wait_fixed(10)):
            with attempt:
                for unit in mysql_units:
                    unit_address = await get_unit_ip(ops_test, unit.name)

                    output = await execute_queries_on_unit(
                        unit_address,
                        server_config_credentials["username"],
                        server_config_credentials["password"],
                        select_value_sql,
                    )
                    assert output[0] == value
    except RetryError:
        assert False, "Cannot query inserted data from all units"

    return value


async def clean_up_database_and_table(
    ops_test: OpsTest, database_name: str, table_name: str
) -> None:
    """Cleans the database and table created by insert_data_into_mysql_and_validate_replication.

    Args:
        ops_test: The ops test framework
        database_name: The name of the database to drop
        table_name: The name of the table to drop
    """
    mysql_application_name = get_application_name(ops_test, "mysql")

    mysql_unit = ops_test.model.applications[mysql_application_name].units[0]

    server_config_credentials = await get_server_config_credentials(mysql_unit)

    primary = await get_primary_unit_wrapper(ops_test, mysql_application_name)
    primary_address = await get_unit_ip(ops_test, primary.name)

    clean_up_database_and_table_sql = [
        f"DROP TABLE IF EXISTS `{database_name}`.`{table_name}`",
        f"DROP DATABASE IF EXISTS `{database_name}`",
    ]

    await execute_queries_on_unit(
        primary_address,
        server_config_credentials["username"],
        server_config_credentials["password"],
        clean_up_database_and_table_sql,
        commit=True,
    )


async def ensure_all_units_continuous_writes_incrementing(
    ops_test: OpsTest, mysql_units: Optional[List[Unit]] = None
) -> None:
    """Ensure that continuous writes is incrementing on all units.

    Also, ensure that all continuous writes up to the max written value is available
    on all units (ensure that no committed data is lost).
    """
    logger.info("Ensure continuous writes are incrementing")

    mysql_application_name = get_application_name(ops_test, "mysql")

    if not mysql_units:
        mysql_units = ops_test.model.applications[mysql_application_name].units

    primary = await get_primary_unit_wrapper(ops_test, mysql_application_name)

    server_config_credentials = await get_server_config_credentials(mysql_units[0])

    last_max_written_value = await get_max_written_value_in_database(
        ops_test, primary, server_config_credentials
    )

    select_all_continuous_writes_sql = [f"SELECT * FROM `{DATABASE_NAME}`.`{TABLE_NAME}`"]

    async with ops_test.fast_forward():
        for unit in mysql_units:
            for attempt in Retrying(
                reraise=True, stop=stop_after_delay(5 * 60), wait=wait_fixed(10)
            ):
                with attempt:
                    # ensure that all units are up to date (including the previous primary)
                    unit_address = await get_unit_ip(ops_test, unit.name)

                    # ensure the max written value is incrementing (continuous writes is active)
                    max_written_value = await get_max_written_value_in_database(
                        ops_test, unit, server_config_credentials
                    )
                    assert (
                        max_written_value > last_max_written_value
                    ), "Continuous writes not incrementing"

                    # ensure that the unit contains all values up to the max written value
                    all_written_values = set(
                        await execute_queries_on_unit(
                            unit_address,
                            server_config_credentials["username"],
                            server_config_credentials["password"],
                            select_all_continuous_writes_sql,
                        )
                    )
                    numbers = set(range(1, max_written_value))
                    assert (
                        numbers <= all_written_values
                    ), f"Missing numbers in database for unit {unit.name}"

                    last_max_written_value = max_written_value
