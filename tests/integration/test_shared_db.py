#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from pathlib import Path
from typing import Dict, List

import pytest
import yaml
from pytest_operator.plugin import OpsTest

from tests.integration.helpers import (
    execute_commands_on_unit,
    get_primary_unit,
    get_server_config_credentials,
    scale_application,
)

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = METADATA["name"]
CLUSTER_NAME = "test_cluster"
KEYSTONE_APP_NAME = "keystone"
ANOTHER_KEYSTONE_APP_NAME = "another-keystone"


async def deploy_and_relate_keystone_with_mysql(
    ops_test: OpsTest,
    keystone_application_name: str,
    number_of_units: int,
) -> None:
    """Helper function to deploy and relate keystone with mysql.

    Args:
        ops_test: The ops test framework
        keystone_application_name: The name of the keystone application to deploy
        number_of_units: The number of keystone units to deploy
    """
    # Deploy keystone
    # Explicitly setting the series to 'focal' as it defaults to 'xenial'
    await ops_test.model.deploy(
        "keystone",
        series="focal",
        application_name=keystone_application_name,
        num_units=number_of_units,
    )
    await ops_test.model.wait_for_idle(
        apps=[keystone_application_name],
        status="blocked",
        raise_on_blocked=False,
        timeout=1000,
    )

    # Relate keystone to mysql
    await ops_test.model.relate(f"{keystone_application_name}:shared-db", f"{APP_NAME}:shared-db")
    await ops_test.model.wait_for_idle(
        apps=[keystone_application_name],
        status="active",
        raise_on_blocked=False,  # both applications are blocked initially
        timeout=1000,
    )


async def check_successful_keystone_migration(
    ops_test: OpsTest, server_config_credentials: Dict
) -> None:
    """Checks that the keystone application is successfully migrated in mysql.

    Args:
        ops_test: The ops test framework
        server_config_credentials: The credentials for the server config user
    """
    show_tables_sql = [
        "SHOW DATABASES",
    ]
    get_count_keystone_tables_sql = [
        "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'keystone'",
    ]

    for unit in ops_test.model.applications[APP_NAME].units:
        unit_address = await unit.get_public_address()

        # Ensure 'keystone' database exists in mysql
        output = await execute_commands_on_unit(
            unit_address,
            server_config_credentials["username"],
            server_config_credentials["password"],
            show_tables_sql,
        )
        assert "keystone" in output

        # Ensure that keystone tables exist in the 'keystone' database
        output = await execute_commands_on_unit(
            unit_address,
            server_config_credentials["username"],
            server_config_credentials["password"],
            get_count_keystone_tables_sql,
        )
        assert output[0] > 0


async def check_keystone_users_existence(
    ops_test: OpsTest,
    server_config_credentials: Dict[str, str],
    users_that_should_exist: List[str],
    users_that_should_not_exist: List[str],
) -> None:
    """Checks that keystone users exist in the database.

    Args:
        ops_test: The ops test framework
        server_config_credentials: The credentials for the server config user
        users_that_should_exist: List of users that should exist in the database
        users_that_should_not_exist: List of users that should not exist in the database
    """
    random_unit = ops_test.model.applications[APP_NAME].units[0]
    server_config_credentials = await get_server_config_credentials(random_unit)

    select_users_sql = [
        "SELECT CONCAT(user, '@', host) FROM mysql.user",
    ]

    unit = ops_test.model.applications[APP_NAME].units[0]
    unit_address = await unit.get_public_address()

    # Retrieve all users in the database
    output = await execute_commands_on_unit(
        unit_address,
        server_config_credentials["username"],
        server_config_credentials["password"],
        select_users_sql,
    )

    # Assert users that should exist
    for user in users_that_should_exist:
        assert user in output

    # Assert users that should not exist
    for user in users_that_should_not_exist:
        assert user not in output


@pytest.mark.order(100)
@pytest.mark.abort_on_fail
async def test_keystone_bundle(ops_test: OpsTest) -> None:
    """Deploy the keystone bundle to test the 'shared-db' relation.

    Args:
        ops_test: The ops test framework
    """
    # Build and deploy the mysql charm
    charm = await ops_test.build_charm(".")
    config = {"cluster-name": CLUSTER_NAME}
    await ops_test.model.deploy(charm, application_name=APP_NAME, config=config, num_units=3)

    # Reduce the update_status frequency until the keystone charm is deployed
    await ops_test.model.set_config({"update-status-hook-interval": "10s"})

    # Wait until the mysql charm is successfully deployed
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

    # Get the server config credentials
    random_unit = ops_test.model.applications[APP_NAME].units[0]
    server_config_credentials = await get_server_config_credentials(random_unit)

    # Deploy and test the first deployment of keystone
    await deploy_and_relate_keystone_with_mysql(ops_test, KEYSTONE_APP_NAME, 2)
    await check_successful_keystone_migration(ops_test, server_config_credentials)

    keystone_users = []
    for unit in ops_test.model.applications[KEYSTONE_APP_NAME].units:
        unit_address = await unit.get_public_address()

        keystone_users.append(f"keystone@{unit_address}")

    await check_keystone_users_existence(ops_test, server_config_credentials, keystone_users, [])

    # Deploy and test another deployment of keystone
    await deploy_and_relate_keystone_with_mysql(ops_test, ANOTHER_KEYSTONE_APP_NAME, 2)
    await check_successful_keystone_migration(ops_test, server_config_credentials)

    another_keystone_users = []
    for unit in ops_test.model.applications[ANOTHER_KEYSTONE_APP_NAME].units:
        unit_address = await unit.get_public_address()

        another_keystone_users.append(f"keystone@{unit_address}")

    await check_keystone_users_existence(
        ops_test, server_config_credentials, keystone_users + another_keystone_users, []
    )

    # Scale down the second deployment of keystone and confirm that the first deployment
    # is still active
    await scale_application(ops_test, ANOTHER_KEYSTONE_APP_NAME, 0)
    await ops_test.model.remove_application(ANOTHER_KEYSTONE_APP_NAME, block_until_done=True)

    await check_keystone_users_existence(
        ops_test, server_config_credentials, keystone_users, another_keystone_users
    )

    # Scale down the primary unit of mysql
    primary_unit = await get_primary_unit(
        ops_test,
        random_unit,
        APP_NAME,
        CLUSTER_NAME,
        server_config_credentials["username"],
        server_config_credentials["password"],
    )
    primary_unit_name = primary_unit.name

    await ops_test.model.destroy_units(primary_unit_name)

    await ops_test.model.block_until(lambda: len(ops_test.model.applications[APP_NAME].units) == 2)
    await ops_test.model.wait_for_idle(
        apps=[APP_NAME],
        status="active",
        raise_on_blocked=True,
        timeout=1000,
    )

    await check_keystone_users_existence(
        ops_test, server_config_credentials, keystone_users, another_keystone_users
    )

    # Scale mysql back up to 3 units
    await scale_application(ops_test, APP_NAME, 3)

    # Scale down the first deployment of keystone
    await scale_application(ops_test, KEYSTONE_APP_NAME, 0)
    await ops_test.model.remove_application(KEYSTONE_APP_NAME, block_until_done=True)

    # Scale down the mysql application
    await scale_application(ops_test, APP_NAME, 0)
    await ops_test.model.remove_application(APP_NAME, block_until_done=True)

    # Effectively disable the update status from firing
    await ops_test.model.set_config({"update-status-hook-interval": "60m"})
