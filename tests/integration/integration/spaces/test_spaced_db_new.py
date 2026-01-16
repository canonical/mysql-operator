#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.
import logging

import jubilant_backports
import pytest
from jubilant_backports import Juju
from tenacity import Retrying, stop_after_delay, wait_fixed

from ...helpers_ha import (
    get_app_units,
    get_mysql_max_written_value,
    get_mysql_primary_unit,
    wait_for_apps_status,
)

DATABASE_APP_NAME = "mysql"
APPLICATION_APP_NAME = "mysql-test-app"

TIMEOUT = 15 * 60

logger = logging.getLogger(__name__)

logging.getLogger("jubilant.wait").setLevel(logging.WARNING)


# TODO: Move to conftest.py before merging
@pytest.fixture(scope="module")
async def lxd_spaces(juju: Juju):
    juju.cli("reload-spaces")
    juju.cli("add-space", "client", "10.0.0.0/24")
    juju.cli("add-space", "peers", "10.10.10.0/24")
    juju.cli("add-space", "isolated", "10.20.20.0/24")


@pytest.mark.abort_on_fail
@pytest.mark.skip_if_deployed
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
    await ensure_all_units_continuous_writes_incrementing(juju, DATABASE_APP_NAME)

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
    juju.run(unit, "start-continuous-writes")

    # Ensure continuous writes do not increment for all units
    with pytest.raises(AssertionError):
        await ensure_all_units_continuous_writes_incrementing(juju, DATABASE_APP_NAME)

    juju.remove_application(isolated_app_name)
    juju.wait(
        ready=lambda status: isolated_app_name not in status.apps,
        timeout=TIMEOUT,
    )


async def ensure_all_units_continuous_writes_incrementing(
    juju: Juju,
    mysql_application_name: str,
) -> None:
    """Ensure that continuous writes is incrementing on all units.

    Also, ensure that all continuous writes up to the max written value is available
    on all units (ensure that no committed data is lost).
    """
    logger.info("Ensure continuous writes are incrementing")

    mysql_units = get_app_units(juju, mysql_application_name)
    primary = get_mysql_primary_unit(juju, mysql_application_name)

    last_max_written_value = await get_mysql_max_written_value(
        juju, mysql_application_name, primary
    )

    for unit in mysql_units:
        for attempt in Retrying(reraise=True, stop=stop_after_delay(5 * 60), wait=wait_fixed(10)):
            with attempt:
                # ensure the max written value is incrementing (continuous writes is active)
                max_written_value = await get_mysql_max_written_value(
                    juju,
                    mysql_application_name,
                    unit,
                )
                logger.info(f"{max_written_value=} on unit {unit}")
                assert max_written_value > last_max_written_value, (
                    "Continuous writes not incrementing"
                )

                last_max_written_value = max_written_value
