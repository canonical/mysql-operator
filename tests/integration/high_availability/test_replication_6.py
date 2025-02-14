# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.


import logging
from pathlib import Path

import yaml
from pytest_operator.plugin import OpsTest

from ..helpers import (
    execute_queries_on_unit,
    get_primary_unit,
    get_server_config_credentials,
)
from .high_availability_helpers import (
    get_application_name,
)

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = METADATA["name"]
ANOTHER_APP_NAME = f"second{APP_NAME}"
TIMEOUT = 17 * 60


async def test_cluster_isolation(ops_test: OpsTest, charm, highly_available_cluster) -> None:
    """Test for cluster data isolation.

    This test creates a new cluster, create a new table on both cluster, write a single record with
    the application name for each cluster, retrieve and compare these records, asserting they are
    not the same.
    """
    app = get_application_name(ops_test, "mysql")
    apps = [app, ANOTHER_APP_NAME]

    await ops_test.model.deploy(
        charm,
        application_name=ANOTHER_APP_NAME,
        num_units=1,
        base="ubuntu@22.04",
    )
    async with ops_test.fast_forward("60s"):
        await ops_test.model.block_until(
            lambda: len(ops_test.model.applications[ANOTHER_APP_NAME].units) == 1
        )
        await ops_test.model.wait_for_idle(
            apps=[ANOTHER_APP_NAME],
            status="active",
            raise_on_blocked=True,
            timeout=TIMEOUT,
        )

    # retrieve connection data for each cluster
    connection_data = {}
    for application in apps:
        random_unit = ops_test.model.applications[application].units[0]
        server_config_credentials = await get_server_config_credentials(random_unit)
        primary_unit = await get_primary_unit(ops_test, random_unit, application)

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

        await execute_queries_on_unit(
            connection_data[application]["host"],
            connection_data[application]["username"],
            connection_data[application]["password"],
            create_records_sql,
            commit=True,
        )

    result = []
    # read single record from each cluster
    for application in apps:
        read_records_sql = ["SELECT id FROM test.cluster_isolation_table"]

        output = await execute_queries_on_unit(
            connection_data[application]["host"],
            connection_data[application]["username"],
            connection_data[application]["password"],
            read_records_sql,
            commit=False,
        )

        assert len(output) == 1, "Just one record must exist on the test table"
        result.append(output[0])

    assert result[0] != result[1], "Writes from one cluster are replicated to another cluster."
