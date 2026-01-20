#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.
import logging

import jubilant_backports
import pytest
from jubilant_backports import Juju

from ...helpers_ha import (
    MINUTE_SECS,
    check_mysql_units_writes_increment,
    get_app_units,
    wait_for_apps_status,
)

DATABASE_APP_NAME = "mysql"
APPLICATION_APP_NAME = "mysql-test-app"

TIMEOUT = 15 * MINUTE_SECS

logger = logging.getLogger(__name__)


@pytest.mark.abort_on_fail
def test_build_and_deploy(juju: Juju, lxd_spaces, charm) -> None:
    """Build the charm and deploy 3 units to ensure a cluster is formed."""
    juju.deploy(
        charm,
        DATABASE_APP_NAME,
        constraints={"spaces": "client,peers"},
        bind={"database-peers": "peers", "database": "client"},
        num_units=3,
        base="ubuntu@22.04",
    )
    # A race condition in Juju 2.9 makes `juju.wait` fail if called too early
    # (filesystem for storage instance "database/X" not found)
    # but it is enough to deploy another application in the meantime
    juju.deploy(
        APPLICATION_APP_NAME,
        APPLICATION_APP_NAME,
        constraints={"spaces": "client"},
        bind={"database": "client"},
        num_units=1,
        base="ubuntu@22.04",
        channel="latest/edge",
    )

    juju.wait(
        ready=wait_for_apps_status(jubilant_backports.all_active, DATABASE_APP_NAME),
        timeout=TIMEOUT,
    )
    juju.wait(
        ready=wait_for_apps_status(jubilant_backports.all_waiting, APPLICATION_APP_NAME),
        timeout=TIMEOUT,
    )


async def test_integrate_with_spaces(juju: Juju):
    """Relate the database to the application."""
    juju.integrate(
        f"{DATABASE_APP_NAME}",
        f"{APPLICATION_APP_NAME}:database",
    )
    juju.wait(
        ready=jubilant_backports.all_active,
        timeout=TIMEOUT,
    )

    unit = get_app_units(juju, APPLICATION_APP_NAME)[0]

    # Remove default route on client so traffic can't be routed through default interface
    logger.info("Flush default routes on client")
    juju.ssh(unit, "sudo ip route flush default")

    logger.info("Starting continuous writes")
    juju.run(unit, "start-continuous-writes")

    # Ensure continuous writes still incrementing for all units
    await check_mysql_units_writes_increment(juju, DATABASE_APP_NAME)

    juju.remove_application(APPLICATION_APP_NAME)
    juju.wait(
        ready=lambda status: APPLICATION_APP_NAME not in status.apps,
        timeout=TIMEOUT,
    )


async def test_integrate_with_isolated_space(juju: Juju):
    """Relate the database to the application."""
    isolated_app_name = "isolated-test-app"

    juju.deploy(
        APPLICATION_APP_NAME,
        isolated_app_name,
        constraints={"spaces": "isolated"},
        bind={"database": "isolated"},
        channel="latest/edge",
    )
    juju.wait(
        ready=wait_for_apps_status(jubilant_backports.all_waiting, isolated_app_name),
        timeout=TIMEOUT,
    )

    # Relate the database to the application
    juju.integrate(
        f"{DATABASE_APP_NAME}",
        f"{isolated_app_name}:database",
    )
    juju.wait(
        ready=wait_for_apps_status(
            jubilant_backports.all_active, DATABASE_APP_NAME, isolated_app_name
        ),
        timeout=TIMEOUT,
    )

    unit = get_app_units(juju, isolated_app_name)[0]

    # Remove default route on client so traffic can't be routed through default interface
    logger.info("Flush default routes on client")
    juju.ssh(unit, "sudo ip route flush default")

    logger.info("Starting continuous writes")
    # The charm will first try to stop the continuous writes,
    # which first queries the database to retrieve the last value.
    # OpsTest supported just enqueuing the action, but Jubilant doesn't,
    # so we need to acknowledge the timeout error resulting from the new network topology
    # (only in Juju >= 3)
    if juju._is_juju_2:
        juju.run(unit, "start-continuous-writes")
    else:
        with pytest.raises(TimeoutError):
            juju.run(unit, "start-continuous-writes")

    # Ensure continuous writes do not increment for all units
    with pytest.raises(AssertionError):
        await check_mysql_units_writes_increment(juju, DATABASE_APP_NAME)

    juju.remove_application(isolated_app_name)
    juju.wait(
        ready=lambda status: isolated_app_name not in status.apps,
        timeout=TIMEOUT,
    )
