# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import json
import logging
import os
import pathlib
import zipfile
from pathlib import Path
from shutil import copy
from typing import Union

import pytest
from pytest_operator.plugin import OpsTest

from .. import juju_
from ..helpers import (
    get_leader_unit,
    get_primary_unit_wrapper,
    get_relation_data,
    retrieve_database_variable_value,
)
from .high_availability_helpers import (
    ensure_all_units_continuous_writes_incrementing,
    relate_mysql_and_application,
)

logger = logging.getLogger(__name__)

TIMEOUT = 20 * 60

MYSQL_APP_NAME = "mysql"
TEST_APP_NAME = "mysql-test-app"


@pytest.mark.abort_on_fail
async def test_deploy_latest(ops_test: OpsTest) -> None:
    """Simple test to ensure that the mysql and application charms get deployed."""
    await asyncio.gather(
        ops_test.model.deploy(
            MYSQL_APP_NAME,
            application_name=MYSQL_APP_NAME,
            num_units=3,
            channel="8.0/edge",
            config={"profile": "testing"},
            base="ubuntu@22.04",
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


@pytest.mark.abort_on_fail
async def test_upgrade_from_edge(
    ops_test: OpsTest,
    charm,
    continuous_writes,
) -> None:
    logger.info("Ensure continuous_writes")
    await ensure_all_units_continuous_writes_incrementing(ops_test)

    application = ops_test.model.applications[MYSQL_APP_NAME]

    logger.info("Refresh the charm")
    await application.refresh(path=charm)

    logger.info("Wait for upgrade to start")
    await ops_test.model.block_until(
        lambda: "waiting" in {unit.workload_status for unit in application.units},
        timeout=TIMEOUT,
    )

    logger.info("Wait for upgrade to complete")
    await ops_test.model.wait_for_idle(
        apps=[MYSQL_APP_NAME], status="active", idle_period=30, timeout=TIMEOUT
    )

    logger.info("Ensure continuous_writes")
    await ensure_all_units_continuous_writes_incrementing(ops_test)


@pytest.mark.abort_on_fail
async def test_fail_and_rollback(ops_test, charm, continuous_writes) -> None:
    logger.info("Get leader unit")
    leader_unit = await get_leader_unit(ops_test, MYSQL_APP_NAME)

    assert leader_unit is not None, "No leader unit found"

    logger.info("Run pre-upgrade-check action")
    await juju_.run_action(leader_unit, "pre-upgrade-check")

    fault_charm = f"/tmp/{pathlib.Path(charm).name}"
    copy(charm, fault_charm)

    logger.info("Inject dependency fault")
    await inject_dependency_fault(ops_test, MYSQL_APP_NAME, fault_charm)

    application = ops_test.model.applications[MYSQL_APP_NAME]

    logger.info("Refresh the charm")
    await application.refresh(path=fault_charm)

    logger.info("Wait for upgrade to fail on leader")
    await ops_test.model.block_until(
        lambda: leader_unit.workload_status == "blocked",
        timeout=TIMEOUT,
    )

    logger.info("Ensure continuous_writes while in failure state")
    await ensure_all_units_continuous_writes_incrementing(ops_test)

    logger.info("Re-run pre-upgrade-check action")
    await juju_.run_action(leader_unit, "pre-upgrade-check")

    logger.info("Re-refresh the charm")
    await application.refresh(path=charm)
    logger.info("Wait for upgrade to start")
    await ops_test.model.block_until(
        lambda: "waiting" in {unit.workload_status for unit in application.units},
        timeout=TIMEOUT,
    )
    await ops_test.model.wait_for_idle(apps=[MYSQL_APP_NAME], status="active", timeout=TIMEOUT)

    logger.info("Ensure continuous_writes after rollback procedure")
    await ensure_all_units_continuous_writes_incrementing(ops_test)

    # remove fault charm file
    os.remove(fault_charm)


async def inject_dependency_fault(
    ops_test: OpsTest, application_name: str, charm_file: Union[str, Path]
) -> None:
    """Inject a dependency fault into the mysql charm."""
    # Open dependency.json and load current charm version
    with open("src/dependency.json", "r") as dependency_file:
        current_charm_version = json.load(dependency_file)["charm"]["version"]

    # query running dependency to overwrite with incompatible version
    relation_data = await get_relation_data(ops_test, application_name, "upgrade")

    loaded_dependency_dict = json.loads(relation_data[0]["application-data"]["dependencies"])
    loaded_dependency_dict["charm"]["upgrade_supported"] = f">{current_charm_version}"
    loaded_dependency_dict["charm"]["version"] = f"{int(current_charm_version) + 1}"

    # Overwrite dependency.json with incompatible version
    with zipfile.ZipFile(charm_file, mode="a") as charm_zip:
        charm_zip.writestr("src/dependency.json", json.dumps(loaded_dependency_dict))
