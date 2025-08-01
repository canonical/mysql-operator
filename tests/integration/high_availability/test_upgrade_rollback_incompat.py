# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import ast
import json
import logging
import pathlib
import shutil
from time import sleep
from zipfile import ZipFile

import pytest
from pytest_operator.plugin import OpsTest

from .. import juju_, markers
from ..helpers import (
    get_leader_unit,
    get_relation_data,
    get_status_log,
    get_unit_by_index,
)
from .high_availability_helpers import (
    ensure_all_units_continuous_writes_incrementing,
    relate_mysql_and_application,
)

logger = logging.getLogger(__name__)

TIMEOUT = 20 * 60
MYSQL_APP_NAME = "mysql"
TEST_APP = "mysql-test-app"


# TODO: remove after next incompatible MySQL server version released in our snap
# (details: https://github.com/canonical/mysql-operator/pull/472#discussion_r1659300069)
@markers.amd64_only
@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest, charm) -> None:
    """Simple test to ensure that the mysql and application charms get deployed."""
    snap_revisions = pathlib.Path("snap_revisions.json")
    with snap_revisions.open("r") as file:
        old_revisions: dict = json.load(file)
    new_revisions = old_revisions.copy()
    # TODO: support arm64 & s390x
    new_revisions["x86_64"] = "69"
    with snap_revisions.open("w") as file:
        json.dump(new_revisions, file)
    local_charm = await charm_local_build(ops_test, charm)

    with snap_revisions.open("w") as file:
        json.dump(old_revisions, file)

    async with ops_test.fast_forward("30s"):
        await ops_test.model.deploy(
            local_charm,
            application_name=MYSQL_APP_NAME,
            num_units=3,
            base="ubuntu@22.04",
            config={"profile": "testing", "plugin-audit-enabled": "false"},
        )

        await ops_test.model.deploy(
            TEST_APP,
            application_name=TEST_APP,
            channel="latest/edge",
            num_units=1,
            base="ubuntu@22.04",
            config={"auto_start_writes": False, "sleep_interval": "500"},
        )

        await relate_mysql_and_application(ops_test, MYSQL_APP_NAME, TEST_APP)
        await ops_test.model.wait_for_idle(
            apps=[MYSQL_APP_NAME, TEST_APP],
            status="active",
            timeout=TIMEOUT,
        )


# TODO: remove after next incompatible MySQL server version released in our snap
# (details: https://github.com/canonical/mysql-operator/pull/472#discussion_r1659300069)
@markers.amd64_only
@pytest.mark.abort_on_fail
async def test_pre_upgrade_check(ops_test: OpsTest) -> None:
    """Test that the pre-upgrade-check action runs successfully."""
    logger.info("Get leader unit")
    leader_unit = await get_leader_unit(ops_test, MYSQL_APP_NAME)

    assert leader_unit is not None, "No leader unit found"
    logger.info("Run pre-upgrade-check action")
    await juju_.run_action(leader_unit, "pre-upgrade-check")


# TODO: remove after next incompatible MySQL server version released in our snap
# (details: https://github.com/canonical/mysql-operator/pull/472#discussion_r1659300069)
@markers.amd64_only
@pytest.mark.abort_on_fail
async def test_upgrade_to_failling(
    ops_test: OpsTest,
    charm,
    continuous_writes,
) -> None:
    logger.info("Ensure continuous_writes")
    await ensure_all_units_continuous_writes_incrementing(ops_test)

    application = ops_test.model.applications[MYSQL_APP_NAME]

    with InjectFailure(
        path="src/upgrade.py",
        original_str="self.charm.recover_unit_after_restart()",
        replace_str="raise Exception",
    ):
        logger.info("Build charm with failure injected")
        new_charm = await charm_local_build(ops_test, charm, refresh=True)

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


# TODO: remove after next incompatible MySQL server version released in our snap
# (details: https://github.com/canonical/mysql-operator/pull/472#discussion_r1659300069)
@markers.amd64_only
@pytest.mark.abort_on_fail
async def test_rollback(ops_test, charm, continuous_writes) -> None:
    application = ops_test.model.applications[MYSQL_APP_NAME]

    relation_data = await get_relation_data(ops_test, MYSQL_APP_NAME, "upgrade")
    upgrade_stack = relation_data[0]["application-data"]["upgrade-stack"]
    upgrading_unit = get_unit_by_index(
        MYSQL_APP_NAME, application.units, ast.literal_eval(upgrade_stack)[-1]
    )
    assert upgrading_unit is not None, "No upgrading unit found"
    assert upgrading_unit.workload_status == "blocked", "Upgrading unit's status is not blocked"

    snap_revisions = pathlib.Path("snap_revisions.json")
    with snap_revisions.open("r") as file:
        old_revisions: dict = json.load(file)
    new_revisions = old_revisions.copy()
    # TODO: support arm64 & s390x
    new_revisions["x86_64"] = "69"
    with snap_revisions.open("w") as file:
        json.dump(new_revisions, file)
    local_charm = await charm_local_build(ops_test, charm, refresh=True)

    logger.info("Get leader unit")
    leader_unit = await get_leader_unit(ops_test, MYSQL_APP_NAME)

    assert leader_unit is not None, "No leader unit found"

    sleep(10)
    logger.info("Run pre-upgrade-check action")
    await juju_.run_action(leader_unit, "pre-upgrade-check")

    sleep(20)
    logger.info("Refresh with previous charm")
    await application.refresh(path=local_charm)

    logger.info("Wait for upgrade to start")
    await ops_test.model.block_until(
        lambda: "waiting" in {unit.workload_status for unit in application.units},
        timeout=TIMEOUT,
    )
    await ops_test.model.wait_for_idle(apps=[MYSQL_APP_NAME], status="active", timeout=TIMEOUT)

    logger.info("Ensure rollback has taken place")

    status_logs = await get_status_log(ops_test, upgrading_unit.name, 100)

    upgrade_failed_index = -1
    for index, status_log in enumerate(status_logs):
        if "upgrade failed. Check logs for rollback instruction" in status_log:
            upgrade_failed_index = index
            break
    assert upgrade_failed_index > -1, "Upgrade failed status log not found"

    post_upgrade_failed_status_logs = status_logs[upgrade_failed_index:]

    upgrade_complete_index = -1
    for index, status_log in enumerate(post_upgrade_failed_status_logs):
        if "upgrade completed" in status_log:
            upgrade_complete_index = index
            break
    assert upgrade_complete_index > -1, "Upgrade completed status log not found for rollback"

    logger.info("Ensure continuous_writes after rollback procedure")
    await ensure_all_units_continuous_writes_incrementing(ops_test)


class InjectFailure(object):
    def __init__(self, path: str, original_str: str, replace_str: str):
        self.path = path
        self.original_str = original_str
        self.replace_str = replace_str
        with open(path, "r") as file:
            self.original_content = file.read()

    def __enter__(self):
        logger.info("Injecting failure")
        assert self.original_str in self.original_content, "replace content not found"
        new_content = self.original_content.replace(self.original_str, self.replace_str)
        assert self.original_str not in new_content, "original string not replaced"
        with open(self.path, "w") as file:
            file.write(new_content)

    def __exit__(self, exc_type, exc_value, traceback):
        logger.info("Reverting failure")
        with open(self.path, "w") as file:
            file.write(self.original_content)


async def charm_local_build(ops_test: OpsTest, charm, refresh: bool = False):
    """Wrapper for a local charm build zip file updating."""
    local_charms = pathlib.Path().glob("local-*.charm")
    for lc in local_charms:
        # clean up local charms from previous runs to avoid
        # pytest_operator_cache globbing them
        lc.unlink()

    update_files = ["snap_revisions.json", "src/upgrade.py"]

    # create a copy of the charm to avoid modifying the original
    local_charm = pathlib.Path(shutil.copy(charm, f"local-{pathlib.Path(charm).stem}.charm"))

    for path in update_files:
        with open(path, "r") as f:
            content = f.read()

        with ZipFile(local_charm, mode="a") as charm_zip:
            charm_zip.writestr(path, content)

    if refresh:
        # when refreshing, return posix path
        return local_charm
    # when deploying, return prefixed full path
    return f"local:{local_charm.resolve()}"
