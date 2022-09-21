#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from pathlib import Path

import pytest
import yaml
from helpers import (
    app_name,
    cut_network_from_unit,
    execute_commands_on_unit,
    generate_random_string,
    get_controller_machine,
    get_primary_unit_wrapper,
    get_process_pid,
    get_system_user_password,
    get_unit_ip,
    graceful_stop_server,
    instance_ip,
    is_connection_possible,
    is_machine_reachable_from,
    is_unit_in_cluster,
    restore_network_for_unit,
    scale_application,
    start_server,
    unit_hostname,
    wait_network_restore,
)
from pytest_operator.plugin import OpsTest
from tenacity import RetryError, Retrying, stop_after_attempt, wait_fixed

from src.constants import CLUSTER_ADMIN_USERNAME, SERVER_CONFIG_USERNAME

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = METADATA["name"]
MYSQL_DAEMON = "mysqld"


async def build_and_deploy(ops_test: OpsTest) -> None:
    """Build and deploy."""
    if app := await app_name(ops_test):
        async with ops_test.fast_forward():
            await scale_application(ops_test, app, 3)
            return

    # Build and deploy charm from local source folder
    charm = await ops_test.build_charm(".")

    # Reduce the update_status frequency until the cluster is deployed
    async with ops_test.fast_forward():
        await ops_test.model.deploy(charm, application_name=APP_NAME, num_units=3)

        await ops_test.model.block_until(
            lambda: len(ops_test.model.applications[APP_NAME].units) == 3
        )
        await ops_test.model.wait_for_idle(
            apps=[APP_NAME],
            status="active",
            raise_on_blocked=True,
            timeout=1000,
        )


@pytest.mark.order(1)
@pytest.mark.abort_on_fail
@pytest.mark.healing_tests
async def test_kill_db_process(ops_test: OpsTest) -> None:
    """Kill mysqld process and check for auto cluster recovery."""
    await build_and_deploy(ops_test)

    app = await app_name(ops_test)

    primary_unit = await get_primary_unit_wrapper(ops_test, app)
    another_unit = (set(ops_test.model.applications[app].units) - {primary_unit}).pop()

    primary_unit_ip = await get_unit_ip(ops_test, primary_unit.name)

    # get running mysqld PID
    pid = await get_process_pid(ops_test, primary_unit.name, MYSQL_DAEMON)

    # kill mysqld for the unit
    logger.info(f"Killing process id {pid}")
    await ops_test.juju("ssh", primary_unit.name, "sudo", "kill", "-9", pid)

    config = {
        "username": CLUSTER_ADMIN_USERNAME,
        "password": await get_system_user_password(primary_unit, CLUSTER_ADMIN_USERNAME),
        "host": primary_unit_ip,
    }

    # retrieve new PID
    new_pid = await get_process_pid(ops_test, primary_unit.name, MYSQL_DAEMON)
    logger.info(f"New process id is {new_pid}")

    # verify that mysqld instance is not the killed one
    assert new_pid != pid, "❌ PID for mysql daemon did not change"

    # verify daemon restarted via connection
    assert is_connection_possible(config), f"❌ Daemon did not restart on unit {primary_unit.name}"

    # verify instance is part of the cluster
    logger.info("Check if instance back in cluster")
    assert await is_unit_in_cluster(
        ops_test, primary_unit.name, another_unit.name
    ), " Unit not online in the cluster"


@pytest.mark.order(2)
@pytest.mark.abort_on_fail
@pytest.mark.healing_tests
async def test_freeze_db_process(ops_test: OpsTest):
    """Freeze and unfreeze process and check for auto cluster recovery."""
    app = await app_name(ops_test)
    primary_unit = await get_primary_unit_wrapper(ops_test, app)
    another_unit = (set(ops_test.model.applications[app].units) - {primary_unit}).pop()

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

    # verify instance is part of the cluster
    logger.info("Check if instance in cluster")
    assert await is_unit_in_cluster(
        ops_test, primary_unit.name, another_unit.name
    ), "❌ Unit not online in the cluster"


@pytest.mark.order(3)
@pytest.mark.abort_on_fail
@pytest.mark.healing_tests
async def test_network_cut(ops_test: OpsTest):
    """Completely cut and restore network."""
    app = await app_name(ops_test)
    primary_unit = await get_primary_unit_wrapper(ops_test, app)
    all_units = ops_test.model.applications[app].units
    another_unit = (set(all_units) - {primary_unit}).pop()

    # get unit hostname
    primary_hostname = await unit_hostname(ops_test, primary_unit.name)

    logger.info(f"Unit {primary_unit.name} it's on machine {primary_hostname} ✅")

    model_name = ops_test.model.info.name
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
    wait_network_restore(model_name, primary_hostname, primary_unit_ip)

    # update instance ip as it may change on network restore
    config["host"] = instance_ip(model_name, primary_hostname)

    # verify that connection is possible
    assert is_connection_possible(config), "❌ Connection is not possible after network restore"

    # verify instance is part of the cluster
    logger.info("Check if instance in cluster")
    assert await is_unit_in_cluster(
        ops_test, primary_unit.name, another_unit.name
    ), "Unit not online in the cluster"


@pytest.mark.order(4)
@pytest.mark.abort_on_fail
@pytest.mark.healing_tests
async def test_replicate_data_on_restart(ops_test: OpsTest):
    """Stop server, write data, start and validate replication."""
    app = await app_name(ops_test)
    primary_unit = await get_primary_unit_wrapper(ops_test, app)
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

    logger.info(f"Stopping server on unit {primary_unit.name}")
    await graceful_stop_server(ops_test, primary_unit.name)

    # verify that connection is gone
    assert not is_connection_possible(
        config
    ), f"❌ Connection to host {primary_unit_ip} is possible"

    # get primary to write to it
    server_config_password = await get_system_user_password(primary_unit, SERVER_CONFIG_USERNAME)
    logger.info("Get new primary")
    new_primary_unit = await get_primary_unit_wrapper(ops_test, app)
    new_primary_unit_ip = await get_unit_ip(ops_test, new_primary_unit.name)

    random_chars = generate_random_string(40)
    create_records_sql = [
        "CREATE DATABASE IF NOT EXISTS test",
        "DROP TABLE IF EXISTS test.data_replication_table",
        "CREATE TABLE test.data_replication_table (id varchar(40), primary key(id))",
        f"INSERT INTO test.data_replication_table VALUES ('{random_chars}')",
    ]

    logger.info("Write to new primary")
    await execute_commands_on_unit(
        new_primary_unit_ip,
        SERVER_CONFIG_USERNAME,
        server_config_password,
        create_records_sql,
        commit=True,
    )

    # restart server on old primary
    logger.info(f"Re starting server on unit {primary_unit.name}")
    await start_server(ops_test, primary_unit.name)

    # verify/wait availability
    assert is_connection_possible(config), "❌ Connection not possible after restart"

    # read and verify data
    select_data_sql = [
        f"SELECT * FROM test.data_replication_table WHERE id = '{random_chars}'",
    ]

    # allow some time for sync
    try:
        for attempt in Retrying(stop=stop_after_attempt(3), wait=wait_fixed(5)):
            with attempt:
                output = await execute_commands_on_unit(
                    primary_unit_ip,
                    SERVER_CONFIG_USERNAME,
                    server_config_password,
                    select_data_sql,
                )
                assert random_chars in output, "❌ Data was not synced"
    except RetryError:
        assert False, "❌ Data was not synced"
