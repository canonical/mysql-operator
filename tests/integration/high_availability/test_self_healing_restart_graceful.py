# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from pathlib import Path

import pytest
import yaml
from pytest_operator.plugin import OpsTest

from constants import CLUSTER_ADMIN_USERNAME

from ..helpers import (
    execute_queries_on_unit,
    get_primary_unit_wrapper,
    get_system_user_password,
    get_unit_ip,
    graceful_stop_server,
    is_connection_possible,
    start_server,
)
from .high_availability_helpers import (
    ensure_all_units_continuous_writes_incrementing,
    get_application_name,
)

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = METADATA["name"]
MYSQL_DAEMON = "mysqld"
WAIT_TIMEOUT = 30 * 60


@pytest.mark.abort_on_fail
async def test_cluster_manual_rejoin(
    ops_test: OpsTest, highly_available_cluster, continuous_writes
):
    """The cluster manual re-join test.

    A graceful restart is performed in one of the instances (choosing Primary to make it painful).
    In order to verify that the instance can come back ONLINE, after disabling automatic re-join
    """
    # Ensure continuous writes still incrementing for all units
    await ensure_all_units_continuous_writes_incrementing(ops_test)

    mysql_app_name = get_application_name(ops_test, "mysql")
    primary_unit = await get_primary_unit_wrapper(ops_test, mysql_app_name)

    config = {
        "username": CLUSTER_ADMIN_USERNAME,
        "password": await get_system_user_password(primary_unit, CLUSTER_ADMIN_USERNAME),
        "host": await get_unit_ip(ops_test, primary_unit.name),
    }

    queries = [
        "SET PERSIST group_replication_autorejoin_tries=0",
    ]

    # Disable automatic re-join procedure
    await execute_queries_on_unit(
        unit_address=config["host"],
        username=config["username"],
        password=config["password"],
        queries=queries,
        commit=True,
    )

    logger.info(f"Stopping server on unit {primary_unit.name}")
    await graceful_stop_server(ops_test, primary_unit.name)

    # Verify connection is not possible
    assert not is_connection_possible(config), "❌ Connection is possible after instance stop"

    logger.info(f"Re starting server on unit {primary_unit.name}")
    await start_server(ops_test, primary_unit.name)

    # Verify unit comes back active
    async with ops_test.fast_forward():
        logger.info("Waiting unit to be back online.")
        await ops_test.model.block_until(
            lambda: primary_unit.workload_status == "active",
            timeout=WAIT_TIMEOUT,
        )

    # Ensure continuous writes still incrementing for all units
    await ensure_all_units_continuous_writes_incrementing(ops_test)
