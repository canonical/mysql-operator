#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from pathlib import Path
from time import sleep

import pytest
import yaml
from helpers import (
    app_name,
    cluster_name,
    cut_network_from_unit,
    execute_commands_on_unit,
    generate_random_string,
    get_primary_unit,
    get_process_pid,
    get_system_user_password,
    graceful_stop_server,
    instance_ip,
    is_connection_possible,
    is_unit_in_cluster,
    restore_network_for_unit,
    scale_application,
    start_server,
    unit_hostname,
    wait_network_restore,
)
from pytest_operator.plugin import OpsTest

from src.constants import CLUSTER_ADMIN_USERNAME, SERVER_CONFIG_USERNAME

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = METADATA["name"]
MYSQL_DAEMON = "mysqld"


async def build_and_deploy(ops_test: OpsTest) -> None:
    """Build and deploy."""
    if app := await app_name(ops_test):
        if len(ops_test.model.applications[app].units) == 3:
            return
        else:
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
    unit = ops_test.model.applications[app].units[0]
    another_unit = ops_test.model.applications[app].units[1]

    # get running mysqld PID
    pid = await get_process_pid(ops_test, unit.name, MYSQL_DAEMON)

    # kill mysqld for the unit
    logger.info(f"Killing process id {pid}")
    await ops_test.juju("ssh", unit.name, "sudo", "kill", "-9", pid)

    config = {
        "username": CLUSTER_ADMIN_USERNAME,
        "password": await get_system_user_password(unit, CLUSTER_ADMIN_USERNAME),
        "host": await unit.get_public_address(),
    }

    # verify connection so daemon is restarted
    assert is_connection_possible(config), "❌ Daemon did not restarted"

    # retrieve new PID
    new_pid = await get_process_pid(ops_test, unit.name, MYSQL_DAEMON)
    logger.info(f"New process id is {new_pid}")

    # verify that mysqld instance is not the killed one
    assert new_pid != pid, "❌ PID for mysql daemon did not changed"

    # verify instance is part of the cluster
    logger.info("Check if instance back in cluster")
    assert await is_unit_in_cluster(
        ops_test, unit.name, another_unit.name
    ), " Unit not online in the cluster"


@pytest.mark.order(2)
@pytest.mark.abort_on_fail
@pytest.mark.healing_tests
async def test_freeze_db_process(ops_test: OpsTest):
    """Freeze and unfreeze process and check for auto cluster recovery."""
    app = await app_name(ops_test)
    unit = ops_test.model.applications[app].units[0]
    another_unit = ops_test.model.applications[app].units[1]

    # get running mysqld PID
    pid = await get_process_pid(ops_test, unit.name, MYSQL_DAEMON)

    # freeze (STOP signal) mysqld for the unit
    logger.info(f"Freezing process id {pid}")
    await ops_test.juju("ssh", unit.name, "sudo", "kill", "-19", pid)

    config = {
        "username": CLUSTER_ADMIN_USERNAME,
        "password": await get_system_user_password(unit, CLUSTER_ADMIN_USERNAME),
        "host": await unit.get_public_address(),
    }

    # verify that connection is not possible
    assert not is_connection_possible(config), "❌ Mysqld is not paused"

    # unfreeze (CONT signal) mysqld for the unit
    logger.info(f"Unfreezing process id {pid}")
    await ops_test.juju("ssh", unit.name, "sudo", "kill", "-18", pid)

    # verify that connection is possible
    assert is_connection_possible(config), "❌ Mysqld is not paused"

    # verify instance is part of the cluster
    logger.info("Check if instance in cluster")
    assert await is_unit_in_cluster(
        ops_test, unit.name, another_unit.name
    ), "❌ Unit not online in the cluster"


@pytest.mark.order(3)
@pytest.mark.abort_on_fail
@pytest.mark.healing_tests
async def test_network_cut(ops_test: OpsTest):
    """Completely cut and restore network."""
    app = await app_name(ops_test)
    unit = ops_test.model.applications[app].units[0]
    another_unit = ops_test.model.applications[app].units[1]

    # get unit hostname
    hostname = await unit_hostname(ops_test, unit.name)

    logger.info(f"Unit {unit.name} it's on machine {hostname} ✅")

    model_name = ops_test.model.info.name
    unit_ip = instance_ip(model_name, hostname)

    config = {
        "username": CLUSTER_ADMIN_USERNAME,
        "password": await get_system_user_password(unit, CLUSTER_ADMIN_USERNAME),
        "host": unit_ip,
    }

    # verify that connection is possible
    assert is_connection_possible(config), f"❌ Connection to host {unit_ip} is not possible"

    logger.info(f"Cutting network for {hostname}")
    cut_network_from_unit(hostname)

    # verify that connection is not possible
    assert not is_connection_possible(config), "❌ Connection is possible after network cut"

    logger.info(f"Restoring network for {hostname}")
    restore_network_for_unit(hostname)

    # wait until network is reestablished for the unit
    wait_network_restore(model_name, hostname, unit_ip)

    # update instance ip as it may change on network restore
    config["host"] = instance_ip(model_name, hostname)

    # verify that connection is possible
    assert is_connection_possible(config), "❌ Connection is not possible after network restore"

    # verify instance is part of the cluster
    logger.info("Check if instance in cluster")
    assert await is_unit_in_cluster(
        ops_test, unit.name, another_unit.name
    ), "Unit not online in the cluster"


@pytest.mark.order(4)
@pytest.mark.abort_on_fail
@pytest.mark.healing_tests
async def test_replicate_data_on_restart(ops_test: OpsTest):
    """Stop machine, write data, start and validate replication."""
    app = await app_name(ops_test)
    unit = ops_test.model.applications[app].units[0]
    another_unit = ops_test.model.applications[app].units[1]
    cluster = cluster_name(another_unit, ops_test.model.info.name)

    # get unit hostname
    hostname = await unit_hostname(ops_test, unit.name)

    model_name = ops_test.model.info.name
    unit_ip = instance_ip(model_name, hostname)

    config = {
        "username": CLUSTER_ADMIN_USERNAME,
        "password": await get_system_user_password(unit, CLUSTER_ADMIN_USERNAME),
        "host": unit_ip,
    }

    # verify that connection is possible
    assert is_connection_possible(config), f"❌ Connection to host {unit_ip} is not possible"

    logger.info(f"Stopping server on unit {unit.name}")
    await graceful_stop_server(ops_test, unit.name)

    # allow some time to the shutdown process
    sleep(10)

    # verify that connection is gone
    assert not is_connection_possible(config), f"❌ Connection to host {unit_ip} is possible"

    # get primary to write to it
    server_config_password = await get_system_user_password(unit, SERVER_CONFIG_USERNAME)
    logger.info("Get primary")
    primary_unit = await get_primary_unit(
        ops_test, another_unit, app, cluster, SERVER_CONFIG_USERNAME, server_config_password
    )

    primary_unit_hostname = await unit_hostname(ops_test, primary_unit.name)
    primary_unit_ip = instance_ip(model_name, primary_unit_hostname)

    random_chars = generate_random_string(40)
    create_records_sql = [
        "CREATE DATABASE IF NOT EXISTS test",
        "CREATE TABLE IF NOT EXISTS test.data_replication_table (id varchar(40), primary key(id))",
        f"INSERT INTO test.data_replication_table VALUES ('{random_chars}')",
    ]

    logger.info("Write to primary")
    await execute_commands_on_unit(
        primary_unit_ip,
        SERVER_CONFIG_USERNAME,
        server_config_password,
        create_records_sql,
        commit=True,
    )

    # restart server
    logger.info(f"Re starting server on unit {unit.name}")
    await start_server(ops_test, unit.name)

    # verify/wait availability
    assert is_connection_possible(config), "❌ Connection not possible after restart"

    # read and verify data
    select_data_sql = [
        f"SELECT * FROM test.data_replication_table WHERE id = '{random_chars}'",
    ]

    # allow some time for sync
    sleep(10)

    output = await execute_commands_on_unit(
        unit_ip,
        SERVER_CONFIG_USERNAME,
        server_config_password,
        select_data_sql,
    )
    assert random_chars in output, "❌ Data was not synced"
