#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.


import json
import logging
import re
import time
from pathlib import Path
from typing import Dict

import pytest
import yaml
from juju.unit import Unit
from pytest_operator.plugin import OpsTest

from tests.integration.helpers import generate_random_string, run_command_on_unit

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = METADATA["name"]
CLUSTER_NAME = "test_cluster"


@pytest.mark.order(1)
@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest):
    """Build the charm and deploy 3 units to ensure a cluster is formed."""
    # Build and deploy charm from local source folder
    charm = await ops_test.build_charm(".")
    config = {"cluster-name": CLUSTER_NAME}
    await ops_test.model.deploy(charm, application_name=APP_NAME, config=config, num_units=3)

    # Reduce the update_status frequency until the cluster is deployed
    await ops_test.model.set_config({"update-status-hook-interval": "10s"})

    await ops_test.model.wait_for_idle(
        apps=[APP_NAME],
        status="active",
        raise_on_blocked=True,
        timeout=1000,
    )
    assert len(ops_test.model.applications[APP_NAME].units) == 3

    for unit in ops_test.model.applications[APP_NAME].units:
        assert unit.workload_status == "active"

    # Effectively disable the update status from firing
    await ops_test.model.set_config({"update-status-hook-interval": "60m"})


@pytest.mark.order(2)
@pytest.mark.abort_on_fail
async def test_consistent_data_replication_across_cluster(ops_test: OpsTest):
    """Confirm that data is replicated from the primary node to all the replicas."""
    # Insert values into a table on the primary unit
    random_unit = ops_test.model.applications[APP_NAME].units[0]
    server_config_credentials = await get_server_config_credentials(random_unit)

    primary_unit = await get_primary_unit(
        ops_test,
        random_unit,
        server_config_credentials["username"],
        server_config_credentials["password"],
    )

    random_chars = generate_random_string(40)
    create_records_sql = (
        "CREATE DATABASE IF NOT EXISTS test",
        "CREATE TABLE IF NOT EXISTS test.data_replication_table (id varchar(40), primary key(id))",
        f"INSERT INTO test.data_replication_table VALUES ('{random_chars}')",
    )

    mysqlsh_sql_base_command = f"mysqlsh --sql {server_config_credentials['username']}:{server_config_credentials['password']}@127.0.0.1"

    await run_command_on_unit(
        primary_unit, f"{mysqlsh_sql_base_command} -e \"{';'.join(create_records_sql)}\""
    )

    # Allow time for the data to be replicated
    time.sleep(2)

    # Confirm that the values are available on all units
    for unit in ops_test.model.applications[APP_NAME].units:
        output = await run_command_on_unit(
            unit,
            f"{mysqlsh_sql_base_command} -e \"SELECT * FROM test.data_replication_table WHERE id = '{random_chars}'\"",
        )
        assert random_chars in output


@pytest.mark.order(3)
@pytest.mark.abort_on_fail
async def test_primary_reelection(ops_test: OpsTest):
    """Confirm that a new primary is elected when the current primary is torn down."""
    random_unit = ops_test.model.applications[APP_NAME].units[0]
    server_config_credentials = await get_server_config_credentials(random_unit)

    primary_unit = await get_primary_unit(
        ops_test,
        random_unit,
        server_config_credentials["username"],
        server_config_credentials["password"],
    )
    primary_unit_name = primary_unit.name

    assert len(ops_test.model.applications[APP_NAME].units) == 3

    # Destroy the primary unit and wait 5 seconds to ensure that the
    # juju status changed from active
    await ops_test.model.destroy_units(primary_unit.name)
    time.sleep(5)
    await ops_test.model.wait_for_idle(
        apps=[APP_NAME],
        status="active",
        raise_on_blocked=True,
        timeout=1000,
    )

    # Wait for unit to be destroyed and confirm that the new primary unit is different
    assert len(ops_test.model.applications[APP_NAME].units) == 2

    random_unit = ops_test.model.applications[APP_NAME].units[0]
    new_primary_unit = await get_primary_unit(
        ops_test,
        random_unit,
        server_config_credentials["username"],
        server_config_credentials["password"],
    )

    assert primary_unit_name != new_primary_unit.name


@pytest.mark.order(4)
@pytest.mark.abort_on_fail
async def test_cluster_preserves_data_on_delete(ops_test: OpsTest):
    """Test that data is preserved during scale up and scale down."""
    # Insert values into test table from the primary unit
    random_unit = ops_test.model.applications[APP_NAME].units[0]
    server_config_credentials = await get_server_config_credentials(random_unit)

    primary_unit = await get_primary_unit(
        ops_test,
        random_unit,
        server_config_credentials["username"],
        server_config_credentials["password"],
    )

    random_chars = generate_random_string(40)
    create_records_sql = (
        "CREATE DATABASE IF NOT EXISTS test",
        "CREATE TABLE IF NOT EXISTS test.instance_state_replication (id varchar(40), primary key(id))",
        f"INSERT INTO test.instance_state_replication VALUES ('{random_chars}')",
    )

    mysqlsh_sql_base_command = f"mysqlsh --sql {server_config_credentials['username']}:{server_config_credentials['password']}@127.0.0.1"

    await run_command_on_unit(
        primary_unit, f"{mysqlsh_sql_base_command} -e \"{';'.join(create_records_sql)}\""
    )

    assert len(ops_test.model.applications[APP_NAME].units) == 2
    old_unit_names = [unit.name for unit in ops_test.model.applications[APP_NAME].units]

    # Add a unit and wait until it is active
    await ops_test.model.applications[APP_NAME].add_unit()
    time.sleep(5)
    await ops_test.model.wait_for_idle(
        apps=[APP_NAME],
        status="active",
        raise_on_blocked=True,
        timeout=1000,
    )

    assert len(ops_test.model.applications[APP_NAME].units) == 3

    added_unit = [
        unit
        for unit in ops_test.model.applications[APP_NAME].units
        if unit.name not in old_unit_names
    ][0]

    # Ensure that all units have the above inserted data
    for unit in ops_test.model.applications[APP_NAME].units:
        output = await run_command_on_unit(
            unit,
            f"{mysqlsh_sql_base_command} -e \"SELECT * FROM test.instance_state_replication WHERE id = '{random_chars}'\"",
        )
        assert random_chars in output

    # Destroy the recently created unit and wait until the application is active
    await ops_test.model.destroy_units(added_unit.name)
    time.sleep(5)
    await ops_test.model.wait_for_idle(
        apps=[APP_NAME],
        status="active",
        raise_on_blocked=True,
        timeout=1000,
    )

    assert len(ops_test.model.applications[APP_NAME].units) == 2

    # Ensure that the data still exists in all the units
    for unit in ops_test.model.applications[APP_NAME].units:
        output = await run_command_on_unit(
            unit,
            f"{mysqlsh_sql_base_command} -e \"SELECT * FROM test.instance_state_replication WHERE id = '{random_chars}'\"",
        )
        assert random_chars in output


async def get_primary_unit(
    ops_test: OpsTest, unit: Unit, server_config_username: str, server_config_password: str
) -> str:
    """Helper to retrieve the primary unit.

    Args:
        ops_test: The ops test object passed into every test case
        unit: A unit on which to run dba.get_cluster().status() on
        server_config_username: The server config username
        server_config_password: The server config password

    Returns:
        A juju unit that is a MySQL primary
    """
    commands = [
        "mysqlsh",
        "--python",
        f"{server_config_username}:{server_config_password}@127.0.0.1",
        "-e",
        f"\"print('<CLUSTER_STATUS>' + dba.get_cluster('{CLUSTER_NAME}').status().__repr__() + '</CLUSTER_STATUS>')\"",
    ]
    raw_output = await run_command_on_unit(unit, " ".join(commands))
    if not raw_output:
        return None

    matches = re.search("<CLUSTER_STATUS>(.+)</CLUSTER_STATUS>", raw_output)
    if not matches:
        return None

    cluster_status = json.loads(matches.group(1).strip())

    primary_name = [
        label
        for label, member in cluster_status["defaultReplicaSet"]["topology"].items()
        if member["mode"] == "R/W"
    ][0].replace("-", "/")

    for unit in ops_test.model.applications[APP_NAME].units:
        if unit.name == primary_name:
            return unit

    return None


async def get_server_config_credentials(unit: Unit) -> Dict:
    """Helper to run an action to retrieve server config credentials.

    Args:
        unit: The juju unit on which to run the get-server-config-credentials action

    Returns:
        A dictionary with the server config username and password
    """
    action = await unit.run_action("get-server-config-credentials")
    result = await action.wait()

    return {
        "username": result.results["server-config-username"],
        "password": result.results["server-config-password"],
    }
