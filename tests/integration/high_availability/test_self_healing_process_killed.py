# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from pathlib import Path

import pytest
import yaml
from pytest_operator.plugin import OpsTest

from ..helpers import (
    get_primary_unit_wrapper,
    get_process_pid,
)
from .high_availability_helpers import (
    clean_up_database_and_table,
    ensure_all_units_continuous_writes_incrementing,
    ensure_n_online_mysql_members,
    get_application_name,
    insert_data_into_mysql_and_validate_replication,
)

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = METADATA["name"]
MYSQL_DAEMON = "mysqld"
WAIT_TIMEOUT = 30 * 60


@pytest.mark.abort_on_fail
async def test_kill_db_process(
    ops_test: OpsTest, highly_available_cluster, continuous_writes
) -> None:
    """Kill mysqld process and check for auto cluster recovery."""
    mysql_application_name = get_application_name(ops_test, "mysql")

    await ensure_all_units_continuous_writes_incrementing(ops_test)

    primary_unit = await get_primary_unit_wrapper(ops_test, mysql_application_name)

    # ensure all units in the cluster are online
    assert await ensure_n_online_mysql_members(
        ops_test, 3
    ), "The deployed mysql application is not fully online"

    # get running mysqld PID
    pid = await get_process_pid(ops_test, primary_unit.name, MYSQL_DAEMON)

    # kill mysqld for the unit
    logger.info(f"Killing process id {pid}")
    await ops_test.juju("ssh", primary_unit.name, "sudo", "kill", "-9", pid)

    # retrieve new PID
    new_pid = await get_process_pid(ops_test, primary_unit.name, MYSQL_DAEMON)
    logger.info(f"New process id is {new_pid}")

    # verify that mysqld instance is not the killed one
    assert new_pid != pid, "❌ PID for mysql daemon did not change"

    # ensure continuous writes still incrementing for all units
    async with ops_test.fast_forward():
        await ensure_all_units_continuous_writes_incrementing(ops_test)

    # ensure that we are able to insert data into the primary and have it replicated to all units
    database_name, table_name = "test-kill-db-process", "data"
    await insert_data_into_mysql_and_validate_replication(ops_test, database_name, table_name)
    await clean_up_database_and_table(ops_test, database_name, table_name)
