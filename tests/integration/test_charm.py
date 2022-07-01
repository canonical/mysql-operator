#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.


import logging
import time
from pathlib import Path

import pytest
import yaml
from pytest_operator.plugin import OpsTest

from tests.integration.helpers import (
    execute_commands_on_unit,
    generate_random_string,
    get_primary_unit,
    get_server_config_credentials,
    scale_application,
)

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = METADATA["name"]
CLUSTER_NAME = "test_cluster"


@pytest.mark.order(1)
@pytest.mark.abort_on_fail
@pytest.mark.ha_tests
async def test_build_and_deploy(ops_test: OpsTest) -> None:
    """Build the charm and deploy 3 units to ensure a cluster is formed."""
    # Build and deploy charm from local source folder
    charm = await ops_test.build_charm(".")
    config = {"cluster-name": CLUSTER_NAME}
    await ops_test.model.deploy(charm, application_name=APP_NAME, config=config, num_units=3)

    # Reduce the update_status frequency until the cluster is deployed
    await ops_test.model.set_config({"update-status-hook-interval": "10s"})

    await ops_test.model.block_until(lambda: len(ops_test.model.applications[APP_NAME].units) == 3)
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
@pytest.mark.ha_tests
async def test_consistent_data_replication_across_cluster(ops_test: OpsTest) -> None:
    """Confirm that data is replicated from the primary node to all the replicas."""
    # Insert values into a table on the primary unit
    random_unit = ops_test.model.applications[APP_NAME].units[0]
    server_config_credentials = await get_server_config_credentials(random_unit)

    primary_unit = await get_primary_unit(
        ops_test,
        random_unit,
        APP_NAME,
        CLUSTER_NAME,
        server_config_credentials["username"],
        server_config_credentials["password"],
    )
    primary_unit_address = await primary_unit.get_public_address()

    random_chars = generate_random_string(40)
    create_records_sql = [
        "CREATE DATABASE IF NOT EXISTS test",
        "CREATE TABLE IF NOT EXISTS test.data_replication_table (id varchar(40), primary key(id))",
        f"INSERT INTO test.data_replication_table VALUES ('{random_chars}')",
    ]

    await execute_commands_on_unit(
        primary_unit_address,
        server_config_credentials["username"],
        server_config_credentials["password"],
        create_records_sql,
        commit=True,
    )

    # Allow time for the data to be replicated
    time.sleep(2)

    select_data_sql = [
        f"SELECT * FROM test.data_replication_table WHERE id = '{random_chars}'",
    ]

    # Confirm that the values are available on all units
    for unit in ops_test.model.applications[APP_NAME].units:
        unit_address = await unit.get_public_address()

        output = await execute_commands_on_unit(
            unit_address,
            server_config_credentials["username"],
            server_config_credentials["password"],
            select_data_sql,
        )
        assert random_chars in output


@pytest.mark.order(3)
@pytest.mark.abort_on_fail
@pytest.mark.ha_tests
async def test_primary_reelection(ops_test: OpsTest) -> None:
    """Confirm that a new primary is elected when the current primary is torn down."""
    await ops_test.model.set_config({"update-status-hook-interval": "10s"})

    application = ops_test.model.applications[APP_NAME]

    random_unit = application.units[0]
    server_config_credentials = await get_server_config_credentials(random_unit)

    primary_unit = await get_primary_unit(
        ops_test,
        random_unit,
        APP_NAME,
        CLUSTER_NAME,
        server_config_credentials["username"],
        server_config_credentials["password"],
    )
    primary_unit_name = primary_unit.name

    # Destroy the primary unit and wait 5 seconds to ensure that the
    # juju status changed from active
    await ops_test.model.destroy_units(primary_unit.name)

    await ops_test.model.block_until(lambda: len(application.units) == 2)
    await ops_test.model.wait_for_idle(
        apps=[APP_NAME],
        status="active",
        raise_on_blocked=True,
        timeout=1000,
    )

    # Wait for unit to be destroyed and confirm that the new primary unit is different
    random_unit = application.units[0]
    new_primary_unit = await get_primary_unit(
        ops_test,
        random_unit,
        APP_NAME,
        CLUSTER_NAME,
        server_config_credentials["username"],
        server_config_credentials["password"],
    )

    assert primary_unit_name != new_primary_unit.name

    # Add the unit back and wait until it is active
    await scale_application(ops_test, APP_NAME, 3)


@pytest.mark.order(4)
@pytest.mark.abort_on_fail
@pytest.mark.ha_tests
async def test_cluster_preserves_data_on_delete(ops_test: OpsTest) -> None:
    """Test that data is preserved during scale up and scale down."""
    # Insert values into test table from the primary unit
    application = ops_test.model.applications[APP_NAME]

    random_unit = application.units[0]
    server_config_credentials = await get_server_config_credentials(random_unit)

    primary_unit = await get_primary_unit(
        ops_test,
        random_unit,
        APP_NAME,
        CLUSTER_NAME,
        server_config_credentials["username"],
        server_config_credentials["password"],
    )
    primary_unit_address = await primary_unit.get_public_address()

    random_chars = generate_random_string(40)
    create_records_sql = [
        "CREATE DATABASE IF NOT EXISTS test",
        "CREATE TABLE IF NOT EXISTS test.instance_state_replication (id varchar(40), primary key(id))",
        f"INSERT INTO test.instance_state_replication VALUES ('{random_chars}')",
    ]

    await execute_commands_on_unit(
        primary_unit_address,
        server_config_credentials["username"],
        server_config_credentials["password"],
        create_records_sql,
        commit=True,
    )

    old_unit_names = [unit.name for unit in ops_test.model.applications[APP_NAME].units]

    # Add a unit and wait until it is active
    await scale_application(ops_test, APP_NAME, 4)

    added_unit = [unit for unit in application.units if unit.name not in old_unit_names][0]

    # Ensure that all units have the above inserted data
    select_data_sql = [
        f"SELECT * FROM test.instance_state_replication WHERE id = '{random_chars}'",
    ]

    for unit in application.units:
        unit_address = await unit.get_public_address()
        output = await execute_commands_on_unit(
            unit_address,
            server_config_credentials["username"],
            server_config_credentials["password"],
            select_data_sql,
        )
        assert random_chars in output

    # Destroy the recently created unit and wait until the application is active
    await ops_test.model.destroy_units(added_unit.name)

    await ops_test.model.block_until(lambda: len(ops_test.model.applications[APP_NAME].units) == 3)
    await ops_test.model.wait_for_idle(
        apps=[APP_NAME],
        status="active",
        raise_on_blocked=True,
        timeout=1000,
    )

    # Ensure that the data still exists in all the units
    for unit in application.units:
        unit_address = await unit.get_public_address()
        output = await execute_commands_on_unit(
            unit_address,
            server_config_credentials["username"],
            server_config_credentials["password"],
            select_data_sql,
        )
        assert random_chars in output

    await ops_test.model.set_config({"update-status-hook-interval": "60m"})
