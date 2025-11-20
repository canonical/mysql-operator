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
    get_mysql_primary_unit,
    get_mysql_server_credentials,
    get_unit_ip,
    scale_app_units,
    wait_for_apps_status,
)

logger = logging.getLogger(__name__)

APP_NAME = CHARM_METADATA["name"]
CLUSTER_NAME = "test_cluster"
KEYSTONE_APP_NAME = "keystone"
ANOTHER_KEYSTONE_APP_NAME = "another-keystone"
SLOW_WAIT_TIMEOUT = 25 * 60
FAST_WAIT_TIMEOUT = 15 * 60


def deploy_and_relate_keystone_with_mysql(
    juju: Juju,
    keystone_application_name: str,
    number_of_units: int,
) -> None:
    """Helper function to deploy and relate keystone with mysql.

    Args:
        juju: The Juju instance
        keystone_application_name: The name of the keystone application to deploy
        number_of_units: The number of keystone units to deploy
    """
    # Deploy keystone
    logger.info("Deploy keystone..")
    juju.deploy(
        "keystone",
        keystone_application_name,
        channel="yoga/stable",
        base="ubuntu@22.04",
        num_units=number_of_units,
    )

    juju.wait(
        ready=wait_for_apps_status(jubilant_backports.all_blocked, keystone_application_name),
        timeout=SLOW_WAIT_TIMEOUT,
    )

    # Relate keystone to mysql
    logger.info("Relate keystone and mysql")
    juju.integrate(f"{keystone_application_name}:shared-db", f"{APP_NAME}:shared-db")
    logger.info("Wait keystone settle after relation")
    juju.wait(
        ready=wait_for_apps_status(jubilant_backports.all_active, keystone_application_name),
        timeout=SLOW_WAIT_TIMEOUT,
    )


@pytest.mark.abort_on_fail
def test_keystone_bundle_shared_db(juju: Juju, charm) -> None:
    """Deploy the keystone bundle to test the 'shared-db' relation.

    Args:
        juju: The Juju instance
    """
    config = {"cluster-name": CLUSTER_NAME, "profile": "testing"}
    juju.deploy(
        charm,
        APP_NAME,
        config=config,
        num_units=3,
        base="ubuntu@22.04",
    )

    # Wait until the mysql charm is successfully deployed
    juju.wait(
        ready=wait_for_apps_status(jubilant_backports.all_active, APP_NAME),
        error=jubilant_backports.any_blocked,
        timeout=FAST_WAIT_TIMEOUT,
    )
    assert len(get_app_units(juju, APP_NAME)) == 3

    # Get the server config credentials
    random_unit = get_app_units(juju, APP_NAME)[0]
    server_config_credentials = get_mysql_server_credentials(juju, random_unit)

    # Deploy and test the first deployment of keystone
    deploy_and_relate_keystone_with_mysql(juju, KEYSTONE_APP_NAME, 2)
    check_successful_keystone_migration(juju, APP_NAME, server_config_credentials)

    keystone_users = []
    for unit_name in get_app_units(juju, KEYSTONE_APP_NAME):
        unit_address = get_unit_ip(juju, KEYSTONE_APP_NAME, unit_name)

        keystone_users.append(f"keystone@{unit_address}")

    check_keystone_users_existence(juju, APP_NAME, server_config_credentials, keystone_users, [])

    # Deploy and test another deployment of keystone
    deploy_and_relate_keystone_with_mysql(juju, ANOTHER_KEYSTONE_APP_NAME, 2)
    check_successful_keystone_migration(juju, APP_NAME, server_config_credentials)

    another_keystone_users = []
    for unit_name in get_app_units(juju, ANOTHER_KEYSTONE_APP_NAME):
        unit_address = get_unit_ip(juju, ANOTHER_KEYSTONE_APP_NAME, unit_name)

        another_keystone_users.append(f"keystone@{unit_address}")

    check_keystone_users_existence(
        juju, APP_NAME, server_config_credentials, keystone_users + another_keystone_users, []
    )

    # Scale down the second deployment of keystone and confirm that the first deployment
    # is still active
    scale_app_units(juju, ANOTHER_KEYSTONE_APP_NAME, 0)
    juju.remove_application(ANOTHER_KEYSTONE_APP_NAME)

    check_keystone_users_existence(
        juju, APP_NAME, server_config_credentials, keystone_users, another_keystone_users
    )

    # Scale down the primary unit of mysql
    primary_unit_name = get_mysql_primary_unit(juju, APP_NAME, random_unit)

    juju.remove_unit(primary_unit_name)

    juju.wait(
        ready=wait_for_apps_status(jubilant_backports.all_active, APP_NAME),
        error=jubilant_backports.any_blocked,
        timeout=FAST_WAIT_TIMEOUT,
    )

    check_keystone_users_existence(
        juju, APP_NAME, server_config_credentials, keystone_users, another_keystone_users
    )

    # Scale mysql back up to 3 units
    scale_app_units(juju, APP_NAME, 3)

    # Scale down the first deployment of keystone
    scale_app_units(juju, KEYSTONE_APP_NAME, 0)
    juju.remove_application(KEYSTONE_APP_NAME)

    # Scale down the mysql application
    scale_app_units(juju, APP_NAME, 0)
    juju.remove_application(APP_NAME)
