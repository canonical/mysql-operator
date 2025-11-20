#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import logging

import jubilant_backports
import pytest
from jubilant_backports import Juju

from ...helpers_ha import (
    CHARM_METADATA,
    check_keystone_users_existence,
    check_successful_keystone_migration,
    get_app_units,
    get_mysql_server_credentials,
    get_unit_ip,
    scale_app_units,
    wait_for_apps_status,
)

logger = logging.getLogger(__name__)

APP_NAME = CHARM_METADATA["name"]
CLUSTER_NAME = "test_cluster"
KEYSTONE_APP_NAME = "keystone"
KEYSTONE_MYSQLROUTER_APP_NAME = "keystone-mysql-router"
ANOTHER_KEYSTONE_APP_NAME = "another-keystone"
ANOTHER_KEYSTONE_MYSQLROUTER_APP_NAME = "another-keystone-mysql-router"
SLOW_WAIT_TIMEOUT = 45 * 60
FAST_WAIT_TIMEOUT = 30 * 60


@pytest.mark.abort_on_fail
def test_keystone_bundle_db_router(juju: Juju, charm) -> None:
    """Deploy the keystone bundle to test the 'db-router' relation."""
    config = {"cluster-name": CLUSTER_NAME, "profile": "testing"}

    juju.deploy(
        charm,
        APP_NAME,
        config=config,
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
        channel="8.0/stable",  # pin to channel as it contains a fix to https://bugs.launchpad.net/charm-mysql-router/+bug/1927981
    )

    juju.integrate(f"{KEYSTONE_APP_NAME}:shared-db", f"{KEYSTONE_MYSQLROUTER_APP_NAME}:shared-db")

    juju.wait(
        ready=wait_for_apps_status(jubilant_backports.all_active, APP_NAME),
        timeout=SLOW_WAIT_TIMEOUT,
    )
    juju.wait(
        ready=wait_for_apps_status(jubilant_backports.all_waiting, KEYSTONE_APP_NAME),
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

    # Get the server config credentials
    db_unit = get_app_units(juju, APP_NAME)[0]
    server_config_credentials = get_mysql_server_credentials(juju, db_unit)

    check_successful_keystone_migration(juju, APP_NAME, server_config_credentials)

    keystone_users = []
    for unit_name in get_app_units(juju, KEYSTONE_APP_NAME):
        unit_address = get_unit_ip(juju, KEYSTONE_APP_NAME, unit_name)

        keystone_users.append(f"keystone@{unit_address}")
        keystone_users.append(f"mysqlrouteruser@{unit_address}")

    check_keystone_users_existence(juju, APP_NAME, server_config_credentials, keystone_users, [])

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
        channel="8.0/stable",  # pin to channel as it contains a fix to https://bugs.launchpad.net/charm-mysql-router/+bug/1927981
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

    check_successful_keystone_migration(juju, APP_NAME, server_config_credentials)

    another_keystone_users = []
    for unit_name in get_app_units(juju, ANOTHER_KEYSTONE_APP_NAME):
        unit_address = get_unit_ip(juju, ANOTHER_KEYSTONE_APP_NAME, unit_name)

        another_keystone_users.append(f"keystone@{unit_address}")
        another_keystone_users.append(f"mysqlrouteruser@{unit_address}")

    check_keystone_users_existence(
        juju, APP_NAME, server_config_credentials, keystone_users + another_keystone_users, []
    )

    # Scale down the second deployment of keystone and confirm that the first deployment
    # is still active
    scale_app_units(juju, ANOTHER_KEYSTONE_APP_NAME, 0)

    juju.remove_application(ANOTHER_KEYSTONE_APP_NAME)
    juju.remove_application(ANOTHER_KEYSTONE_MYSQLROUTER_APP_NAME)

    check_keystone_users_existence(
        juju, APP_NAME, server_config_credentials, keystone_users, another_keystone_users
    )
