# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from pathlib import Path
from subprocess import run
from time import sleep

import pytest
import yaml
from pytest_operator.plugin import OpsTest

from .high_availability.high_availability_helpers import (
    deploy_and_scale_mysql,
    get_application_name,
)

logger = logging.getLogger(__name__)


METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
SLEEP_WAIT = 5


@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest, charm) -> None:
    """Build the charm and deploy 3 units to ensure a cluster is formed."""
    await deploy_and_scale_mysql(ops_test, charm)


@pytest.mark.abort_on_fail
async def test_reboot_1_of_3_units(ops_test: OpsTest) -> None:
    """Reboot a single unit and ensure it comes back online."""
    app_name = get_application_name(ops_test, "mysql")
    app = ops_test.model.applications[app_name]
    unit = app.units[0]

    logger.info(f"Rebooting single {unit.name}")
    _machine_restart(unit.machine.hostname)
    logger.info("Sleep to allow juju status change")
    sleep(SLEEP_WAIT)
    logger.info("Waiting for the application to become idle")
    async with ops_test.fast_forward("30s"):
        await ops_test.model.wait_for_idle(
            apps=[app_name],
            status="active",
            timeout=15 * 60,
        )


@pytest.mark.abort_on_fail
async def test_reboot_2_of_3_units(ops_test: OpsTest) -> None:
    """Reboot a single unit and ensure it comes back online."""
    app_name = get_application_name(ops_test, "mysql")
    app = ops_test.model.applications[app_name]

    for unit in app.units[:2]:
        logger.info(f"Rebooting {unit.name}")
        _machine_restart(unit.machine.hostname)
    logger.info("Sleep to allow juju status change")
    sleep(SLEEP_WAIT)
    logger.info("Waiting for the application to become idle")
    async with ops_test.fast_forward("30s"):
        await ops_test.model.wait_for_idle(
            apps=[app_name],
            status="active",
            timeout=15 * 60,
        )


@pytest.mark.abort_on_fail
async def test_reboot_3_of_3_units(ops_test: OpsTest) -> None:
    """Reboot a single unit and ensure it comes back online."""
    app_name = get_application_name(ops_test, "mysql")
    app = ops_test.model.applications[app_name]

    for unit in app.units:
        logger.info(f"Rebooting {unit.name}")
        _machine_restart(unit.machine.hostname)
    logger.info("Sleep to allow juju status change")
    sleep(SLEEP_WAIT)
    logger.info("Waiting for the application to become idle")
    async with ops_test.fast_forward("30s"):
        await ops_test.model.wait_for_idle(
            apps=[app_name],
            status="active",
            timeout=15 * 60,
        )


def _machine_restart(machine_name: str) -> None:
    """Restart the machine."""
    run(["lxc", "restart", machine_name], check=True)
