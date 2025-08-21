# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import logging
from pathlib import Path

import pytest
import yaml
from pytest_operator.plugin import OpsTest

from constants import CLUSTER_ADMIN_USERNAME

from ..helpers import (
    get_system_user_password,
    get_unit_ip,
    graceful_stop_server,
    is_connection_possible,
    start_server,
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
async def test_cluster_pause(ops_test: OpsTest, highly_available_cluster, continuous_writes):
    """Pause test.

    A graceful simultaneous restart of all instances,
    check primary election after the start, write and read data
    """
    mysql_application_name = get_application_name(ops_test, "mysql")
    all_units = ops_test.model.applications[mysql_application_name].units

    config = {
        "username": CLUSTER_ADMIN_USERNAME,
        "password": await get_system_user_password(all_units[0], CLUSTER_ADMIN_USERNAME),
    }

    # ensure update status won't run to avoid self healing
    await ops_test.model.set_config({"update-status-hook-interval": "60m"})

    # stop all instances
    logger.info("Stopping all instances")

    await asyncio.gather(
        graceful_stop_server(ops_test, all_units[0].name),
        graceful_stop_server(ops_test, all_units[1].name),
        graceful_stop_server(ops_test, all_units[2].name),
    )

    # verify connection is not possible to any instance
    for unit in all_units:
        unit_ip = await get_unit_ip(ops_test, unit.name)
        config["host"] = unit_ip
        assert not is_connection_possible(config), (
            f"❌ connection to unit {unit.name} is still possible"
        )

    # restart all instances
    logger.info("Starting all instances")
    for unit in all_units:
        await start_server(ops_test, unit.name)

    async with ops_test.fast_forward():
        logger.info("Waiting units to enter maintenance.")
        await ops_test.model.block_until(
            lambda: {unit.workload_status for unit in all_units} == {"maintenance"},
            timeout=WAIT_TIMEOUT,
        )
        logger.info("Waiting units to be back online.")
        await ops_test.model.block_until(
            lambda: {unit.workload_status for unit in all_units} == {"active"},
            timeout=WAIT_TIMEOUT,
        )

    # ensure continuous writes still incrementing for all units
    await ensure_all_units_continuous_writes_incrementing(ops_test)

    # ensure that we are able to insert data into the primary and have it replicated to all units
    database_name, table_name = "test-cluster-pause", "data"
    await insert_data_into_mysql_and_validate_replication(ops_test, database_name, table_name)
    await clean_up_database_and_table(ops_test, database_name, table_name)

    # return to default
    await ops_test.model.set_config({"update-status-hook-interval": "5m"})
