# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import logging

import pytest
from pytest_operator.plugin import OpsTest

from .. import juju_
from ..helpers import get_leader_unit, get_primary_unit_wrapper, retrieve_database_variable_value
from .high_availability_helpers import (
    ensure_all_units_continuous_writes_incrementing,
    relate_mysql_and_application,
)

logger = logging.getLogger(__name__)

TIMEOUT = 20 * 60

MYSQL_APP_NAME = "mysql"
TEST_APP_NAME = "mysql-test-app"


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


@pytest.mark.abort_on_fail
async def test_pre_upgrade_check(ops_test: OpsTest) -> None:
    """Test that the pre-upgrade-check action runs successfully."""
    mysql_units = ops_test.model.applications[MYSQL_APP_NAME].units

    logger.info("Get leader unit")
    leader_unit = await get_leader_unit(ops_test, MYSQL_APP_NAME)

    assert leader_unit is not None, "No leader unit found"
    logger.info("Run pre-upgrade-check action")
    await juju_.run_action(leader_unit, "pre-upgrade-check")

    logger.info("Assert slow shutdown is enabled")
    for unit in mysql_units:
        value = await retrieve_database_variable_value(ops_test, unit, "innodb_fast_shutdown")
        assert value == 0, f"innodb_fast_shutdown not 0 at {unit.name}"

    primary_unit = await get_primary_unit_wrapper(ops_test, MYSQL_APP_NAME)

    logger.info("Assert primary is set to leader")
    assert await primary_unit.is_leader_from_status(), "Primary unit not set to leader"


async def test_upgrade_from_stable(ops_test: OpsTest, charm):
    """Test updating from stable channel."""
    application = ops_test.model.applications[MYSQL_APP_NAME]

    logger.info("Refresh the charm")
    await application.refresh(path=charm)

    logger.info("Wait for upgrade to start")
    await ops_test.model.block_until(
        lambda: "maintenance" in {unit.workload_status for unit in application.units},
        timeout=TIMEOUT,
    )

    logger.info("Wait for upgrade to complete")
    await ops_test.model.wait_for_idle(
        apps=[MYSQL_APP_NAME], status="active", idle_period=30, timeout=TIMEOUT
    )

    logger.info("Ensure continuous_writes")
    await ensure_all_units_continuous_writes_incrementing(ops_test)
