#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import logging
from pathlib import Path
from typing import Dict, List

import pytest
import yaml
from pytest_operator.plugin import OpsTest

from tests.integration.helpers import (
    execute_commands_on_unit,
    get_server_config_credentials,
    scale_application,
)

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = METADATA["name"]
CLUSTER_NAME = "test_cluster"
KEYSTONE_APP_NAME = "keystone"
KEYSTONE_MYSQLROUTER_APP_NAME = "keystone-mysql-router"
ANOTHER_KEYSTONE_APP_NAME = "another-keystone"
ANOTHER_KEYSTONE_MYSQLROUTER_APP_NAME = "another-keystone-mysql-router"
SLOW_WAIT_TIMEOUT = 45 * 60
FAST_WAIT_TIMEOUT = 30 * 60


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
        assert "keystone" in output, "keystone database not found in mysql"

        # Ensure that keystone tables exist in the 'keystone' database
        output = await execute_commands_on_unit(
            unit_address,
            server_config_credentials["username"],
            server_config_credentials["password"],
            get_count_keystone_tables_sql,
        )
        assert output[0] > 0, "No keystone tables found in the 'keystone' database"


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
        assert user in output, "User(s) that should exist are not in the database"

    # Assert users that should not exist
    for user in users_that_should_not_exist:
        assert user not in output, "User(s) that should not exist are in the database"


@pytest.mark.order(1)
@pytest.mark.abort_on_fail
@pytest.mark.db_router_tests
async def test_keystone_bundle_db_router(ops_test: OpsTest) -> None:
    """Deploy the keystone bundle to test the 'db-router' relation.

    Args:
        ops_test: The ops test framework
    """
    charm = await ops_test.build_charm(".")
    config = {"cluster-name": CLUSTER_NAME}

    mysql_app = await ops_test.model.deploy(
        charm, application_name=APP_NAME, config=config, num_units=1
    )

    # Deploy keystone
    # Explicitly setting the series to 'focal' as it defaults to 'xenial'
    keystone_app = await ops_test.model.deploy(
        "keystone",
        series="focal",
        application_name=KEYSTONE_APP_NAME,
        num_units=2,
    )

    # Deploy mysqlrouter and relate it to keystone
    keystone_mysqlrouter_app = await ops_test.model.deploy(
        "mysql-router",
        channel="8.0/stable",  # pin to channel as it contains a fix to https://bugs.launchpad.net/charm-mysql-router/+bug/1927981
        application_name=KEYSTONE_MYSQLROUTER_APP_NAME,
    )

    await ops_test.model.relate(
        f"{KEYSTONE_APP_NAME}:shared-db",
        f"{KEYSTONE_MYSQLROUTER_APP_NAME}:shared-db",
    )

    # Reduce the update_status frequency for the duration of the test
    async with ops_test.fast_forward():

        await asyncio.gather(
            ops_test.model.block_until(
                lambda: mysql_app.status in ("active", "error"), timeout=SLOW_WAIT_TIMEOUT
            ),
            ops_test.model.block_until(
                lambda: keystone_app.status in ("waiting", "error"), timeout=SLOW_WAIT_TIMEOUT
            ),
            ops_test.model.block_until(
                lambda: keystone_mysqlrouter_app.status in ("blocked", "error"),
                timeout=SLOW_WAIT_TIMEOUT,
            ),
        )
        assert (
            mysql_app.status == "active"
            and keystone_app.status == "waiting"
            and keystone_mysqlrouter_app.status == "blocked"
        )

        # Relate mysqlrouter to mysql
        await ops_test.model.relate(
            f"{KEYSTONE_MYSQLROUTER_APP_NAME}:db-router", f"{APP_NAME}:db-router"
        )
        await ops_test.model.block_until(
            lambda: keystone_app.status in ("active", "error")
            and keystone_mysqlrouter_app.status in ("active", "error"),
            timeout=SLOW_WAIT_TIMEOUT,
        )
        assert keystone_app.status == "active" and keystone_mysqlrouter_app.status == "active"

        # Get the server config credentials
        db_unit = ops_test.model.applications[APP_NAME].units[0]
        server_config_credentials = await get_server_config_credentials(db_unit)

        await check_successful_keystone_migration(ops_test, server_config_credentials)

        keystone_users = []
        for unit in ops_test.model.applications[KEYSTONE_APP_NAME].units:
            unit_address = await unit.get_public_address()

            keystone_users.append(f"keystone@{unit_address}")
            keystone_users.append(f"mysqlrouteruser@{unit_address}")

        await check_keystone_users_existence(
            ops_test, server_config_credentials, keystone_users, []
        )

        # Deploy and test another deployment of keystone
        # Deploy keystone
        # Explicitly setting the series to 'focal' as it defaults to 'xenial'
        another_keystone_app = await ops_test.model.deploy(
            "keystone",
            series="focal",
            application_name=ANOTHER_KEYSTONE_APP_NAME,
            num_units=2,
        )

        # Deploy mysqlrouter and relate it to keystone
        another_keystone_mysqlrouter_app = await ops_test.model.deploy(
            "mysql-router",
            channel="8.0/stable",  # pin to channel as it contains a fix to https://bugs.launchpad.net/charm-mysql-router/+bug/1927981
            application_name=ANOTHER_KEYSTONE_MYSQLROUTER_APP_NAME,
        )

        await ops_test.model.relate(
            f"{ANOTHER_KEYSTONE_APP_NAME}:shared-db",
            f"{ANOTHER_KEYSTONE_MYSQLROUTER_APP_NAME}:shared-db",
        )

        # Relate mysqlrouter to mysql
        await ops_test.model.relate(
            f"{ANOTHER_KEYSTONE_MYSQLROUTER_APP_NAME}:db-router", f"{APP_NAME}:db-router"
        )
        await ops_test.model.block_until(
            lambda: another_keystone_app.status in ("active", "error")
            and another_keystone_mysqlrouter_app.status in ("active", "error"),
            timeout=SLOW_WAIT_TIMEOUT,
        )
        assert (
            another_keystone_app.status == "active"
            and another_keystone_mysqlrouter_app.status == "active"
        )

        await check_successful_keystone_migration(ops_test, server_config_credentials)

        another_keystone_users = []
        for unit in ops_test.model.applications[ANOTHER_KEYSTONE_APP_NAME].units:
            unit_address = await unit.get_public_address()

            another_keystone_users.append(f"keystone@{unit_address}")
            another_keystone_users.append(f"mysqlrouteruser@{unit_address}")

        await check_keystone_users_existence(
            ops_test, server_config_credentials, keystone_users + another_keystone_users, []
        )

        # Scale down the second deployment of keystone and confirm that the first deployment
        # is still active
        await scale_application(ops_test, ANOTHER_KEYSTONE_APP_NAME, 0)

        await asyncio.gather(
            ops_test.model.remove_application(ANOTHER_KEYSTONE_APP_NAME, block_until_done=True),
            ops_test.model.remove_application(
                ANOTHER_KEYSTONE_MYSQLROUTER_APP_NAME, block_until_done=True
            ),
        )

        await check_keystone_users_existence(
            ops_test, server_config_credentials, keystone_users, another_keystone_users
        )
