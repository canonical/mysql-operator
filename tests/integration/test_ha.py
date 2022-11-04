#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.


import logging
import subprocess
import time
from pathlib import Path

import pytest
import yaml
from pytest_operator.plugin import OpsTest

from tests.integration.helpers import (
    app_name,
    cluster_name,
    execute_commands_on_unit,
    generate_random_string,
    get_primary_unit,
    get_server_config_credentials,
    scale_application,
)
from tests.integration.integration_constants import SERIES_TO_VERSION

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = METADATA["name"]
ANOTHER_APP_NAME = f"second{APP_NAME}"


@pytest.mark.order(1)
@pytest.mark.abort_on_fail
@pytest.mark.ha_tests
async def test_build_and_deploy(ops_test: OpsTest, series: str) -> None:
    """Build the charm and deploy 3 units to ensure a cluster is formed."""
    if app := await app_name(ops_test):
        if len(ops_test.model.applications[app].units) == 3:
            return
        else:
            async with ops_test.fast_forward():
                await scale_application(ops_test, app, 3)
            return

    # Build and deploy charm from local source folder
    # Manually call charmcraft pack because ops_test.build_charm() does not support
    # multiple bases in the charmcraft file
    charmcraft_pack_commands = ["sg", "lxd", "-c", "charmcraft pack"]
    subprocess.check_output(charmcraft_pack_commands)
    charm_url = f"local:mysql_ubuntu-{SERIES_TO_VERSION[series]}-amd64.charm"

    await ops_test.model.deploy(
        charm_url,
        application_name=APP_NAME,
        num_units=3,
        series=series,
    )
    # variable used to avoid rebuilding the charm
    global another_charm_url
    another_charm_url = charm_url

    # Reduce the update_status frequency until the cluster is deployed
    async with ops_test.fast_forward():

        await ops_test.model.block_until(
            lambda: len(ops_test.model.applications[APP_NAME].units) == 3
        )
        await ops_test.model.wait_for_idle(
            apps=[APP_NAME],
            status="active",
            raise_on_blocked=True,
            timeout=1000,
        )
        assert len(ops_test.model.applications[APP_NAME].units) == 3

        for unit in ops_test.model.applications[APP_NAME].units:
            assert unit.workload_status == "active"


@pytest.mark.order(2)
@pytest.mark.abort_on_fail
@pytest.mark.ha_tests
async def test_consistent_data_replication_across_cluster(
    ops_test: OpsTest,
) -> None:
    """Confirm that data is replicated from the primary node to all the replicas."""
    # Insert values into a table on the primary unit
    app = await app_name(ops_test)
    random_unit = ops_test.model.applications[app].units[0]
    cluster = cluster_name(random_unit, ops_test.model.info.name)
    server_config_credentials = await get_server_config_credentials(random_unit)

    primary_unit = await get_primary_unit(
        ops_test,
        random_unit,
        app,
        cluster,
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
    for unit in ops_test.model.applications[app].units:
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
    app = await app_name(ops_test)

    application = ops_test.model.applications[app]

    random_unit = application.units[0]
    cluster = cluster_name(random_unit, ops_test.model.info.name)
    server_config_credentials = await get_server_config_credentials(random_unit)

    primary_unit = await get_primary_unit(
        ops_test,
        random_unit,
        app,
        cluster,
        server_config_credentials["username"],
        server_config_credentials["password"],
    )
    primary_unit_name = primary_unit.name

    # Destroy the primary unit and wait 5 seconds to ensure that the
    # juju status changed from active
    await ops_test.model.destroy_units(primary_unit.name)

    async with ops_test.fast_forward():
        await ops_test.model.block_until(lambda: len(application.units) == 2)
        await ops_test.model.wait_for_idle(
            apps=[app],
            status="active",
            raise_on_blocked=True,
            timeout=1000,
        )

    # Wait for unit to be destroyed and confirm that the new primary unit is different
    random_unit = application.units[0]
    new_primary_unit = await get_primary_unit(
        ops_test,
        random_unit,
        app,
        cluster,
        server_config_credentials["username"],
        server_config_credentials["password"],
    )

    assert primary_unit_name != new_primary_unit.name

    # Add the unit back and wait until it is active
    async with ops_test.fast_forward():
        await scale_application(ops_test, app, 3)


@pytest.mark.order(4)
@pytest.mark.abort_on_fail
@pytest.mark.ha_tests
async def test_cluster_preserves_data_on_delete(ops_test: OpsTest) -> None:
    """Test that data is preserved during scale up and scale down."""
    # Insert values into test table from the primary unit
    app = await app_name(ops_test)
    application = ops_test.model.applications[app]

    random_unit = application.units[0]
    cluster = cluster_name(random_unit, ops_test.model.info.name)
    server_config_credentials = await get_server_config_credentials(random_unit)

    primary_unit = await get_primary_unit(
        ops_test,
        random_unit,
        app,
        cluster,
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

    old_unit_names = [unit.name for unit in ops_test.model.applications[app].units]

    # Add a unit and wait until it is active
    async with ops_test.fast_forward():
        await scale_application(ops_test, app, 4)

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
    async with ops_test.fast_forward():
        await ops_test.model.block_until(lambda: len(ops_test.model.applications[app].units) == 3)
        await ops_test.model.wait_for_idle(
            apps=[app],
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


@pytest.mark.order(5)
@pytest.mark.ha_tests
async def test_cluster_isolation(ops_test: OpsTest, series: str) -> None:
    """Test for cluster data isolation.

    This test creates a new cluster, create a new table on both cluster, write a single record with
    the application name for each cluster, retrieve and compare these records, asserting they are
    not the same.
    """
    app = await app_name(ops_test)
    apps = [app, ANOTHER_APP_NAME]

    # Build and deploy secondary charm
    charm_url = another_charm_url
    if not charm_url:
        # Manually call charmcraft pack because ops_test.build_charm() does not support
        # multiple bases in the charmcraft file
        charmcraft_pack_commands = ["sg", "lxd", "-c", "charmcraft pack"]
        subprocess.check_output(charmcraft_pack_commands)
        charm_url = f"local:mysql_ubuntu-{SERIES_TO_VERSION[series]}-amd64.charm"

    await ops_test.model.deploy(
        charm_url,
        application_name=ANOTHER_APP_NAME,
        num_units=1,
        series=series,
    )
    async with ops_test.fast_forward():
        await ops_test.model.block_until(
            lambda: len(ops_test.model.applications[ANOTHER_APP_NAME].units) == 1
        )
        await ops_test.model.wait_for_idle(
            apps=[ANOTHER_APP_NAME],
            status="active",
            raise_on_blocked=True,
            timeout=1000,
        )

    # retrieve connection data for each cluster
    connection_data = dict()
    for application in apps:
        random_unit = ops_test.model.applications[application].units[0]
        cluster = cluster_name(random_unit, ops_test.model.info.name)
        server_config_credentials = await get_server_config_credentials(random_unit)
        primary_unit = await get_primary_unit(
            ops_test,
            random_unit,
            application,
            cluster,
            server_config_credentials["username"],
            server_config_credentials["password"],
        )

        primary_unit_address = await primary_unit.get_public_address()

        connection_data[application] = {
            "host": primary_unit_address,
            "username": server_config_credentials["username"],
            "password": server_config_credentials["password"],
        }

    # write single distinct record to each cluster
    for application in apps:
        create_records_sql = [
            "CREATE DATABASE IF NOT EXISTS test",
            "DROP TABLE IF EXISTS test.cluster_isolation_table",
            "CREATE TABLE test.cluster_isolation_table (id varchar(40), primary key(id))",
            f"INSERT INTO test.cluster_isolation_table VALUES ('{application}')",
        ]

        await execute_commands_on_unit(
            connection_data[application]["host"],
            connection_data[application]["username"],
            connection_data[application]["password"],
            create_records_sql,
            commit=True,
        )

    result = list()
    # read single record from each cluster
    for application in apps:
        read_records_sql = ["SELECT id FROM test.cluster_isolation_table"]

        output = await execute_commands_on_unit(
            connection_data[application]["host"],
            connection_data[application]["username"],
            connection_data[application]["password"],
            read_records_sql,
            commit=False,
        )

        assert len(output) == 1, "Just one record must exist on the test table"
        result.append(output[0])

    assert result[0] != result[1], "Writes from one cluster are replicated to another cluster."
