# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from pathlib import Path

import pytest
import yaml
from pytest_operator.plugin import OpsTest
from tenacity import Retrying, stop_after_attempt, wait_fixed

from constants import CLUSTER_ADMIN_USERNAME

from ..helpers import (
    cut_network_from_unit,
    get_controller_machine,
    get_primary_unit_wrapper,
    get_system_user_password,
    get_unit_ip,
    is_connection_possible,
    is_machine_reachable_from,
    restore_network_for_unit,
    unit_hostname,
    wait_network_restore,
)
from .high_availability_helpers import (
    clean_up_database_and_table,
    ensure_all_units_continuous_writes_incrementing,
    get_application_name,
    insert_data_into_mysql_and_validate_replication,
)

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = METADATA["name"]
MYSQL_DAEMON = "mysqld"
WAIT_TIMEOUT = 30 * 60


@pytest.mark.abort_on_fail
async def test_network_cut(ops_test: OpsTest, highly_available_cluster, continuous_writes):
    """Completely cut and restore network."""
    mysql_application_name = get_application_name(ops_test, "mysql")
    primary_unit = await get_primary_unit_wrapper(ops_test, mysql_application_name)
    all_units = ops_test.model.applications[mysql_application_name].units

    # ensure continuous writes still incrementing for all units
    await ensure_all_units_continuous_writes_incrementing(ops_test)

    # get unit hostname
    primary_hostname = await unit_hostname(ops_test, primary_unit.name)

    logger.info(f"Unit {primary_unit.name} it's on machine {primary_hostname} ✅")

    primary_unit_ip = await get_unit_ip(ops_test, primary_unit.name)
    cluster_admin_password = await get_system_user_password(primary_unit, CLUSTER_ADMIN_USERNAME)

    config = {
        "username": CLUSTER_ADMIN_USERNAME,
        "password": cluster_admin_password,
        "host": primary_unit_ip,
    }

    # verify that connection is possible
    assert is_connection_possible(config), (
        f"❌ Connection to host {primary_unit_ip} is not possible"
    )

    logger.info(f"Cutting network for {primary_hostname}")
    cut_network_from_unit(primary_hostname)

    # verify machine is not reachable from peer units
    for unit in set(all_units) - {primary_unit}:
        hostname = await unit_hostname(ops_test, unit.name)
        assert not is_machine_reachable_from(hostname, primary_hostname), (
            "❌ unit is reachable from peer"
        )

    # verify machine is not reachable from controller
    controller = await get_controller_machine(ops_test)
    assert not is_machine_reachable_from(controller, primary_hostname), (
        "❌ unit is reachable from controller"
    )

    # verify that connection is not possible
    assert not is_connection_possible(config), "❌ Connection is possible after network cut"

    logger.info(f"Restoring network for {primary_hostname}")
    restore_network_for_unit(primary_hostname)

    # wait until network is reestablished for the unit
    await wait_network_restore(ops_test, primary_unit.name)

    # ensure continuous writes still incrementing for all units
    async with ops_test.fast_forward():
        # wait for the unit to be ready
        for attempt in Retrying(stop=stop_after_attempt(60), wait=wait_fixed(10)):
            with attempt:
                new_unit_ip = await get_unit_ip(ops_test, primary_unit.name)
                new_unit_config = {
                    "username": CLUSTER_ADMIN_USERNAME,
                    "password": cluster_admin_password,
                    "host": new_unit_ip,
                }

                logger.debug(
                    f"Waiting until connection possible after network restore on {new_unit_ip}"
                )
                assert is_connection_possible(new_unit_config), (
                    "❌ Connection is not possible after network restore"
                )

        logger.info(f"Waiting for {primary_unit.name} to enter active")
        await ops_test.model.block_until(
            lambda: primary_unit.workload_status == "active", timeout=40 * 60
        )

    await ensure_all_units_continuous_writes_incrementing(ops_test)

    # ensure that we are able to insert data into the primary and have it replicated to all units
    database_name, table_name = "test-network-cut", "data"
    await insert_data_into_mysql_and_validate_replication(ops_test, database_name, table_name)
    await clean_up_database_and_table(ops_test, database_name, table_name)
