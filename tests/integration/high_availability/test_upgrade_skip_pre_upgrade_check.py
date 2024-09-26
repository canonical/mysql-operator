# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import logging
from time import sleep

import pytest
from pytest_operator.plugin import OpsTest

from .. import markers
from .high_availability_helpers import (
    ensure_all_units_continuous_writes_incrementing,
    relate_mysql_and_application,
)

logger = logging.getLogger(__name__)

TIMEOUT = 20 * 60

MYSQL_APP_NAME = "mysql"
TEST_APP_NAME = "mysql-test-app"


@pytest.mark.group(1)
@markers.amd64_only  # TODO: remove after arm64 stable release
@pytest.mark.abort_on_fail
async def test_deploy_stable(ops_test: OpsTest) -> None:
    """Simple test to ensure that the mysql and application charms get deployed."""
    await asyncio.gather(
        ops_test.model.deploy(
            MYSQL_APP_NAME,
            application_name=MYSQL_APP_NAME,
            num_units=3,
            channel="8.0/stable",
            base="ubuntu@22.04",
            config={"profile": "testing"},
        ),
        ops_test.model.deploy(
            TEST_APP_NAME,
            application_name=TEST_APP_NAME,
            num_units=1,
            channel="latest/edge",
            base="ubuntu@22.04",
            config={"sleep_interval": 50},
        ),
    )
    await relate_mysql_and_application(ops_test, MYSQL_APP_NAME, TEST_APP_NAME)
    logger.info("Wait for applications to become active")
    await ops_test.model.wait_for_idle(
        apps=[MYSQL_APP_NAME, TEST_APP_NAME],
        status="active",
        timeout=TIMEOUT,
    )
    assert len(ops_test.model.applications[MYSQL_APP_NAME].units) == 3


@pytest.mark.group(1)
@markers.amd64_only  # TODO: remove after arm64 stable release
async def test_refresh_without_pre_upgrade_check(ops_test: OpsTest):
    """Test updating from stable channel."""
    application = ops_test.model.applications[MYSQL_APP_NAME]
    logger.info("Build charm locally")
    charm = await ops_test.build_charm(".")

    logger.info("Refresh the charm")
    await application.refresh(path=charm)

    # Refresh without pre-upgrade-check can have two immediate effects:
    #   1. None, if there's no configuration change
    #   2. Rolling restart, if there's a configuration change
    # for both, operations should continue to work
    # and there's a mismatch between the charm and the snap
    logger.info("Wait for rolling restart OR continue to writes")
    count = 0
    while count < 2 * 60:
        if "maintenance" in {unit.workload_status for unit in application.units}:
            # Case when refresh triggers a rolling restart
            logger.info("Waiting for rolling restart to complete")
            await ops_test.model.wait_for_idle(
                apps=[MYSQL_APP_NAME], status="active", idle_period=30, timeout=TIMEOUT
            )
            break
        else:
            count += 1
            sleep(1)

    logger.info("Ensure continuous_writes")
    await ensure_all_units_continuous_writes_incrementing(ops_test)
