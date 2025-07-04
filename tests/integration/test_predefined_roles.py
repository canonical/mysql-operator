#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import logging

import pytest
from mysql.connector.errors import OperationalError
from pytest_operator.plugin import OpsTest

from . import juju_
from .helpers import (
    execute_queries_on_unit,
    get_primary_unit,
    get_server_config_credentials,
)
from .relations.test_database import DATABASE_APP_NAME

logger = logging.getLogger(__name__)

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
                application_name=f"{DATA_INTEGRATOR_APP_NAME}-1",
                base="ubuntu@22.04",
            ),
            ops_test.model.deploy(
                DATA_INTEGRATOR_APP_NAME,
                application_name=f"{DATA_INTEGRATOR_APP_NAME}-2",
                base="ubuntu@22.04",
            ),
        )

    await ops_test.model.wait_for_idle(
        apps=[DATABASE_APP_NAME],
        status="active",
    )
    await ops_test.model.wait_for_idle(
        apps=[f"{DATA_INTEGRATOR_APP_NAME}-1", f"{DATA_INTEGRATOR_APP_NAME}-2"],
        status="blocked",
    )


@pytest.mark.abort_on_fail
async def test_charmed_read_role(ops_test: OpsTest):
    """Test the charmed_read predefined role."""
    await ops_test.model.applications[f"{DATA_INTEGRATOR_APP_NAME}-1"].set_config({
        "database-name": "charmed_read_database",
        "extra-user-roles": "charmed_read",
    })
    await ops_test.model.add_relation(f"{DATA_INTEGRATOR_APP_NAME}-1", DATABASE_APP_NAME)
    await ops_test.model.wait_for_idle(
        apps=[f"{DATA_INTEGRATOR_APP_NAME}-1", DATABASE_APP_NAME],
        status="active",
    )

    mysql_unit = ops_test.model.applications[DATABASE_APP_NAME].units[-1]
    primary_unit = await get_primary_unit(ops_test, mysql_unit, DATABASE_APP_NAME)
    primary_unit_address = await primary_unit.get_public_address()
    server_config_credentials = await get_server_config_credentials(primary_unit)

    await execute_queries_on_unit(
        primary_unit_address,
        server_config_credentials["username"],
        server_config_credentials["password"],
        [
            "CREATE TABLE charmed_read_database.test_table (id SERIAL PRIMARY KEY, data TEXT)"
            "INSERT INTO charmed_read_database.test_table (data) VALUES ('test_data_1'), ('test_data_2')"
        ],
        commit=True,
    )

    data_integrator_unit = ops_test.model.applications[DATA_INTEGRATOR_APP_NAME].units[0]
    results = await juju_.run_action(data_integrator_unit, "get-credentials")

    logger.info("Checking that the charmed_read role can read from the database")
    rows = await execute_queries_on_unit(
        primary_unit_address,
        results["mysql"]["username"],
        results["mysql"]["password"],
        ["SELECT data FROM test_table"],
        commit=True,
    )
    assert sorted(row[0] for row in rows) == sorted([
        "test_data_1",
        "test_data_2",
    ]), "Unexpected data in charmed_read_database with charmed_read role"

    logger.info("Checking that the charmed_read role cannot create a new table")
    with pytest.raises(OperationalError):
        await execute_queries_on_unit(
            primary_unit_address,
            results["mysql"]["username"],
            results["mysql"]["password"],
            [
                "CREATE TABLE charmed_read_database.new_table (id SERIAL PRIMARY KEY, data TEXT)",
            ],
            commit=True,
        )

    logger.info("Checking that the charmed_read role cannot write to an existing table")
    with pytest.raises(OperationalError):
        await execute_queries_on_unit(
            primary_unit_address,
            results["mysql"]["username"],
            results["mysql"]["password"],
            [
                "INSERT INTO charmed_read_database.test_table (data) VALUES ('test_data_3'), ('test_data_4')",
            ],
            commit=True,
        )

    await ops_test.model.applications[DATABASE_APP_NAME].remove_relation(
        f"{DATABASE_APP_NAME}:database",
        f"{DATA_INTEGRATOR_APP_NAME}-1:mysql",
    )
    await ops_test.model.wait_for_idle(apps=[f"{DATA_INTEGRATOR_APP_NAME}-1"], status="blocked")


@pytest.mark.abort_on_fail
async def test_charmed_dml_role(ops_test: OpsTest):
    """Test the charmed_dml role."""
    await ops_test.model.applications[f"{DATA_INTEGRATOR_APP_NAME}-1"].set_config({
        "database-name": "charmed_dml_database",
    })
    await ops_test.model.add_relation(f"{DATA_INTEGRATOR_APP_NAME}-1", DATABASE_APP_NAME)
    await ops_test.model.wait_for_idle(
        apps=[f"{DATA_INTEGRATOR_APP_NAME}-1", DATABASE_APP_NAME],
        status="active",
    )

    await ops_test.model.applications[f"{DATA_INTEGRATOR_APP_NAME}-2"].set_config({
        "database-name": "throwaway",
        "extra-user-roles": "charmed_dml",
    })
    await ops_test.model.add_relation(f"{DATA_INTEGRATOR_APP_NAME}-2", DATABASE_APP_NAME)
    await ops_test.model.wait_for_idle(
        apps=[f"{DATA_INTEGRATOR_APP_NAME}-2", DATABASE_APP_NAME],
        status="active",
    )

    data_integrator_1_unit = ops_test.model.applications[f"{DATA_INTEGRATOR_APP_NAME}-1"].units[0]
    data_integrator_1_unit_address = await data_integrator_1_unit.get_public_address()
    results = await juju_.run_action(data_integrator_1_unit, "get-credentials")

    rows = await execute_queries_on_unit(
        data_integrator_1_unit_address,
        results["mysql"]["username"],
        results["mysql"]["password"],
        [
            "CREATE TABLE charmed_dml_database.test_table (id SERIAL PRIMARY KEY, data TEXT)"
            "INSERT INTO charmed_dml_database.test_table (data) VALUES ('test_data_1'), ('test_data_2')"
            "SELECT data FROM charmed_dml_database.test_table"
        ],
        commit=True,
    )
    assert sorted(row[0] for row in rows) == sorted([
        "test_data_1",
        "test_data_2",
    ]), "Unexpected data in charmed_dml_database with charmed_dml role"

    data_integrator_2_unit = ops_test.model.applications[f"{DATA_INTEGRATOR_APP_NAME}-2"].units[0]
    data_integrator_2_unit_address = await data_integrator_2_unit.get_public_address()
    results = await juju_.run_action(data_integrator_2_unit, "get-credentials")

    logger.info("Checking that the charmed_dml role can write to an existing table")
    await execute_queries_on_unit(
        data_integrator_2_unit_address,
        results["mysql"]["username"],
        results["mysql"]["password"],
        [
            "INSERT INTO charmed_dml_database.test_table (data) VALUES ('test_data_3')",
        ],
        commit=True,
    )

    await ops_test.model.applications[DATABASE_APP_NAME].remove_relation(
        f"{DATABASE_APP_NAME}:database",
        f"{DATA_INTEGRATOR_APP_NAME}-1:mysql",
    )
    await ops_test.model.applications[DATABASE_APP_NAME].remove_relation(
        f"{DATABASE_APP_NAME}:database",
        f"{DATA_INTEGRATOR_APP_NAME}-2:mysql",
    )
    await ops_test.model.wait_for_idle(
        apps=[f"{DATA_INTEGRATOR_APP_NAME}-1", f"{DATA_INTEGRATOR_APP_NAME}-2"],
        status="blocked",
    )
