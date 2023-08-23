# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import logging

import pytest
from integration.helpers import (
    get_primary_unit_wrapper,
    retrieve_database_variable_value,
)
from integration.high_availability.high_availability_helpers import (
    ensure_all_units_continuous_writes_incrementing,
    high_availability_test_setup,
)
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)

TIMEOUT = 15 * 60


@pytest.mark.group(1)
async def test_build_and_deploy(ops_test: OpsTest, mysql_charm_series: str) -> None:
    """Simple test to ensure that the mysql and application charms get deployed."""
    await high_availability_test_setup(ops_test, mysql_charm_series)


@pytest.mark.group(1)
@pytest.mark.abort_on_fail
async def test_pre_upgrade_check(ops_test: OpsTest, mysql_charm_series: str) -> None:
    """Test that the pre-upgrade-check action runs successfully."""
    mysql_app_name, _ = await high_availability_test_setup(ops_test, mysql_charm_series)

    mysql_units = ops_test.model.applications[mysql_app_name].units

    logger.info("Get leader unit")
    leader_unit = None
    for unit in mysql_units:
        if await unit.is_leader_from_status():
            leader_unit = unit
            break

    assert leader_unit is not None, "No leader unit found"
    logger.info("Run pre-upgrade-check action")
    action = await leader_unit.run_action("pre-upgrade-check")
    await action.wait()

    logger.info("Assert slow shutdown is enabled")
    for unit in mysql_units:
        value = await retrieve_database_variable_value(ops_test, unit, "innodb_fast_shutdown")
        assert value == 0, f"innodb_fast_shutdown not 0 at {unit.name}"

    primary_unit = await get_primary_unit_wrapper(ops_test, mysql_app_name)

    logger.info("Assert primary is set to leader")
    assert await primary_unit.is_leader_from_status(), "Primary unit not set to leader"


@pytest.mark.group(1)
@pytest.mark.abort_on_fail
async def test_upgrade_charms(
    ops_test: OpsTest, continuous_writes, mysql_charm_series: str
) -> None:
    mysql_app_name, _ = await high_availability_test_setup(ops_test, mysql_charm_series)
    logger.info("Ensure continuous_writes")
    await ensure_all_units_continuous_writes_incrementing(ops_test)

    logger.info("Refresh the charm")
    application = ops_test.model.applications[mysql_app_name]
    charm = await ops_test.build_charm(".")
    await application.refresh(path=charm)
    async with ops_test.fast_forward("60s"):
        await ops_test.model.wait_for_idle(apps=[mysql_app_name], status="active", timeout=TIMEOUT)

    mysql_units = ops_test.model.applications[mysql_app_name].units
    leader_unit = None
    for unit in mysql_units:
        if await unit.is_leader_from_status():
            leader_unit = unit
            break

    assert leader_unit is not None, "No leader unit found"
    logger.info("Wait for upgrade to complete")
    await ops_test.model.wait_for_idle(
        apps=[mysql_app_name], status="active", idle_period=30, timeout=TIMEOUT
    )

    logger.info("Ensure continuous_writes")
    await ensure_all_units_continuous_writes_incrementing(ops_test)
