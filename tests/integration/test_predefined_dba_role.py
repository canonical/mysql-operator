#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio

import pytest
from pytest_operator.plugin import OpsTest

from . import juju_
from .helpers import (
    execute_queries_on_unit,
    get_primary_unit,
    get_server_config_credentials,
)
from .relations.test_database import DATABASE_APP_NAME

DATA_INTEGRATOR_APP_NAME = "data-integrator"


@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest, charm) -> None:
    """Simple test to ensure that the mysql and data-integrator charms get deployed."""
    async with ops_test.fast_forward("10s"):
        await asyncio.gather(
            ops_test.model.deploy(
                charm,
                application_name=DATABASE_APP_NAME,
                num_units=3,
                base="ubuntu@22.04",
                config={"profile": "testing"},
            ),
            ops_test.model.deploy(
                DATA_INTEGRATOR_APP_NAME,
                base="ubuntu@22.04",
            ),
        )

    await ops_test.model.wait_for_idle(apps=[DATABASE_APP_NAME], status="active")
    await ops_test.model.wait_for_idle(apps=[DATA_INTEGRATOR_APP_NAME], status="blocked")


@pytest.mark.abort_on_fail
async def test_charmed_dba_role(ops_test: OpsTest):
    """Test the DBA predefined role."""
    await ops_test.model.applications[DATA_INTEGRATOR_APP_NAME].set_config({
        "database-name": "charmed_dba_database",
        "extra-user-roles": "charmed_dba",
    })
    await ops_test.model.add_relation(DATA_INTEGRATOR_APP_NAME, DATABASE_APP_NAME)
    await ops_test.model.wait_for_idle(
        apps=[DATA_INTEGRATOR_APP_NAME, DATABASE_APP_NAME], status="active"
    )

    mysql_unit = ops_test.model.applications[DATABASE_APP_NAME].units[-1]
    primary_unit = await get_primary_unit(ops_test, mysql_unit, DATABASE_APP_NAME)
    primary_unit_address = await primary_unit.get_public_address()
    server_config_credentials = await get_server_config_credentials(primary_unit)

    await execute_queries_on_unit(
        primary_unit_address,
        server_config_credentials["username"],
        server_config_credentials["password"],
        ["CREATE DATABASE IF NOT EXISTS test"],
        commit=True,
    )

    data_integrator_unit = ops_test.model.applications[DATA_INTEGRATOR_APP_NAME].units[0]
    results = await juju_.run_action(data_integrator_unit, "get-credentials")

    rows = await execute_queries_on_unit(
        primary_unit_address,
        results["mysql"]["username"],
        results["mysql"]["password"],
        ["SHOW DATABASES"],
        commit=True,
    )

    for row in rows:
        if row[0] == "test":
            break
    else:
        raise AssertionError()
