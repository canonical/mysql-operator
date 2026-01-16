#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import random

import jubilant_backports
import pytest
from jubilant_backports import Juju

from ...helpers_ha import (
    get_app_units,
    get_mysql_tables,
    get_mysql_users,
    get_unit_ip,
    scale_app_units,
    wait_for_app_status,
    wait_for_apps_status,
    wait_for_unit_status,
)

logger = logging.getLogger(__name__)

APP_NAME = "mysql"
CLUSTER_NAME = "test_cluster"
KEYSTONE_APP_NAME = "keystone"
KEYSTONE_MYSQLROUTER_APP_NAME = "keystone-mysql-router"
ANOTHER_KEYSTONE_APP_NAME = "another-keystone"
ANOTHER_KEYSTONE_MYSQLROUTER_APP_NAME = "another-keystone-mysql-router"
SLOW_WAIT_TIMEOUT = 45 * 60
FAST_WAIT_TIMEOUT = 30 * 60


@pytest.mark.abort_on_fail
async def test_keystone_bundle_db_router(juju: Juju, charm) -> None:
    """Deploy the keystone bundle to test the 'db-router' relation."""
    juju.deploy(
        charm,
        APP_NAME,
        config={"cluster-name": CLUSTER_NAME, "profile": "testing"},
        num_units=1,
        base="ubuntu@22.04",
    )

    # Deploy keystone
    juju.deploy(
        "keystone",
        KEYSTONE_APP_NAME,
        base="ubuntu@20.04",
        num_units=2,
        channel="yoga/stable",
    )

    # Deploy mysqlrouter and relate it to keystone
    juju.deploy(
        "mysql-router",
        KEYSTONE_MYSQLROUTER_APP_NAME,
        channel="8.0/stable",
    )

    juju.integrate(f"{KEYSTONE_APP_NAME}:shared-db", f"{KEYSTONE_MYSQLROUTER_APP_NAME}:shared-db")

    juju.wait(
        ready=wait_for_apps_status(jubilant_backports.all_active, APP_NAME),
        timeout=SLOW_WAIT_TIMEOUT,
    )
    juju.wait(
        ready=lambda status: all((
            wait_for_app_status(KEYSTONE_APP_NAME, "waiting"),
            *(
                wait_for_unit_status(KEYSTONE_APP_NAME, unit_name, "blocked")
                for unit_name in status.get_units(KEYSTONE_APP_NAME)
            ),
        )),
        timeout=SLOW_WAIT_TIMEOUT,
    )
    juju.wait(
        ready=wait_for_apps_status(jubilant_backports.all_blocked, KEYSTONE_MYSQLROUTER_APP_NAME),
        timeout=SLOW_WAIT_TIMEOUT,
    )

    juju.integrate(f"{KEYSTONE_MYSQLROUTER_APP_NAME}:db-router", f"{APP_NAME}:db-router")

    juju.wait(
        ready=wait_for_apps_status(
            jubilant_backports.all_active, KEYSTONE_APP_NAME, KEYSTONE_MYSQLROUTER_APP_NAME
        ),
        timeout=SLOW_WAIT_TIMEOUT,
    )

    mysql_units = get_app_units(juju, APP_NAME)
    random_unit = random.choice(mysql_units)

    for unit_name in mysql_units:
        unit_tables = await get_mysql_tables(juju, APP_NAME, unit_name, "keystone")
        assert len(unit_tables) > 0

    keystone_users = []
    for unit_name in get_app_units(juju, KEYSTONE_APP_NAME):
        unit_address = get_unit_ip(juju, KEYSTONE_APP_NAME, unit_name)

        keystone_users.append(f"keystone@{unit_address}")
        keystone_users.append(f"mysqlrouteruser@{unit_address}")

    db_users = await get_mysql_users(juju, APP_NAME, random_unit)
    for user in keystone_users:
        assert user in db_users

    # Deploy and test another deployment of keystone
    juju.deploy(
        "keystone",
        ANOTHER_KEYSTONE_APP_NAME,
        base="ubuntu@20.04",
        num_units=2,
        channel="yoga/stable",
    )

    # Deploy mysqlrouter and relate it to keystone
    juju.deploy(
        "mysql-router",
        ANOTHER_KEYSTONE_MYSQLROUTER_APP_NAME,
        channel="8.0/stable",
    )

    juju.integrate(
        f"{ANOTHER_KEYSTONE_APP_NAME}:shared-db",
        f"{ANOTHER_KEYSTONE_MYSQLROUTER_APP_NAME}:shared-db",
    )

    # Relate mysqlrouter to mysql
    juju.integrate(f"{ANOTHER_KEYSTONE_MYSQLROUTER_APP_NAME}:db-router", f"{APP_NAME}:db-router")

    juju.wait(
        ready=wait_for_apps_status(
            jubilant_backports.all_active,
            ANOTHER_KEYSTONE_APP_NAME,
            ANOTHER_KEYSTONE_MYSQLROUTER_APP_NAME,
        ),
        timeout=SLOW_WAIT_TIMEOUT,
    )

    for unit_name in mysql_units:
        unit_tables = await get_mysql_tables(juju, APP_NAME, unit_name, "keystone")
        assert len(unit_tables) > 0

    another_keystone_users = []
    for unit_name in get_app_units(juju, ANOTHER_KEYSTONE_APP_NAME):
        unit_address = get_unit_ip(juju, ANOTHER_KEYSTONE_APP_NAME, unit_name)

        another_keystone_users.append(f"keystone@{unit_address}")
        another_keystone_users.append(f"mysqlrouteruser@{unit_address}")

    db_users = await get_mysql_users(juju, APP_NAME, random_unit)
    for user in keystone_users + another_keystone_users:
        assert user in db_users

    # Scale down the second deployment of keystone and confirm that the first deployment
    # is still active
    scale_app_units(juju, ANOTHER_KEYSTONE_APP_NAME, 0)

    juju.remove_application(ANOTHER_KEYSTONE_APP_NAME)
    juju.remove_application(ANOTHER_KEYSTONE_MYSQLROUTER_APP_NAME)

    db_users = await get_mysql_users(juju, APP_NAME, random_unit)
    for user in keystone_users:
        assert user in db_users
    for user in another_keystone_users:
        assert user not in db_users
