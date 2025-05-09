# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from pathlib import Path

import pytest
import yaml
from pytest_operator.plugin import OpsTest

from constants import SERVER_CONFIG_USERNAME

from ..helpers import (
    execute_queries_on_unit,
    get_primary_unit_wrapper,
    get_system_user_password,
    get_unit_ip,
    graceful_stop_server,
    is_unit_in_cluster,
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
async def test_sst_test(ops_test: OpsTest, highly_available_cluster, continuous_writes):
    """The SST test.

    A forceful restart instance with deleted data and without transaction logs (forced clone).
    """
    mysql_application_name = get_application_name(ops_test, "mysql")
    primary_unit = await get_primary_unit_wrapper(ops_test, mysql_application_name)
    server_config_password = await get_system_user_password(primary_unit, SERVER_CONFIG_USERNAME)
    all_units = ops_test.model.applications[mysql_application_name].units

    # ensure continuous writes still incrementing for all units
    await ensure_all_units_continuous_writes_incrementing(ops_test)

    # copy data dir content removal script
    await ops_test.juju("scp", "tests/integration/clean-data-dir.sh", f"{primary_unit.name}:/tmp")

    logger.info(f"Stopping server on unit {primary_unit.name}")
    await graceful_stop_server(ops_test, primary_unit.name)

    logger.info("Removing data directory")
    # data removal run within a script
    # so it allow `*` expansion
    return_code, _, _ = await ops_test.juju(
        "ssh",
        primary_unit.name,
        "sudo",
        "/tmp/clean-data-dir.sh",
    )

    assert return_code == 0, "❌ Failed to remove data directory"

    # Flush and purge bin logs on remaining units
    purge_bin_log_sql = ["FLUSH LOGS", "PURGE BINARY LOGS BEFORE NOW()"]
    for unit in all_units:
        if unit.name != primary_unit.name:
            logger.info(f"Purge binlogs on unit {unit.name}")
            unit_ip = await get_unit_ip(ops_test, unit.name)
            await execute_queries_on_unit(
                unit_ip, SERVER_CONFIG_USERNAME, server_config_password, purge_bin_log_sql, True
            )

    async with ops_test.fast_forward():
        # Wait for unit switch to maintenance status
        logger.info("Waiting unit to enter in maintenance.")
        await ops_test.model.block_until(
            lambda: primary_unit.workload_status == "maintenance",
            timeout=WAIT_TIMEOUT,
        )

        # Wait for unit switch back to active status, this is where self-healing happens
        logger.info("Waiting unit to be back online.")
        await ops_test.model.block_until(
            lambda: primary_unit.workload_status == "active",
            timeout=WAIT_TIMEOUT,
        )

    new_primary_unit = await get_primary_unit_wrapper(ops_test, mysql_application_name)

    # verify new primary
    assert primary_unit.name != new_primary_unit.name, "❌ Primary hasn't changed."

    # verify instance is part of the cluster
    logger.info("Check if instance in cluster")
    assert await is_unit_in_cluster(primary_unit.name, new_primary_unit), (
        "❌ Unit not online in the cluster"
    )

    await ensure_all_units_continuous_writes_incrementing(ops_test)

    # ensure that we are able to insert data into the primary and have it replicated to all units
    database_name, table_name = "test-forceful-restart", "data"
    await insert_data_into_mysql_and_validate_replication(ops_test, database_name, table_name)
    await clean_up_database_and_table(ops_test, database_name, table_name)
