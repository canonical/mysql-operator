# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import logging

import jubilant_backports
import pytest
from jubilant_backports import Juju

from constants import CLUSTER_ADMIN_USERNAME

from ...helpers import (
    generate_random_string,
    is_connection_possible,
)
from .high_availability_helpers_new import (
    check_mysql_units_writes_increment,
    get_app_units,
    get_unit_ip,
    insert_mysql_test_data,
    remove_mysql_test_data,
    start_mysql_process_gracefully,
    stop_mysql_process_gracefully,
    update_interval,
    verify_mysql_test_data,
    wait_for_apps_status,
    wait_for_unit_status,
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
async def test_cluster_pause(juju: Juju, continuous_writes) -> None:
    """Pause test.

    A graceful simultaneous restart of all instances,
    check primary election after the start, write and read data
    """
    # Ensure continuous writes still incrementing for all units
    await check_mysql_units_writes_increment(juju, MYSQL_APP_NAME)

    mysql_units = get_app_units(juju, MYSQL_APP_NAME)

    # Ensure update status will not run to avoid self-healing
    juju.model_config({"update-status-hook-interval": "60m"})

    logging.info("Stopping all instances")
    for unit_name in mysql_units:
        stop_mysql_process_gracefully(juju, unit_name)

    logging.info("Checking all instances connectivity")
    for unit_name in mysql_units:
        credentials_task = juju.run(
            unit=unit_name,
            action="get-password",
            params={"username": CLUSTER_ADMIN_USERNAME},
        )
        config = {
            "username": credentials_task.results["username"],
            "password": credentials_task.results["password"],
            "host": get_unit_ip(juju, MYSQL_APP_NAME, unit_name),
        }

        assert not is_connection_possible(config)

    logging.info("Starting all instances")
    for unit_name in mysql_units:
        start_mysql_process_gracefully(juju, unit_name)

    with update_interval(juju, "10s"):
        logging.info("Waiting units to enter maintenance")
        juju.wait(
            ready=lambda status: all((
                wait_for_unit_status(MYSQL_APP_NAME, f"{MYSQL_APP_NAME}/0", "maintenance")(status),
                wait_for_unit_status(MYSQL_APP_NAME, f"{MYSQL_APP_NAME}/1", "maintenance")(status),
                wait_for_unit_status(MYSQL_APP_NAME, f"{MYSQL_APP_NAME}/2", "maintenance")(status),
            )),
            timeout=20 * MINUTE_SECS,
        )
        logging.info("Waiting units to be back online")
        juju.wait(
            ready=lambda status: all((
                wait_for_unit_status(MYSQL_APP_NAME, f"{MYSQL_APP_NAME}/0", "active")(status),
                wait_for_unit_status(MYSQL_APP_NAME, f"{MYSQL_APP_NAME}/1", "active")(status),
                wait_for_unit_status(MYSQL_APP_NAME, f"{MYSQL_APP_NAME}/2", "active")(status),
            )),
            timeout=20 * MINUTE_SECS,
        )

    # Ensure continuous writes still incrementing for all units
    await check_mysql_units_writes_increment(juju, MYSQL_APP_NAME)

    # Ensure that we are able to insert data into the primary
    table_name = "data"
    table_value = generate_random_string(255)

    await insert_mysql_test_data(juju, MYSQL_APP_NAME, table_name, table_value)
    await verify_mysql_test_data(juju, MYSQL_APP_NAME, table_name, table_value)
    await remove_mysql_test_data(juju, MYSQL_APP_NAME, table_name)

    # Restore standard interval
    juju.model_config({"update-status-hook-interval": "5m"})
