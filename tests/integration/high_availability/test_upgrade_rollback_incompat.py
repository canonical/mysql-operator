# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import ast
import logging
import subprocess

import pytest
from pytest_operator.plugin import OpsTest

from .. import juju_
from ..helpers import get_leader_unit, get_relation_data, get_unit_by_index
from .high_availability_helpers import (
    ensure_all_units_continuous_writes_incrementing,
    high_availability_test_setup,
)

logger = logging.getLogger(__name__)

TIMEOUT = 20 * 60
MYSQL_APP_NAME = "mysql"


@pytest.mark.group(1)
@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest, mysql_charm_series: str) -> None:
    """Simple test to ensure that the mysql and application charms get deployed."""
    sub_regex_older_snap = "s/CHARMED_MYSQL_SNAP_REVISION.*/CHARMED_MYSQL_SNAP_REVISION = 69/"
    src_patch(sub_regex=sub_regex_older_snap, file_name="src/constants.py")
    # store for later refreshing to it
    await high_availability_test_setup(ops_test, mysql_charm_series)

    src_patch(revert=True)


@pytest.mark.group(1)
@pytest.mark.abort_on_fail
async def test_pre_upgrade_check(ops_test: OpsTest) -> None:
    """Test that the pre-upgrade-check action runs successfully."""
    logger.info("Get leader unit")
    leader_unit = await get_leader_unit(ops_test, MYSQL_APP_NAME)

    assert leader_unit is not None, "No leader unit found"
    logger.info("Run pre-upgrade-check action")
    await juju_.run_action(leader_unit, "pre-upgrade-check")


@pytest.mark.group(1)
@pytest.mark.abort_on_fail
async def test_upgrade_to_failling(
    ops_test: OpsTest,
    continuous_writes,
) -> None:
    logger.info("Ensure continuous_writes")
    await ensure_all_units_continuous_writes_incrementing(ops_test)

    application = ops_test.model.applications[MYSQL_APP_NAME]
    logger.info("Build charm locally")

    sub_regex_failing_rejoin = (
        's/logger.debug("Recovering unit")/self.charm._mysql.set_instance_offline_mode(True)/'
    )
    src_patch(sub_regex=sub_regex_failing_rejoin, file_name="src/upgrade.py")
    new_charm = await ops_test.build_charm(".")
    src_patch(revert=True)

    logger.info("Refresh the charm")
    await application.refresh(path=new_charm)

    logger.info("Wait for upgrade to start")
    await ops_test.model.block_until(
        lambda: "waiting" in {unit.workload_status for unit in application.units},
        timeout=TIMEOUT,
    )
    logger.info("Get first upgrading unit")
    relation_data = await get_relation_data(ops_test, MYSQL_APP_NAME, "upgrade")
    upgrade_stack = relation_data[0]["application-data"]["upgrade-stack"]
    upgrading_unit = get_unit_by_index(
        MYSQL_APP_NAME, application.units, ast.literal_eval(upgrade_stack)[-1]
    )

    assert upgrading_unit is not None, "No upgrading unit found"

    logger.info("Wait for upgrade to fail on upgrading unit")
    await ops_test.model.block_until(
        lambda: upgrading_unit.workload_status == "blocked",
        timeout=TIMEOUT,
    )


@pytest.mark.group(1)
@pytest.mark.abort_on_fail
async def test_rollback(ops_test, continuous_writes) -> None:
    logger.info("Get leader unit")
    leader_unit = await get_leader_unit(ops_test, MYSQL_APP_NAME)

    assert leader_unit is not None, "No leader unit found"

    logger.info("Run pre-upgrade-check action")
    await juju_.run_action(leader_unit, "pre-upgrade-check")

    application = ops_test.model.applications[MYSQL_APP_NAME]

    sub_regex_older_snap = "s/CHARMED_MYSQL_SNAP_REVISION.*/CHARMED_MYSQL_SNAP_REVISION = 69/"
    src_patch(sub_regex=sub_regex_older_snap, file_name="src/constants.py")

    charm = await ops_test.build_charm(".")
    logger.info("Refresh with previous charm")
    await application.refresh(path=charm)

    logger.info("Wait for upgrade to start")
    await ops_test.model.block_until(
        lambda: "waiting" in {unit.workload_status for unit in application.units},
        timeout=TIMEOUT,
    )
    await ops_test.model.wait_for_idle(apps=[MYSQL_APP_NAME], status="active", timeout=TIMEOUT)

    logger.info("Ensure continuous_writes after rollback procedure")
    await ensure_all_units_continuous_writes_incrementing(ops_test)


def src_patch(sub_regex: str = "", file_name: str = "", revert: bool = False) -> None:
    """Apply a patch to the source code."""
    if revert:
        cmd = "git checkout ."  # revert all changes
        logger.info("Reverting patch on source")
    else:
        cmd = f"sed -i -e '{sub_regex}' {file_name}"
        logger.info("Applying patch to source")
    subprocess.run([cmd], shell=True, check=True)
