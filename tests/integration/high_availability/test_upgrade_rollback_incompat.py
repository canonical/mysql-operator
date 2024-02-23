# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import ast
import logging
import subprocess
from tempfile import NamedTemporaryFile

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
PATCH_OLD_SNAP = (
    "diff --git a/src/constants.py b/src/constants.py\n"
    "index 4d6078e..515cf41 100644\n"
    "--- a/src/constants.py\n"
    "+++ b/src/constants.py\n"
    '@@ -25,7 +25,7 @@ TLS_SSL_KEY_FILE = "custom-server-key.pem"\n'
    ' TLS_SSL_CERT_FILE = "custom-server-cert.pem"\n'
    " MYSQL_EXPORTER_PORT = 9104\n"
    ' CHARMED_MYSQL_SNAP_NAME = "charmed-mysql"\n'
    "-CHARMED_MYSQL_SNAP_REVISION = 96  # MySQL v8.0.35\n"
    "+CHARMED_MYSQL_SNAP_REVISION = 69  # MySQL v8.0.34\n"
    ' CHARMED_MYSQLD_EXPORTER_SERVICE = "mysqld-exporter"\n'
    ' CHARMED_MYSQLD_SERVICE = "mysqld"\n'
    ' CHARMED_MYSQL = "charmed-mysql.mysql"\n'
)
PATCH_FAIL_UPGRADE = (
    "diff --git a/src/upgrade.py b/src/upgrade.py\n"
    "index 5b9c861..41b85fd 100644\n"
    "--- a/src/upgrade.py\n"
    "+++ b/src/upgrade.py\n"
    "@@ -240,6 +240,7 @@ class MySQLVMUpgrade(DataUpgrade):\n"
    " \n"
    "     def _recover_multi_unit_cluster(self) -> None:\n"
    '         logger.debug("Recovering unit")\n'
    "+        self.charm._mysql.set_instance_offline_mode(True)\n"
    "         try:\n"
    "             for attempt in Retrying(\n"
    "                 stop=stop_after_attempt(RECOVER_ATTEMPTS), wait=wait_fixed(10)\n"
)


@pytest.mark.group(1)
@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest, mysql_charm_series: str) -> None:
    """Simple test to ensure that the mysql and application charms get deployed."""
    src_patch(patch=PATCH_OLD_SNAP)
    # store for later refreshing to it
    global charm
    charm = await ops_test.build_charm(".")

    await high_availability_test_setup(ops_test, mysql_charm_series)

    src_patch(patch=PATCH_OLD_SNAP, revert=True)


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

    src_patch(patch=PATCH_FAIL_UPGRADE)
    new_charm = await ops_test.build_charm(".")
    src_patch(patch=PATCH_FAIL_UPGRADE, revert=True)

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


def src_patch(patch: str, revert: bool = False) -> None:
    """Apply a patch to the source code."""
    with NamedTemporaryFile("w", delete=False) as patch_file:
        patch_file.write(patch)
        if revert:
            cmd = f"patch -R -p1 <{patch_file.name}"
        else:
            cmd = f"patch -p1 <{patch_file.name}"
        subprocess.run([cmd], shell=True, check=True)
