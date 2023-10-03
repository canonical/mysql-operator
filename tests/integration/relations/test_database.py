#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import logging
from pathlib import Path

import pytest
import yaml
from pytest_operator.plugin import OpsTest
from tenacity import AsyncRetrying, RetryError, stop_after_delay, wait_fixed

from constants import (
    DB_RELATION_NAME,
    PASSWORD_LENGTH,
    ROOT_USERNAME,
    SERVER_CONFIG_USERNAME,
)
from utils import generate_random_password

from ..helpers import (
    check_read_only_endpoints,
    execute_queries_on_unit,
    fetch_credentials,
    get_primary_unit,
    get_relation_data,
    is_relation_broken,
    is_relation_joined,
    remove_leader_unit,
    rotate_credentials,
    scale_application,
)

logger = logging.getLogger(__name__)

DB_METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
DATABASE_APP_NAME = DB_METADATA["name"]
CLUSTER_NAME = "test_cluster"

APPLICATION_APP_NAME = "mysql-test-app"

APPS = [DATABASE_APP_NAME, APPLICATION_APP_NAME]

ENDPOINT = "database"
TIMEOUT = 15 * 60


@pytest.mark.group(1)
@pytest.mark.abort_on_fail
@pytest.mark.skip_if_deployed
async def test_build_and_deploy(ops_test: OpsTest, mysql_charm_series: str) -> None:
    """Build the charm and deploy 3 units to ensure a cluster is formed."""
    db_charm = await ops_test.build_charm(".")

    config = {"cluster-name": CLUSTER_NAME, "profile": "testing"}

    await asyncio.gather(
        ops_test.model.deploy(
            db_charm,
            application_name=DATABASE_APP_NAME,
            config=config,
            num_units=3,
            series=mysql_charm_series,
        ),
        ops_test.model.deploy(
            APPLICATION_APP_NAME,
            application_name=APPLICATION_APP_NAME,
            num_units=2,
            channel="latest/edge",
        ),
    )

    # Reduce the update_status frequency until the cluster is deployed
    async with ops_test.fast_forward("60s"):
        await ops_test.model.block_until(
            lambda: len(ops_test.model.applications[DATABASE_APP_NAME].units) == 3
        )

        await ops_test.model.block_until(
            lambda: len(ops_test.model.applications[APPLICATION_APP_NAME].units) == 2
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

    assert len(ops_test.model.applications[APPLICATION_APP_NAME].units) == 2


@pytest.mark.group(1)
@pytest.mark.abort_on_fail
async def test_password_rotation(ops_test: OpsTest):
    """Rotate password and confirm changes."""
    random_unit = ops_test.model.applications[DATABASE_APP_NAME].units[-1]

    old_credentials = await fetch_credentials(random_unit, SERVER_CONFIG_USERNAME)

    # get primary unit first, need that to invoke set-password action
    primary_unit = await get_primary_unit(ops_test, random_unit, DATABASE_APP_NAME)
    primary_unit_address = await primary_unit.get_public_address()
    logger.debug(
        "Test succeeded Primary unit detected before password rotation is %s", primary_unit_address
    )

    new_password = generate_random_password(PASSWORD_LENGTH)

    await rotate_credentials(
        unit=primary_unit, username=SERVER_CONFIG_USERNAME, password=new_password
    )

    updated_credentials = await fetch_credentials(random_unit, SERVER_CONFIG_USERNAME)
    assert updated_credentials["password"] != old_credentials["password"]
    assert updated_credentials["password"] == new_password

    # verify that the new password actually works by querying the db
    show_tables_sql = [
        "SHOW DATABASES",
    ]
    output = await execute_queries_on_unit(
        primary_unit_address,
        updated_credentials["username"],
        updated_credentials["password"],
        show_tables_sql,
    )
    assert len(output) > 0, "query with new password failed, no databases found"


@pytest.mark.group(1)
@pytest.mark.abort_on_fail
async def test_password_rotation_silent(ops_test: OpsTest):
    """Rotate password and confirm changes."""
    random_unit = ops_test.model.applications[DATABASE_APP_NAME].units[-1]

    old_credentials = await fetch_credentials(random_unit, SERVER_CONFIG_USERNAME)

    # get primary unit first, need that to invoke set-password action
    primary_unit = await get_primary_unit(ops_test, random_unit, DATABASE_APP_NAME)
    primary_unit_address = await primary_unit.get_public_address()
    logger.debug(
        "Test succeeded Primary unit detected before password rotation is %s", primary_unit_address
    )

    await rotate_credentials(unit=primary_unit, username=SERVER_CONFIG_USERNAME)

    updated_credentials = await fetch_credentials(random_unit, SERVER_CONFIG_USERNAME)
    assert updated_credentials["password"] != old_credentials["password"]

    # verify that the new password actually works by querying the db
    show_tables_sql = [
        "SHOW DATABASES",
    ]
    output = await execute_queries_on_unit(
        primary_unit_address,
        updated_credentials["username"],
        updated_credentials["password"],
        show_tables_sql,
    )
    assert len(output) > 0, "query with new password failed, no databases found"


@pytest.mark.group(1)
@pytest.mark.abort_on_fail
async def test_password_rotation_root_user_implicit(ops_test: OpsTest):
    """Rotate password and confirm changes."""
    random_unit = ops_test.model.applications[DATABASE_APP_NAME].units[-1]

    root_credentials = await fetch_credentials(random_unit, ROOT_USERNAME)

    old_credentials = await fetch_credentials(random_unit)
    assert old_credentials["password"] == root_credentials["password"]

    # get primary unit first, need that to invoke set-password action
    primary_unit = await get_primary_unit(ops_test, random_unit, DATABASE_APP_NAME)
    primary_unit_address = await primary_unit.get_public_address()
    logger.debug(
        "Test succeeded Primary unit detected before password rotation is %s", primary_unit_address
    )

    await rotate_credentials(unit=primary_unit)

    updated_credentials = await fetch_credentials(random_unit)
    assert updated_credentials["password"] != old_credentials["password"]

    updated_root_credentials = await fetch_credentials(random_unit, ROOT_USERNAME)
    assert updated_credentials["password"] == updated_root_credentials["password"]


@pytest.mark.group(1)
@pytest.mark.abort_on_fail
@pytest.mark.usefixtures("only_without_juju_secrets")
async def test_relation_creation_databag(ops_test: OpsTest):
    """Relate charms and wait for the expected changes in status."""
    await ops_test.model.relate(
        f"{APPLICATION_APP_NAME}:{ENDPOINT}", f"{DATABASE_APP_NAME}:{ENDPOINT}"
    )

    async with ops_test.fast_forward("60s"):
        await ops_test.model.block_until(
            lambda: is_relation_joined(ops_test, ENDPOINT, ENDPOINT) == True  # noqa: E712
        )

        await ops_test.model.wait_for_idle(apps=APPS, status="active")

    relation_data = await get_relation_data(ops_test, APPLICATION_APP_NAME, "database")
    assert set(["password", "username"]) <= set(relation_data[0]["application-data"])


@pytest.mark.group(1)
@pytest.mark.abort_on_fail
@pytest.mark.usefixtures("only_with_juju_secrets")
async def test_relation_creation(ops_test: OpsTest):
    """Relate charms and wait for the expected changes in status."""
    await ops_test.model.relate(
        f"{APPLICATION_APP_NAME}:{ENDPOINT}", f"{DATABASE_APP_NAME}:{ENDPOINT}"
    )

    async with ops_test.fast_forward("60s"):
        await ops_test.model.block_until(
            lambda: is_relation_joined(ops_test, ENDPOINT, ENDPOINT) == True  # noqa: E712
        )

        await ops_test.model.wait_for_idle(apps=APPS, status="active")

    relation_data = await get_relation_data(ops_test, APPLICATION_APP_NAME, "database")
    assert not set(["password", "username"]) <= set(relation_data[0]["application-data"])
    assert "secret-user" in relation_data[0]["application-data"]


@pytest.mark.group(1)
@pytest.mark.abort_on_fail
async def test_read_only_endpoints(ops_test: OpsTest):
    """Check read-only-endpoints are correctly updated."""
    relation_data = await get_relation_data(
        ops_test=ops_test, application_name=DATABASE_APP_NAME, relation_name=DB_RELATION_NAME
    )
    assert len(relation_data) == 1
    await check_read_only_endpoints(
        ops_test=ops_test, app_name=DATABASE_APP_NAME, relation_name=DB_RELATION_NAME
    )

    # increase the number of units
    async with ops_test.fast_forward("60s"):
        await scale_application(ops_test, DATABASE_APP_NAME, 4)
    await check_read_only_endpoints(
        ops_test=ops_test, app_name=DATABASE_APP_NAME, relation_name=DB_RELATION_NAME
    )

    # decrease the number of units
    async with ops_test.fast_forward("60s"):
        await scale_application(ops_test, DATABASE_APP_NAME, 2)

    # wait for the update of the endpoints
    try:
        async for attempt in AsyncRetrying(stop=stop_after_delay(5 * 60), wait=wait_fixed(20)):
            with attempt:
                # check update for read-only-endpoints
                await check_read_only_endpoints(
                    ops_test=ops_test, app_name=DATABASE_APP_NAME, relation_name=DB_RELATION_NAME
                )
    except RetryError:
        assert False

    # increase the number of units
    async with ops_test.fast_forward("60s"):
        await scale_application(ops_test, DATABASE_APP_NAME, 3)

    # remove the leader unit
    await remove_leader_unit(ops_test=ops_test, application_name=DATABASE_APP_NAME)

    # wait for the update of the endpoints
    try:
        async for attempt in AsyncRetrying(stop=stop_after_delay(5 * 60), wait=wait_fixed(20)):
            with attempt:
                # check update for read-only-endpoints
                await check_read_only_endpoints(
                    ops_test=ops_test, app_name=DATABASE_APP_NAME, relation_name=DB_RELATION_NAME
                )
    except RetryError:
        assert False


@pytest.mark.group(1)
@pytest.mark.abort_on_fail
async def test_relation_broken(ops_test: OpsTest):
    """Remove relation and wait for the expected changes in status."""
    await ops_test.model.applications[DATABASE_APP_NAME].remove_relation(
        f"{APPLICATION_APP_NAME}:{ENDPOINT}", f"{DATABASE_APP_NAME}:{ENDPOINT}"
    )

    await ops_test.model.block_until(
        lambda: is_relation_broken(ops_test, ENDPOINT, ENDPOINT) is True
    )

    async with ops_test.fast_forward("60s"):
        await asyncio.gather(
            ops_test.model.wait_for_idle(
                apps=[DATABASE_APP_NAME], status="active", raise_on_blocked=True
            ),
            ops_test.model.wait_for_idle(
                apps=[APPLICATION_APP_NAME], status="waiting", raise_on_blocked=True
            ),
        )
