# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from pathlib import Path

import pytest
import yaml
from pytest_operator.plugin import OpsTest

from constants import CLUSTER_ADMIN_USERNAME

from ..helpers import (
    get_primary_unit_wrapper,
    get_process_pid,
    get_system_user_password,
    is_connection_possible,
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
async def test_freeze_db_process(ops_test: OpsTest, highly_available_cluster, continuous_writes):
    """Freeze and unfreeze process and check for auto cluster recovery."""
    mysql_application_name = get_application_name(ops_test, "mysql")

    # ensure continuous writes still incrementing for all units
    await ensure_all_units_continuous_writes_incrementing(ops_test)

    primary_unit = await get_primary_unit_wrapper(ops_test, mysql_application_name)
    primary_address = await primary_unit.get_public_address()

    # get running mysqld PID
    pid = await get_process_pid(ops_test, primary_unit.name, MYSQL_DAEMON)

    # freeze (STOP signal) mysqld for the unit
    logger.info(f"Freezing process id {pid}")
    await ops_test.juju("ssh", primary_unit.name, "sudo", "kill", "-19", pid)

    logger.info("Get cluster admin password")
    config = {
        "username": CLUSTER_ADMIN_USERNAME,
        "password": await get_system_user_password(primary_unit, CLUSTER_ADMIN_USERNAME),
        "host": primary_address,
    }

    # verify that connection is not possible
    logger.info(f"Verifying that connection to host {primary_address} is not possible")
    assert not is_connection_possible(config), "❌ Mysqld is not paused"

    # unfreeze (CONT signal) mysqld for the unit
    logger.info(f"Unfreezing process id {pid}")
    await ops_test.juju("ssh", primary_unit.name, "sudo", "kill", "-18", pid)

    # verify that connection is possible
    logger.info(f"Verifying that connection to host {primary_address} is possible")
    assert is_connection_possible(config), "❌ Mysqld is paused"

    # ensure continuous writes still incrementing for all units
    async with ops_test.fast_forward():
        await ensure_all_units_continuous_writes_incrementing(ops_test)

    # ensure that we are able to insert data into the primary and have it replicated to all units
    database_name, table_name = "test-freeze-db-process", "data"
    await insert_data_into_mysql_and_validate_replication(ops_test, database_name, table_name)
    await clean_up_database_and_table(ops_test, database_name, table_name)
