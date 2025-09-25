#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import subprocess

import jubilant
import pytest
from jubilant import Juju

from ..markers import juju3
from .high_availability_helpers_new import (
    check_mysql_units_writes_increment,
    get_app_units,
    wait_for_apps_status,
    wait_for_unit_status,
)

MYSQL_APP_NAME = "mysql"
MYSQL_TEST_APP_NAME = "mysql-test-app"

MINUTE_SECS = 60

logging.getLogger("jubilant.wait").setLevel(logging.WARNING)


@juju3
@pytest.mark.abort_on_fail
def test_deploy_stable(juju: Juju) -> None:
    """Simple test to ensure that the MySQL and application charms get deployed."""
    logging.info("Deploying MySQL cluster")
    juju.deploy(
        charm=MYSQL_APP_NAME,
        app=MYSQL_APP_NAME,
        base="ubuntu@22.04",
        channel="8.0/stable",
        config={"profile": "testing"},
        num_units=3,
    )
    juju.deploy(
        charm=MYSQL_TEST_APP_NAME,
        app=MYSQL_TEST_APP_NAME,
        base="ubuntu@22.04",
        channel="latest/edge",
        config={"sleep_interval": 50},
        num_units=1,
    )

    juju.integrate(
        f"{MYSQL_APP_NAME}:database",
        f"{MYSQL_TEST_APP_NAME}:database",
    )

    logging.info("Wait for applications to become active")
    juju.wait(
        ready=wait_for_apps_status(jubilant.all_active, MYSQL_APP_NAME, MYSQL_TEST_APP_NAME),
        error=jubilant.any_blocked,
        timeout=20 * MINUTE_SECS,
    )


@juju3
@pytest.mark.abort_on_fail
async def test_refresh_without_pre_upgrade_check(juju: Juju, charm: str) -> None:
    """Test updating from stable channel."""
    logging.info("Refresh the charm")
    juju.refresh(app=MYSQL_APP_NAME, path=charm)

    logging.info("Wait for rolling restart")
    wait_for_any_unit_status(juju, MYSQL_APP_NAME, "maintenance")

    logging.info("Wait for rolling restart to complete")
    juju.wait(
        ready=lambda status: jubilant.all_active(status, MYSQL_APP_NAME),
        timeout=20 * MINUTE_SECS,
    )

    await check_mysql_units_writes_increment(juju, MYSQL_APP_NAME)


@juju3
@pytest.mark.abort_on_fail
async def test_rollback_without_pre_upgrade_check(juju: Juju, charm: str) -> None:
    """Test refresh back to stable channel."""
    # Early Jubilant 1.X.Y versions do not support the `switch` option
    logging.info("Refresh the charm back to stable channel")
    subprocess.run(
        ["juju", "refresh", "--channel=8.0/stable", f"--switch={MYSQL_APP_NAME}", MYSQL_APP_NAME],
        check=True,
    )

    logging.info("Wait for rolling restart")
    wait_for_any_unit_status(juju, MYSQL_APP_NAME, "maintenance")

    logging.info("Wait for rolling restart to complete")
    juju.wait(
        ready=wait_for_apps_status(jubilant.all_active, MYSQL_APP_NAME),
        timeout=20 * MINUTE_SECS,
    )

    await check_mysql_units_writes_increment(juju, MYSQL_APP_NAME)


def wait_for_any_unit_status(juju: Juju, app_name: str, unit_status: str) -> None:
    """Wait for any app unit to reach the desired status."""
    app_units = get_app_units(juju, app_name)
    app_units_funcs = [wait_for_unit_status(app_name, unit, unit_status) for unit in app_units]

    juju.wait(
        ready=lambda status: any(status_func(status) for status_func in app_units_funcs),
        timeout=10 * MINUTE_SECS,
    )
