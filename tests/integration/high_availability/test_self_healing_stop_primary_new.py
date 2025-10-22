# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import random

import jubilant_backports
import pytest
from jubilant_backports import Juju

from constants import CLUSTER_ADMIN_USERNAME, SERVER_CONFIG_USERNAME

from ..helpers import (
    execute_queries_on_unit,
    generate_random_string,
    is_connection_possible,
)
from .high_availability_helpers_new import (
    TEST_DATABASE_NAME,
    check_mysql_units_writes_increment,
    get_app_units,
    get_mysql_primary_unit,
    get_unit_ip,
    remove_mysql_test_data,
    start_mysql_process_gracefully,
    stop_mysql_process_gracefully,
    update_interval,
    verify_mysql_test_data,
    wait_for_apps_status,
)

MYSQL_APP_NAME = "mysql"
MYSQL_TEST_APP_NAME = "mysql-test-app"

MINUTE_SECS = 60

logging.getLogger("jubilant.wait").setLevel(logging.WARNING)


@pytest.mark.abort_on_fail
def test_deploy_highly_available_cluster(juju: Juju, charm: str) -> None:
    """Simple test to ensure that the MySQL and application charms get deployed."""
    logging.info("Deploying MySQL cluster")
    juju.deploy(
        charm=charm,
        app=MYSQL_APP_NAME,
        base="ubuntu@22.04",
        config={"profile": "testing"},
        num_units=3,
    )
    juju.deploy(
        charm=MYSQL_TEST_APP_NAME,
        app=MYSQL_TEST_APP_NAME,
        base="ubuntu@22.04",
        channel="latest/edge",
        config={"sleep_interval": 500},
        num_units=1,
    )

    juju.integrate(
        f"{MYSQL_APP_NAME}:database",
        f"{MYSQL_TEST_APP_NAME}:database",
    )

    logging.info("Wait for applications to become active")
    juju.wait(
        ready=wait_for_apps_status(
            jubilant_backports.all_active, MYSQL_APP_NAME, MYSQL_TEST_APP_NAME
        ),
        error=jubilant_backports.any_blocked,
        timeout=20 * MINUTE_SECS,
    )


@pytest.mark.abort_on_fail
async def test_replicate_data_on_restart(juju: Juju, continuous_writes_new) -> None:
    """Stop server, write data, start and validate replication."""
    # Ensure continuous writes still incrementing for all units
    await check_mysql_units_writes_increment(juju, MYSQL_APP_NAME)

    mysql_units = get_app_units(juju, MYSQL_APP_NAME)
    mysql_primary_unit = get_mysql_primary_unit(juju, MYSQL_APP_NAME)
    mysql_primary_unit_ip = get_unit_ip(juju, MYSQL_APP_NAME, mysql_primary_unit)

    credentials_task = juju.run(
        unit=mysql_primary_unit,
        action="get-password",
        params={"username": CLUSTER_ADMIN_USERNAME},
    )
    credentials_task.raise_on_failure()

    config = {
        "username": credentials_task.results["username"],
        "password": credentials_task.results["password"],
        "host": mysql_primary_unit_ip,
    }

    # Verify that connection is possible
    assert is_connection_possible(config)

    # It is necessary to inhibit update-status-hook to stop the service
    # since the charm will restart the service on the hook
    with update_interval(juju, "60m"):
        logging.info(f"Stopping server on unit {mysql_primary_unit}")
        stop_mysql_process_gracefully(juju, mysql_primary_unit)

        # Verify that connection is gone
        assert not is_connection_possible(config)

        online_units = set(mysql_units) - {mysql_primary_unit}
        online_units = list(online_units)
        random_unit = random.choice(online_units)

        new_mysql_primary_unit = get_mysql_primary_unit(juju, MYSQL_APP_NAME, random_unit)

        logging.info("Write to new primary")
        table_name = "data"
        table_value = generate_random_string(255)
        await insert_mysql_test_data(
            juju, MYSQL_APP_NAME, new_mysql_primary_unit, table_name, table_value
        )

        logging.info(f"Starting server on unit {mysql_primary_unit}")
        start_mysql_process_gracefully(juju, mysql_primary_unit)

    # Verify that connection is possible
    assert is_connection_possible(config, retry_if_not_possible=True)

    await verify_mysql_test_data(juju, MYSQL_APP_NAME, table_name, table_value)
    await remove_mysql_test_data(juju, MYSQL_APP_NAME, table_name)


async def insert_mysql_test_data(
    juju: Juju,
    app_name: str,
    unit_name: str,
    table_name: str,
    table_value: str,
) -> None:
    """Insert data into the MySQL database.

    Args:
        juju: The Juju model.
        app_name: The application name.
        unit_name: The application unit to insert data into.
        table_name: The database table name.
        table_value: The value to insert.
    """
    credentials_task = juju.run(
        unit=unit_name,
        action="get-password",
        params={"username": SERVER_CONFIG_USERNAME},
    )
    credentials_task.raise_on_failure()

    insert_queries = [
        f"CREATE DATABASE IF NOT EXISTS `{TEST_DATABASE_NAME}`",
        f"CREATE TABLE IF NOT EXISTS `{TEST_DATABASE_NAME}`.`{table_name}` (id VARCHAR(255), PRIMARY KEY (id))",
        f"INSERT INTO `{TEST_DATABASE_NAME}`.`{table_name}` (id) VALUES ('{table_value}')",
    ]

    await execute_queries_on_unit(
        get_unit_ip(juju, app_name, unit_name),
        credentials_task.results["username"],
        credentials_task.results["password"],
        insert_queries,
        commit=True,
    )
