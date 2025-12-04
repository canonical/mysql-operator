#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import logging

import jubilant_backports
import pytest
from jubilant_backports import Juju
from mysql.connector.errors import ProgrammingError

from ...helpers import execute_queries_on_unit
from ...helpers_ha import (
    MINUTE_SECS,
    get_app_units,
    get_mysql_primary_unit,
    get_unit_ip,
    wait_for_apps_status,
)

logger = logging.getLogger(__name__)

DATABASE_APP_NAME = "mysql"
INTEGRATOR_APP_NAME = "data-integrator"

TIMEOUT = 15 * MINUTE_SECS

logging.getLogger("jubilant.wait").setLevel(logging.WARNING)


@pytest.mark.abort_on_fail
@pytest.mark.skip_if_deployed
def test_build_and_deploy(juju: Juju, charm) -> None:
    """Simple test to ensure that the mysql and data-integrator charms get deployed."""
    juju.deploy(
        charm,
        DATABASE_APP_NAME,
        num_units=3,
        base="ubuntu@22.04",
        config={"profile": "testing"},
    )
    juju.deploy(
        INTEGRATOR_APP_NAME,
        f"{INTEGRATOR_APP_NAME}1",
        base="ubuntu@24.04",
    )
    juju.deploy(
        INTEGRATOR_APP_NAME,
        f"{INTEGRATOR_APP_NAME}2",
        base="ubuntu@24.04",
    )

    juju.wait(
        ready=wait_for_apps_status(jubilant_backports.all_active, DATABASE_APP_NAME),
        timeout=TIMEOUT,
    )
    juju.wait(
        ready=wait_for_apps_status(
            jubilant_backports.all_blocked, f"{INTEGRATOR_APP_NAME}1", f"{INTEGRATOR_APP_NAME}2"
        ),
        timeout=TIMEOUT,
    )


@pytest.mark.abort_on_fail
async def test_charmed_dba_role(juju: Juju):
    """Test the database-level DBA role."""
    juju.config(f"{INTEGRATOR_APP_NAME}1", {"database-name": "preserved", "extra-user-roles": ""})
    juju.integrate(f"{INTEGRATOR_APP_NAME}1", DATABASE_APP_NAME)
    juju.wait(
        ready=wait_for_apps_status(
            jubilant_backports.all_active, f"{INTEGRATOR_APP_NAME}1", DATABASE_APP_NAME
        ),
        timeout=TIMEOUT,
    )

    juju.config(
        f"{INTEGRATOR_APP_NAME}2",
        {"database-name": "throwaway", "extra-user-roles": "charmed_dba_preserved_00"},
    )
    juju.integrate(f"{INTEGRATOR_APP_NAME}2", DATABASE_APP_NAME)
    juju.wait(
        ready=wait_for_apps_status(
            jubilant_backports.all_active, f"{INTEGRATOR_APP_NAME}2", DATABASE_APP_NAME
        ),
        timeout=TIMEOUT,
    )

    mysql_unit = get_app_units(juju, DATABASE_APP_NAME)[0]
    primary_unit = get_mysql_primary_unit(juju, DATABASE_APP_NAME, mysql_unit)
    primary_unit_address = get_unit_ip(juju, DATABASE_APP_NAME, primary_unit)

    data_integrator_2_unit = get_app_units(juju, f"{INTEGRATOR_APP_NAME}2")[0]
    task = juju.run(unit=data_integrator_2_unit, action="get-credentials")
    task.raise_on_failure()
    results = task.results

    logger.info("Checking that the database-level DBA role cannot create new databases")
    with pytest.raises(ProgrammingError):
        await execute_queries_on_unit(
            primary_unit_address,
            results["mysql"]["username"],
            results["mysql"]["password"],
            ["CREATE DATABASE IF NOT EXISTS test"],
            commit=True,
        )

    logger.info("Checking that the database-level DBA role can see all databases")
    await execute_queries_on_unit(
        primary_unit_address,
        results["mysql"]["username"],
        results["mysql"]["password"],
        ["SHOW DATABASES"],
        commit=True,
    )

    logger.info("Checking that the database-level DBA role can create a new table")
    await execute_queries_on_unit(
        primary_unit_address,
        results["mysql"]["username"],
        results["mysql"]["password"],
        [
            "CREATE TABLE preserved.test_table (`id` SERIAL PRIMARY KEY, `data` TEXT)",
        ],
        commit=True,
    )

    logger.info("Checking that the database-level DBA role can write into an existing table")
    await execute_queries_on_unit(
        primary_unit_address,
        results["mysql"]["username"],
        results["mysql"]["password"],
        [
            "INSERT INTO preserved.test_table (`data`) VALUES ('test_data_1'), ('test_data_2')",
        ],
        commit=True,
    )

    logger.info("Checking that the database-level DBA role can read from an existing table")
    rows = await execute_queries_on_unit(
        primary_unit_address,
        results["mysql"]["username"],
        results["mysql"]["password"],
        [
            "SELECT `data` FROM preserved.test_table",
        ],
        commit=True,
    )
    assert sorted(rows) == sorted(["test_data_1", "test_data_2"]), (
        "Unexpected data in preserved with charmed_dba_preserved_00 role"
    )
