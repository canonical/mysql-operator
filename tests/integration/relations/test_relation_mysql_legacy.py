#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import logging
from pathlib import Path

import pytest
import yaml
from pytest_operator.plugin import OpsTest

from ..helpers import (
    get_legacy_mysql_credentials,
    is_connection_possible,
    is_relation_broken,
    is_relation_joined,
)

logger = logging.getLogger(__name__)

DB_METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
DATABASE_APP_NAME = DB_METADATA["name"]
CLUSTER_NAME = "test_cluster"

APPLICATION_APP_NAME = "mysql-test-app"

APPS = [DATABASE_APP_NAME, APPLICATION_APP_NAME]
ENDPOINT = "mysql"

TEST_USER = "testuser"
TEST_DATABASE = "continuous_writes"
TIMEOUT = 15 * 60


@pytest.mark.abort_on_fail
@pytest.mark.skip_if_deployed
async def test_build_and_deploy(ops_test: OpsTest, charm) -> None:
    """Build the charm and deploy 3 units to ensure a cluster is formed."""
    config = {"cluster-name": CLUSTER_NAME, "profile": "testing"}

    logger.info(
        f"Deploying {DATABASE_APP_NAME} charm with 3 units, and {APPLICATION_APP_NAME} with 1 units"
    )

    await asyncio.gather(
        ops_test.model.deploy(
            charm,
            application_name=DATABASE_APP_NAME,
            config=config,
            num_units=3,
            base="ubuntu@22.04",
        ),
        ops_test.model.deploy(
            APPLICATION_APP_NAME,
            application_name=APPLICATION_APP_NAME,
            num_units=1,
            channel="latest/edge",
            base="ubuntu@22.04",
        ),
    )

    logger.info("Awaiting until both applications are correctly deployed")

    # Reduce the update_status frequency until the cluster is deployed
    async with ops_test.fast_forward("60s"):
        await ops_test.model.block_until(
            lambda: len(ops_test.model.applications[DATABASE_APP_NAME].units) == 3, timeout=TIMEOUT
        )

        await ops_test.model.block_until(
            lambda: len(ops_test.model.applications[APPLICATION_APP_NAME].units) == 1,
            timeout=TIMEOUT,
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

    assert len(ops_test.model.applications[DATABASE_APP_NAME].units) == 3

    for unit in ops_test.model.applications[DATABASE_APP_NAME].units:
        assert unit.workload_status == "active"

    assert len(ops_test.model.applications[APPLICATION_APP_NAME].units) == 1


@pytest.mark.abort_on_fail
async def test_relation_creation(ops_test: OpsTest):
    """Relate charms and wait for the expected changes in status."""
    # Configure a user and database to be used for the relation
    # as required for this relation
    await ops_test.model.applications[DATABASE_APP_NAME].set_config({
        "mysql-interface-user": TEST_USER,
        "mysql-interface-database": TEST_DATABASE,
    })

    logger.info(f"Relating {DATABASE_APP_NAME}:{ENDPOINT} with {APPLICATION_APP_NAME}:{ENDPOINT}")

    await ops_test.model.relate(
        f"{APPLICATION_APP_NAME}:{ENDPOINT}", f"{DATABASE_APP_NAME}:{ENDPOINT}"
    )

    async with ops_test.fast_forward("60s"):
        await ops_test.model.block_until(
            lambda: is_relation_joined(ops_test, ENDPOINT, ENDPOINT) is True,
            timeout=TIMEOUT,
        )

        logger.info("Waiting until both applications are active")

        await ops_test.model.block_until(
            lambda: ops_test.model.applications[DATABASE_APP_NAME].status == "active"
            and ops_test.model.applications[APPLICATION_APP_NAME].status == "active",
            timeout=TIMEOUT,
        )


@pytest.mark.abort_on_fail
async def test_relation_broken(ops_test: OpsTest):
    """Remove relation and wait for the expected changes in status."""
    # store database credentials for test access later
    credentials = await application_database_credentials(ops_test)

    logger.info(
        "Asserting that a connection to the database is still possible with application credentials"
    )

    assert is_connection_possible(credentials) is True

    await ops_test.model.applications[DATABASE_APP_NAME].remove_relation(
        f"{APPLICATION_APP_NAME}:{ENDPOINT}", f"{DATABASE_APP_NAME}:{ENDPOINT}"
    )

    logger.info(
        f"Removing relation {DATABASE_APP_NAME}:{ENDPOINT} with {APPLICATION_APP_NAME}:{ENDPOINT}"
    )

    await ops_test.model.block_until(
        lambda: is_relation_broken(ops_test, ENDPOINT, ENDPOINT) is True,
        timeout=TIMEOUT,
    )

    logger.info(
        f"Waiting till {DATABASE_APP_NAME} is active and {APPLICATION_APP_NAME} is waiting"
    )

    async with ops_test.fast_forward("60s"):
        await asyncio.gather(
            ops_test.model.wait_for_idle(
                apps=[DATABASE_APP_NAME],
                status="active",
                raise_on_blocked=True,
            ),
            ops_test.model.wait_for_idle(
                apps=[APPLICATION_APP_NAME],
                status="waiting",
                raise_on_blocked=True,
            ),
        )

    logger.info(
        "Asserting that a connection to the database is not possible with application credentials"
    )

    assert is_connection_possible(credentials) is False


async def application_database_credentials(ops_test: OpsTest) -> dict:
    unit = ops_test.model.applications[APPLICATION_APP_NAME].units[0]
    return await get_legacy_mysql_credentials(unit)
