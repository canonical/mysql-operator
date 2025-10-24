#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import logging
from pathlib import Path

import pytest
import yaml
from pytest_operator.plugin import OpsTest

from ... import juju_
from ..high_availability.high_availability_helpers import (
    ensure_all_units_continuous_writes_incrementing,
)

DB_METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
DATABASE_APP_NAME = DB_METADATA["name"]
APPLICATION_APP_NAME = "mysql-test-app"

TIMEOUT = 15 * 60

logger = logging.getLogger(__name__)


@pytest.mark.abort_on_fail
@pytest.mark.skip_if_deployed
async def test_build_and_deploy(ops_test: OpsTest, lxd_spaces, charm) -> None:
    """Build the charm and deploy 3 units to ensure a cluster is formed."""
    await asyncio.gather(
        ops_test.model.deploy(
            charm,
            application_name=DATABASE_APP_NAME,
            constraints={"spaces": ["client", "peers"]},
            bind={"database-peers": "peers", "database": "client"},
            num_units=3,
            base="ubuntu@22.04",
        ),
        ops_test.model.deploy(
            APPLICATION_APP_NAME,
            application_name=APPLICATION_APP_NAME,
            constraints={"spaces": ["client"]},
            bind={"database": "client"},
            num_units=1,
            base="ubuntu@22.04",
            channel="latest/edge",
        ),
    )

    # Reduce the update_status frequency until the cluster is deployed
    async with ops_test.fast_forward("60s"):
        await ops_test.model.block_until(
            lambda: len(ops_test.model.applications[DATABASE_APP_NAME].units) == 3,
            lambda: len(ops_test.model.applications[APPLICATION_APP_NAME].units) == 1,
        )
        await asyncio.gather(
            ops_test.model.wait_for_idle(
                apps=[DATABASE_APP_NAME],
                status="active",
                raise_on_blocked=True,
                timeout=TIMEOUT,
            ),
            ops_test.model.wait_for_idle(
                apps=[APPLICATION_APP_NAME],
                status="waiting",
                raise_on_blocked=True,
                timeout=TIMEOUT,
            ),
        )


async def test_integrate_with_spaces(ops_test: OpsTest):
    """Relate the database to the application."""
    await ops_test.model.relate(
        f"{DATABASE_APP_NAME}",
        f"{APPLICATION_APP_NAME}:database",
    )

    await ops_test.model.wait_for_idle(
        apps=[DATABASE_APP_NAME, APPLICATION_APP_NAME],
        status="active",
        timeout=TIMEOUT,
    )

    app = ops_test.model.applications[APPLICATION_APP_NAME]
    unit = app.units[0]

    # Remove default route on client so traffic can't be routed through default interface
    logger.info("Flush default routes on client")
    await unit.run("sudo ip route flush default")

    logger.info("Starting continuous writes")
    await juju_.run_action(unit, "start-continuous-writes")

    # Ensure continuous writes still incrementing for all units
    await ensure_all_units_continuous_writes_incrementing(ops_test)

    await ops_test.model.remove_application(APPLICATION_APP_NAME, block_until_done=True)


async def test_integrate_with_isolated_space(ops_test: OpsTest):
    """Relate the database to the application."""
    isolated_app_name = "isolated-test-app"

    await ops_test.model.deploy(
        APPLICATION_APP_NAME,
        application_name=isolated_app_name,
        constraints={"spaces": ["isolated"]},
        bind={"database": "isolated"},
        channel="latest/edge",
    )
    await ops_test.model.wait_for_idle(
        apps=[isolated_app_name],
        status="waiting",
        timeout=TIMEOUT,
    )

    # Relate the database to the application
    await ops_test.model.relate(
        f"{DATABASE_APP_NAME}",
        f"{isolated_app_name}:database",
    )
    await ops_test.model.wait_for_idle(
        apps=[DATABASE_APP_NAME, isolated_app_name],
        status="active",
        timeout=TIMEOUT,
    )

    app = ops_test.model.applications[isolated_app_name]
    unit = app.units[0]

    # Remove default route on client so traffic can't be routed through default interface
    logger.info("Flush default routes on client")
    await unit.run("sudo ip route flush default")

    logger.info("Starting continuous writes")
    await juju_.run_action(unit, "start-continuous-writes")

    # Ensure continuous writes do not increment for all units
    with pytest.raises(AssertionError):
        await ensure_all_units_continuous_writes_incrementing(ops_test)

    await ops_test.model.remove_application(isolated_app_name, block_until_done=True)
