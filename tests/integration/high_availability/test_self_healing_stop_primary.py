# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from pathlib import Path

import pytest
import yaml
from pytest_operator.plugin import OpsTest
from tenacity import RetryError, Retrying, stop_after_attempt, wait_fixed

from constants import CLUSTER_ADMIN_USERNAME, SERVER_CONFIG_USERNAME

from ..helpers import (
    execute_queries_on_unit,
    get_primary_unit_wrapper,
    get_system_user_password,
    graceful_stop_server,
    is_connection_possible,
    start_server,
    write_random_chars_to_test_table,
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
async def test_replicate_data_on_restart(
    ops_test: OpsTest, highly_available_cluster, continuous_writes
):
    """Stop server, write data, start and validate replication."""
    mysql_application_name = get_application_name(ops_test, "mysql")

    # ensure continuous writes still incrementing for all units
    await ensure_all_units_continuous_writes_incrementing(ops_test)

    primary_unit = await get_primary_unit_wrapper(ops_test, mysql_application_name)
    primary_address = await primary_unit.get_public_address()

    config = {
        "username": CLUSTER_ADMIN_USERNAME,
        "password": await get_system_user_password(primary_unit, CLUSTER_ADMIN_USERNAME),
        "host": primary_address,
    }

    # verify that connection is possible
    assert is_connection_possible(
        config
    ), f"❌ Connection to host {primary_address} is not possible"

    # it's necessary to inhibit update-status-hook to stop the service
    # since the charm will restart the service on the hook
    await ops_test.model.set_config({"update-status-hook-interval": "60m"})
    logger.info(f"Stopping server on unit {primary_unit.name}")
    await graceful_stop_server(ops_test, primary_unit.name)

    # verify that connection is gone
    assert not is_connection_possible(
        config
    ), f"❌ Connection to host {primary_address} is possible"

    # get primary to write to it
    server_config_password = await get_system_user_password(primary_unit, SERVER_CONFIG_USERNAME)
    logger.info("Get new primary")
    new_primary_unit = await get_primary_unit_wrapper(
        ops_test, mysql_application_name, unit_excluded=primary_unit
    )

    logger.info("Write to new primary")
    random_chars = await write_random_chars_to_test_table(ops_test, new_primary_unit)

    # restart server on old primary
    logger.info(f"Re starting server on unit {primary_unit.name}")
    await start_server(ops_test, primary_unit.name)

    # restore standard interval
    await ops_test.model.set_config({"update-status-hook-interval": "5m"})

    # verify/wait availability
    assert is_connection_possible(
        config, retry_if_not_possible=True
    ), "❌ Connection not possible after restart"

    # read and verify data
    select_data_sql = [
        f"SELECT * FROM test.data_replication_table WHERE id = '{random_chars}'",
    ]

    # allow some time for sync
    try:
        for attempt in Retrying(stop=stop_after_attempt(10), wait=wait_fixed(5)):
            with attempt:
                output = await execute_queries_on_unit(
                    primary_address,
                    SERVER_CONFIG_USERNAME,
                    server_config_password,
                    select_data_sql,
                )
                assert random_chars in output, "❌ Data was not synced"
    except RetryError:
        assert False, "❌ Data was not synced"

    # ensure continuous writes still incrementing for all units
    async with ops_test.fast_forward():
        await ensure_all_units_continuous_writes_incrementing(ops_test)

    # ensure that we are able to insert data into the primary and have it replicated to all units
    database_name, table_name = "test-replicate-data-restart", "data"
    await insert_data_into_mysql_and_validate_replication(ops_test, database_name, table_name)
    await clean_up_database_and_table(ops_test, database_name, table_name)
