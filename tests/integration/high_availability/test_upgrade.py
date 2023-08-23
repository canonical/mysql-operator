# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import json
import logging
import os
from pathlib import Path
from shutil import copy

import pytest
from integration.helpers import (
    get_leader_unit,
    get_primary_unit_wrapper,
    get_relation_data,
    retrieve_database_variable_value,
)
from integration.high_availability.high_availability_helpers import (
    ensure_all_units_continuous_writes_incrementing,
    relate_mysql_and_application,
)
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)

TIMEOUT = 15 * 60

MYSQL_APP_NAME = "mysql"
TEST_APP_NAME = "mysql-test-app"


@pytest.mark.group(1)
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
        ),
        ops_test.model.deploy(
            TEST_APP_NAME,
            application_name=TEST_APP_NAME,
            num_units=1,
            channel="latest/edge",
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
@pytest.mark.abort_on_fail
async def test_pre_upgrade_check(ops_test: OpsTest) -> None:
    """Test that the pre-upgrade-check action runs successfully."""
    mysql_units = ops_test.model.applications[MYSQL_APP_NAME].units

    logger.info("Get leader unit")
    leader_unit = await get_leader_unit(ops_test, MYSQL_APP_NAME)

    assert leader_unit is not None, "No leader unit found"
    logger.info("Run pre-upgrade-check action")
    action = await leader_unit.run_action("pre-upgrade-check")
    await action.wait()

    logger.info("Assert slow shutdown is enabled")
    for unit in mysql_units:
        value = await retrieve_database_variable_value(ops_test, unit, "innodb_fast_shutdown")
        assert value == 0, f"innodb_fast_shutdown not 0 at {unit.name}"

    primary_unit = await get_primary_unit_wrapper(ops_test, MYSQL_APP_NAME)

    logger.info("Assert primary is set to leader")
    assert await primary_unit.is_leader_from_status(), "Primary unit not set to leader"


@pytest.mark.group(1)
@pytest.mark.abort_on_fail
async def test_upgrade_charms(
    ops_test: OpsTest,
    continuous_writes,
) -> None:
    logger.info("Ensure continuous_writes")
    await ensure_all_units_continuous_writes_incrementing(ops_test)

    application = ops_test.model.applications[MYSQL_APP_NAME]
    logger.info("Build charm locally")
    charm = await ops_test.build_charm(".")

    logger.info("Refresh the charm")
    await application.refresh(path=charm)

    logger.info("Wait for upgrade to start")
    await ops_test.model.block_until(
        lambda: "waiting" in {unit.workload_status for unit in application.units},
        timeout=TIMEOUT,
    )

    # backup charm file for rollback test
    if not isinstance(charm, Path):
        charm = Path(charm)
    charm.rename(f"/tmp/{charm.name}-backup")

    logger.info("Wait for upgrade to complete")
    await ops_test.model.wait_for_idle(
        apps=[MYSQL_APP_NAME], status="active", idle_period=30, timeout=TIMEOUT
    )

    logger.info("Ensure continuous_writes")
    await ensure_all_units_continuous_writes_incrementing(ops_test)


@pytest.mark.group(1)
@pytest.mark.abort_on_fail
async def test_fail_and_rollback(ops_test, continuous_writes) -> None:
    logger.info("Get leader unit")
    leader_unit = await get_leader_unit(ops_test, MYSQL_APP_NAME)

    assert leader_unit is not None, "No leader unit found"

    logger.info("Run pre-upgrade-check action")
    action = await leader_unit.run_action("pre-upgrade-check")
    await action.wait()

    logger.info("Inject dependency fault")
    await inject_dependency_fault(ops_test, MYSQL_APP_NAME)

    application = ops_test.model.applications[MYSQL_APP_NAME]
    logger.info("Re-build faulty charm locally")
    charm = await ops_test.build_charm(".")

    logger.info("Refresh the charm")
    await application.refresh(path=charm)

    logger.info("Wait for upgrade to fail on leader")
    await ops_test.model.block_until(
        lambda: leader_unit.workload_status == "blocked",
        timeout=TIMEOUT,
    )

    logger.info("Ensure continuous_writes while in failure state")
    await ensure_all_units_continuous_writes_incrementing(ops_test)

    logger.info("Re-run pre-upgrade-check action")
    action = await leader_unit.run_action("pre-upgrade-check")
    await action.wait()

    # restore original charm file
    logger.info("Restore original charm file")
    copy(f"/tmp/{charm.name}-backup", charm.absolute())

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


@pytest.mark.group(1)
@pytest.mark.abort_on_fail
async def test_upgrade_from_stable(ops_test: OpsTest):
    """Test updating from stable channel."""
    logger.info("Remove mysql")
    await ops_test.model.remove_application(MYSQL_APP_NAME, block_until_done=True)
    logger.info("Deploy mysql from stable")
    await ops_test.model.deploy(
        MYSQL_APP_NAME,
        application_name=MYSQL_APP_NAME,
        num_units=3,
        channel="8.0/stable",
        # config={"profile": "testing"}, # config not available in 8.0/stable@r151
    )
    logger.info("Relate test application")
    await relate_mysql_and_application(ops_test, MYSQL_APP_NAME, TEST_APP_NAME)

    application = ops_test.model.applications[MYSQL_APP_NAME]
    logger.info("Build charm locally")
    charm = await ops_test.build_charm(".")

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


async def inject_dependency_fault(ops_test: OpsTest, application_name: str):
    """Inject a dependency fault into the mysql charm."""
    # Open dependency.json and load current charm version
    if os.path.exists("src/dependency.json-orig"):
        # restore original file for multiple test runs
        copy("src/dependency.json-orig", "src/dependency.json")
    else:
        # backup original file
        copy("src/dependency.json", "src/dependency.json-orig")
    with open("src/dependency.json", "r") as dependency_file:
        current_charm_version = json.load(dependency_file)["charm"]["version"]

    # query running dependency to overwrite with incompatible version
    relation_data = await get_relation_data(ops_test, application_name, "upgrade")

    loaded_dependency_dict = json.loads(relation_data[0]["application-data"]["dependencies"])
    loaded_dependency_dict["charm"]["upgrade_supported"] = f">{current_charm_version}"
    loaded_dependency_dict["charm"]["version"] = f"{int(current_charm_version)+1}"

    with open("src/dependency.json", "w") as dependency_file:
        dependency_file.write(json.dumps(loaded_dependency_dict))
