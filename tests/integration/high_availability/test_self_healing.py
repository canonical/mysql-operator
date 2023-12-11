#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import logging
from pathlib import Path

import pytest
import yaml
from pytest_operator.plugin import OpsTest
from tenacity import RetryError, Retrying, stop_after_attempt, wait_fixed

from constants import CLUSTER_ADMIN_USERNAME, SERVER_CONFIG_USERNAME

from ..helpers import (
    cut_network_from_unit,
    execute_queries_on_unit,
    get_controller_machine,
    get_primary_unit_wrapper,
    get_process_pid,
    get_system_user_password,
    get_unit_ip,
    graceful_stop_server,
    is_connection_possible,
    is_machine_reachable_from,
    is_unit_in_cluster,
    restore_network_for_unit,
    start_server,
    unit_hostname,
    wait_network_restore,
    write_random_chars_to_test_table,
)
from .high_availability_helpers import (
    clean_up_database_and_table,
    ensure_all_units_continuous_writes_incrementing,
    ensure_n_online_mysql_members,
    high_availability_test_setup,
    insert_data_into_mysql_and_validate_replication,
)

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = METADATA["name"]
MYSQL_DAEMON = "mysqld"
WAIT_TIMEOUT = 30 * 60


@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest, mysql_charm_series: str) -> None:
    """Build and deploy."""
    await high_availability_test_setup(ops_test, mysql_charm_series)


@pytest.mark.abort_on_fail
async def test_kill_db_process(
    ops_test: OpsTest, continuous_writes, mysql_charm_series: str
) -> None:
    """Kill mysqld process and check for auto cluster recovery."""
    mysql_application_name, _ = await high_availability_test_setup(ops_test, mysql_charm_series)

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


@pytest.mark.abort_on_fail
async def test_freeze_db_process(ops_test: OpsTest, continuous_writes, mysql_charm_series: str):
    """Freeze and unfreeze process and check for auto cluster recovery."""
    mysql_application_name, _ = await high_availability_test_setup(ops_test, mysql_charm_series)
    # ensure continuous writes still incrementing for all units
    await ensure_all_units_continuous_writes_incrementing(ops_test)

    primary_unit = await get_primary_unit_wrapper(ops_test, mysql_application_name)
    primary_unit_ip = await get_unit_ip(ops_test, primary_unit.name)

    # get running mysqld PID
    pid = await get_process_pid(ops_test, primary_unit.name, MYSQL_DAEMON)

    # freeze (STOP signal) mysqld for the unit
    logger.info(f"Freezing process id {pid}")
    await ops_test.juju("ssh", primary_unit.name, "sudo", "kill", "-19", pid)

    config = {
        "username": CLUSTER_ADMIN_USERNAME,
        "password": await get_system_user_password(primary_unit, CLUSTER_ADMIN_USERNAME),
        "host": primary_unit_ip,
    }

    # verify that connection is not possible
    assert not is_connection_possible(config), "❌ Mysqld is not paused"

    # unfreeze (CONT signal) mysqld for the unit
    logger.info(f"Unfreezing process id {pid}")
    await ops_test.juju("ssh", primary_unit.name, "sudo", "kill", "-18", pid)

    # verify that connection is possible
    assert is_connection_possible(config), "❌ Mysqld is paused"

    # ensure continuous writes still incrementing for all units
    async with ops_test.fast_forward():
        await ensure_all_units_continuous_writes_incrementing(ops_test)

    # ensure that we are able to insert data into the primary and have it replicated to all units
    database_name, table_name = "test-freeze-db-process", "data"
    await insert_data_into_mysql_and_validate_replication(ops_test, database_name, table_name)
    await clean_up_database_and_table(ops_test, database_name, table_name)


@pytest.mark.abort_on_fail
async def test_network_cut(ops_test: OpsTest, continuous_writes, mysql_charm_series: str):
    """Completely cut and restore network."""
    mysql_application_name, _ = await high_availability_test_setup(ops_test, mysql_charm_series)
    primary_unit = await get_primary_unit_wrapper(ops_test, mysql_application_name)
    all_units = ops_test.model.applications[mysql_application_name].units

    # ensure continuous writes still incrementing for all units
    await ensure_all_units_continuous_writes_incrementing(ops_test)

    # get unit hostname
    primary_hostname = await unit_hostname(ops_test, primary_unit.name)

    logger.info(f"Unit {primary_unit.name} it's on machine {primary_hostname} ✅")

    primary_unit_ip = await get_unit_ip(ops_test, primary_unit.name)

    config = {
        "username": CLUSTER_ADMIN_USERNAME,
        "password": await get_system_user_password(primary_unit, CLUSTER_ADMIN_USERNAME),
        "host": primary_unit_ip,
    }

    # verify that connection is possible
    assert is_connection_possible(
        config
    ), f"❌ Connection to host {primary_unit_ip} is not possible"

    logger.info(f"Cutting network for {primary_hostname}")
    cut_network_from_unit(primary_hostname)

    # verify machine is not reachable from peer units
    for unit in set(all_units) - {primary_unit}:
        hostname = await unit_hostname(ops_test, unit.name)
        assert not is_machine_reachable_from(
            hostname, primary_hostname
        ), "❌ unit is reachable from peer"

    # verify machine is not reachable from controller
    controller = await get_controller_machine(ops_test)
    assert not is_machine_reachable_from(
        controller, primary_hostname
    ), "❌ unit is reachable from controller"

    # verify that connection is not possible
    assert not is_connection_possible(config), "❌ Connection is possible after network cut"

    logger.info(f"Restoring network for {primary_hostname}")
    restore_network_for_unit(primary_hostname)

    # wait until network is reestablished for the unit
    await wait_network_restore(ops_test, primary_unit.name, primary_unit_ip)

    # update instance ip as it may change on network restore
    config["host"] = await get_unit_ip(ops_test, primary_unit.name)

    # verify that connection is possible
    assert is_connection_possible(config), "❌ Connection is not possible after network restore"

    # ensure continuous writes still incrementing for all units
    async with ops_test.fast_forward():
        # wait for the unit to be ready
        logger.info(f"Waiting for {primary_unit.name} to enter maintenance")
        await ops_test.model.block_until(
            lambda: primary_unit.workload_status in ["maintenance", "active"], timeout=30 * 60
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


@pytest.mark.abort_on_fail
async def test_replicate_data_on_restart(
    ops_test: OpsTest, continuous_writes, mysql_charm_series: str
):
    """Stop server, write data, start and validate replication."""
    mysql_application_name, _ = await high_availability_test_setup(ops_test, mysql_charm_series)

    # ensure continuous writes still incrementing for all units
    await ensure_all_units_continuous_writes_incrementing(ops_test)

    primary_unit = await get_primary_unit_wrapper(ops_test, mysql_application_name)
    primary_unit_ip = await get_unit_ip(ops_test, primary_unit.name)

    config = {
        "username": CLUSTER_ADMIN_USERNAME,
        "password": await get_system_user_password(primary_unit, CLUSTER_ADMIN_USERNAME),
        "host": primary_unit_ip,
    }

    # verify that connection is possible
    assert is_connection_possible(
        config
    ), f"❌ Connection to host {primary_unit_ip} is not possible"

    # it's necessary to inhibit update-status-hook to stop the service
    # since the charm will restart the service on the hook
    await ops_test.model.set_config({"update-status-hook-interval": "60m"})
    logger.info(f"Stopping server on unit {primary_unit.name}")
    await graceful_stop_server(ops_test, primary_unit.name)

    # verify that connection is gone
    assert not is_connection_possible(
        config
    ), f"❌ Connection to host {primary_unit_ip} is possible"

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
    assert is_connection_possible(config), "❌ Connection not possible after restart"

    # read and verify data
    select_data_sql = [
        f"SELECT * FROM test.data_replication_table WHERE id = '{random_chars}'",
    ]

    # allow some time for sync
    try:
        for attempt in Retrying(stop=stop_after_attempt(10), wait=wait_fixed(5)):
            with attempt:
                output = await execute_queries_on_unit(
                    primary_unit_ip,
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


@pytest.mark.abort_on_fail
@pytest.mark.unstable
async def test_cluster_pause(ops_test: OpsTest, continuous_writes, mysql_charm_series: str):
    """Pause test.

    A graceful simultaneous restart of all instances,
    check primary election after the start, write and read data
    """
    mysql_application_name, _ = await high_availability_test_setup(ops_test, mysql_charm_series)
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
        assert not is_connection_possible(
            config
        ), f"❌ connection to unit {unit.name} is still possible"

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


@pytest.mark.abort_on_fail
async def test_sst_test(ops_test: OpsTest, continuous_writes, mysql_charm_series: str):
    """The SST test.

    A forceful restart instance with deleted data and without transaction logs (forced clone).
    """
    mysql_application_name, _ = await high_availability_test_setup(ops_test, mysql_charm_series)
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
    assert await is_unit_in_cluster(
        primary_unit.name, new_primary_unit
    ), "❌ Unit not online in the cluster"

    await ensure_all_units_continuous_writes_incrementing(ops_test)

    # ensure that we are able to insert data into the primary and have it replicated to all units
    database_name, table_name = "test-forceful-restart", "data"
    await insert_data_into_mysql_and_validate_replication(ops_test, database_name, table_name)
    await clean_up_database_and_table(ops_test, database_name, table_name)
