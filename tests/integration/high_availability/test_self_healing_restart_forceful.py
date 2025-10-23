# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import logging

import jubilant_backports
import pytest
from jubilant_backports import Juju
from tenacity import (
    retry,
    stop_after_attempt,
    wait_fixed,
)

from constants import SERVER_CONFIG_USERNAME

from ..helpers import generate_random_string
from .high_availability_helpers_new import (
    check_mysql_units_writes_increment,
    execute_queries_on_unit,
    get_app_leader,
    get_app_units,
    get_mysql_cluster_status,
    get_mysql_primary_unit,
    get_mysql_unit_name,
    get_unit_ip,
    insert_mysql_test_data,
    remove_mysql_test_data,
    stop_mysql_process_gracefully,
    update_interval,
    verify_mysql_test_data,
    wait_for_apps_status,
    wait_for_unit_status,
)

MYSQL_APP_NAME = "mysql"
MYSQL_PROCESS_NAME = "mysqld"
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
async def test_sst_test(juju: Juju, continuous_writes_new):
    """Test a forceful restart with deleted data and without transaction logs (forced clone)."""
    # Ensure continuous writes still incrementing for all units
    await check_mysql_units_writes_increment(juju, MYSQL_APP_NAME)

    mysql_units = get_app_units(juju, MYSQL_APP_NAME)
    mysql_primary_unit = get_mysql_primary_unit(juju, MYSQL_APP_NAME)

    # Copy data dir content removal script
    juju.scp("tests/integration/clean-data-dir.sh", f"{mysql_primary_unit}:/tmp")

    logging.info(f"Stopping server on unit {mysql_primary_unit}")
    stop_mysql_process_gracefully(juju, mysql_primary_unit)

    logging.info("Removing data directory")
    juju.exec("sudo /tmp/clean-data-dir.sh", unit=mysql_primary_unit)

    # Flush and purge bin logs on remaining units
    for unit_name in mysql_units:
        if unit_name != mysql_primary_unit:
            logging.info(f"Purge binary logs on unit {unit_name}")
            await purge_mysql_binary_logs(juju, MYSQL_APP_NAME, unit_name)

    with update_interval(juju, "10s"):
        logging.info("Waiting unit to enter maintenance")
        juju.wait(
            ready=wait_for_unit_status(MYSQL_APP_NAME, mysql_primary_unit, "maintenance"),
            timeout=20 * MINUTE_SECS,
        )

        logging.info("Waiting unit to be back online")
        juju.wait(
            ready=wait_for_unit_status(MYSQL_APP_NAME, mysql_primary_unit, "active"),
            timeout=20 * MINUTE_SECS,
        )

    new_mysql_primary_unit = get_mysql_primary_unit(juju, MYSQL_APP_NAME)
    assert new_mysql_primary_unit != mysql_primary_unit

    # Verify instance is part of the cluster
    logging.info("Check if instance in cluster")
    assert check_unit_in_mysql_cluster(juju, new_mysql_primary_unit)

    # Ensure continuous writes still incrementing for all units
    await check_mysql_units_writes_increment(juju, MYSQL_APP_NAME)

    # Ensure that we are able to insert data into the primary
    table_name = "data"
    table_value = generate_random_string(255)

    await insert_mysql_test_data(juju, MYSQL_APP_NAME, table_name, table_value)
    await verify_mysql_test_data(juju, MYSQL_APP_NAME, table_name, table_value)
    await remove_mysql_test_data(juju, MYSQL_APP_NAME, table_name)


@retry(stop=stop_after_attempt(12), wait=wait_fixed(15), reraise=True)
def check_unit_in_mysql_cluster(juju: Juju, unit_name: str) -> bool:
    """Check is unit is online in the cluster.

    Args:
        juju: The Juju model.
        unit_name: The unit name to check.
    """
    mysql_app_leader = get_app_leader(juju, MYSQL_APP_NAME)
    mysql_cluster_status = get_mysql_cluster_status(juju, mysql_app_leader)
    mysql_cluster_topology = mysql_cluster_status["defaultreplicaset"]["topology"]

    for k, v in mysql_cluster_topology.items():
        if get_mysql_unit_name(k) == unit_name and v.get("status") == "online":
            return True

    return False


async def purge_mysql_binary_logs(juju: Juju, app_name: str, unit_name: str) -> None:
    """Purge MySQL instance binary logs.

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

    await execute_queries_on_unit(
        unit_address=get_unit_ip(juju, app_name, unit_name),
        username=credentials_task.results["username"],
        password=credentials_task.results["password"],
        queries=["FLUSH LOGS", "PURGE BINARY LOGS BEFORE NOW()"],
        commit=True,
    )
