# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from subprocess import run
from time import sleep

import jubilant_backports
import pytest
from jubilant_backports import Juju

from ..helpers_ha import MINUTE_SECS, get_app_units, get_unit_machine

logger = logging.getLogger(__name__)

logging.getLogger("jubilant.wait").setLevel(logging.WARNING)

APP_NAME = "mysql"
CLUSTER_NAME = "test_cluster"
SLEEP_WAIT = 5
TIMEOUT = 15 * MINUTE_SECS


@pytest.mark.skip_if_deployed
@pytest.mark.abort_on_fail
def test_build_and_deploy(juju: Juju, charm) -> None:
    """Build the charm and deploy 3 units to ensure a cluster is formed."""
    logger.info(f"Deploying {APP_NAME}")
    juju.deploy(
        charm,
        APP_NAME,
        base="ubuntu@22.04",
        config={"cluster-name": CLUSTER_NAME, "profile": "testing"},
        num_units=3,
        trust=True,
    )

    juju.wait(
        jubilant_backports.all_active,
        timeout=TIMEOUT,
    )


@pytest.mark.abort_on_fail
def test_reboot_1_of_3_units(juju: Juju) -> None:
    """Reboot a single unit and ensure it comes back online."""
    app_units = get_app_units(juju, APP_NAME)
    unit_name = app_units[0]

    logger.info(f"Rebooting single {unit_name}")
    machine_name = get_unit_machine(juju, APP_NAME, unit_name)
    machine_restart(machine_name)

    logger.info("Sleep to allow juju status change")
    sleep(SLEEP_WAIT)
    logger.info("Waiting for the application to become idle")
    juju.wait(
        jubilant_backports.all_active,
        timeout=TIMEOUT,
    )


@pytest.mark.abort_on_fail
def test_reboot_2_of_3_units(juju: Juju) -> None:
    """Reboot 2 units and ensure they come back online."""
    app_units = get_app_units(juju, APP_NAME)

    for unit_name in app_units[:2]:
        logger.info(f"Rebooting {unit_name}")
        machine_name = get_unit_machine(juju, APP_NAME, unit_name)
        machine_restart(machine_name)

    logger.info("Sleep to allow juju status change")
    sleep(SLEEP_WAIT)
    logger.info("Waiting for the application to become idle")
    juju.wait(
        jubilant_backports.all_active,
        timeout=TIMEOUT,
    )


@pytest.mark.abort_on_fail
def test_reboot_3_of_3_units(juju: Juju) -> None:
    """Reboot all 3 units and ensure they come back online."""
    app_units = get_app_units(juju, APP_NAME)

    for unit_name in app_units:
        logger.info(f"Rebooting {unit_name}")
        machine_name = get_unit_machine(juju, APP_NAME, unit_name)
        machine_restart(machine_name)

    logger.info("Sleep to allow juju status change")
    sleep(SLEEP_WAIT)
    logger.info("Waiting for the application to become idle")
    juju.wait(
        jubilant_backports.all_active,
        timeout=TIMEOUT,
    )


def machine_restart(machine_name: str) -> None:
    """Restart the machine."""
    run(["lxc", "restart", machine_name], check=True)
