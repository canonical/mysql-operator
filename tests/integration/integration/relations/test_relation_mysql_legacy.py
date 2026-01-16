#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import logging

import jubilant_backports
import pytest
from jubilant_backports import Juju

from ...helpers import (
    is_connection_possible,
)
from ...helpers_ha import (
    get_legacy_mysql_credentials,
    wait_for_apps_status,
)

logger = logging.getLogger(__name__)

DATABASE_APP_NAME = "mysql"
CLUSTER_NAME = "test_cluster"

APPLICATION_APP_NAME = "mysql-test-app"

APPS = [DATABASE_APP_NAME, APPLICATION_APP_NAME]
ENDPOINT = "mysql"

TEST_USER = "testuser"
TEST_DATABASE = "continuous_writes"
TIMEOUT = 15 * 60


@pytest.mark.abort_on_fail
@pytest.mark.skip_if_deployed
def test_build_and_deploy(juju: Juju, charm) -> None:
    """Build the charm and deploy 3 units to ensure a cluster is formed."""
    logger.info(
        f"Deploying {DATABASE_APP_NAME} charm with 3 units, and {APPLICATION_APP_NAME} with 1 units"
    )

    juju.deploy(
        charm,
        DATABASE_APP_NAME,
        config={"cluster-name": CLUSTER_NAME, "profile": "testing"},
        num_units=3,
        base="ubuntu@22.04",
    )
    juju.deploy(
        APPLICATION_APP_NAME,
        num_units=1,
        channel="latest/edge",
        base="ubuntu@22.04",
    )

    logger.info("Awaiting until both applications are correctly deployed")

    juju.wait(
        ready=wait_for_apps_status(jubilant_backports.all_active, DATABASE_APP_NAME),
        error=jubilant_backports.any_blocked,
        timeout=TIMEOUT,
    )
    juju.wait(
        ready=wait_for_apps_status(jubilant_backports.all_waiting, APPLICATION_APP_NAME),
        error=jubilant_backports.any_blocked,
        timeout=TIMEOUT,
    )


@pytest.mark.abort_on_fail
def test_relation_creation(juju: Juju):
    """Relate charms and wait for the expected changes in status."""
    # Configure a user and database to be used for the relation
    # as required for this relation
    juju.config(
        DATABASE_APP_NAME,
        {"mysql-interface-user": TEST_USER, "mysql-interface-database": TEST_DATABASE},
    )

    logger.info(f"Relating {DATABASE_APP_NAME}:{ENDPOINT} with {APPLICATION_APP_NAME}:{ENDPOINT}")

    juju.integrate(f"{APPLICATION_APP_NAME}:{ENDPOINT}", f"{DATABASE_APP_NAME}:{ENDPOINT}")

    logger.info("Waiting until both applications are active")

    juju.wait(
        ready=wait_for_apps_status(
            jubilant_backports.all_active, DATABASE_APP_NAME, APPLICATION_APP_NAME
        ),
        error=jubilant_backports.any_blocked,
        timeout=TIMEOUT,
    )


@pytest.mark.abort_on_fail
def test_relation_broken(juju: Juju):
    """Remove relation and wait for the expected changes in status."""
    # store database credentials for test access later
    unit_name = f"{APPLICATION_APP_NAME}/0"
    credentials = get_legacy_mysql_credentials(juju, unit_name)

    logger.info(
        "Asserting that a connection to the database is still possible with application credentials"
    )

    assert is_connection_possible(credentials) is True

    logger.info(
        f"Removing relation {DATABASE_APP_NAME}:{ENDPOINT} with {APPLICATION_APP_NAME}:{ENDPOINT}"
    )

    juju.remove_relation(f"{APPLICATION_APP_NAME}:{ENDPOINT}", f"{DATABASE_APP_NAME}:{ENDPOINT}")

    logger.info(
        f"Waiting till {DATABASE_APP_NAME} is active and {APPLICATION_APP_NAME} is waiting"
    )

    juju.wait(
        ready=wait_for_apps_status(jubilant_backports.all_active, DATABASE_APP_NAME),
        error=jubilant_backports.any_blocked,
        timeout=TIMEOUT,
    )
    juju.wait(
        ready=wait_for_apps_status(jubilant_backports.all_waiting, APPLICATION_APP_NAME),
        error=jubilant_backports.any_blocked,
        timeout=TIMEOUT,
    )

    logger.info(
        "Asserting that a connection to the database is not possible with application credentials"
    )

    assert is_connection_possible(credentials) is False
