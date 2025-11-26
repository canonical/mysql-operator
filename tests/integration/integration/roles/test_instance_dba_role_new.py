#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import logging

import jubilant_backports
import pytest
from jubilant_backports import Juju

from ...helpers_ha import (
    CHARM_METADATA,
    MINUTE_SECS,
    execute_queries_on_unit,
    get_app_units,
    get_mysql_primary_unit,
    get_unit_ip,
    wait_for_apps_status,
)

logger = logging.getLogger(__name__)

DATABASE_APP_NAME = CHARM_METADATA["name"]
INTEGRATOR_APP_NAME = "data-integrator"

TIMEOUT = 15 * MINUTE_SECS


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
        base="ubuntu@24.04",
    )

    juju.wait(
        ready=wait_for_apps_status(jubilant_backports.all_active, DATABASE_APP_NAME),
        timeout=TIMEOUT,
    )
    juju.wait(
        ready=wait_for_apps_status(jubilant_backports.all_blocked, INTEGRATOR_APP_NAME),
        timeout=TIMEOUT,
    )


@pytest.mark.abort_on_fail
def test_charmed_dba_role(juju: Juju):
    """Test the instance-level DBA role."""
    # configure integrator and relate
    juju.config(
        INTEGRATOR_APP_NAME, {"database-name": "charmed_dba_db", "extra-user-roles": "charmed_dba"}
    )
    juju.integrate(INTEGRATOR_APP_NAME, DATABASE_APP_NAME)

    juju.wait(
        ready=wait_for_apps_status(
            jubilant_backports.all_active, INTEGRATOR_APP_NAME, DATABASE_APP_NAME
        ),
        error=jubilant_backports.any_blocked,
        timeout=TIMEOUT,
    )

    mysql_unit = get_app_units(juju, DATABASE_APP_NAME)[0]
    primary_unit = get_mysql_primary_unit(juju, DATABASE_APP_NAME, mysql_unit)
    primary_unit_address = get_unit_ip(juju, DATABASE_APP_NAME, primary_unit)

    data_integrator_unit = get_app_units(juju, INTEGRATOR_APP_NAME)[0]
    task = juju.run(unit=data_integrator_unit, action="get-credentials")
    task.raise_on_failure()
    results = task.results

    logger.info("Checking that the instance-level DBA role can create new databases")
    execute_queries_on_unit(
        juju,
        primary_unit_address,
        results["mysql"]["username"],
        results["mysql"]["password"],
        ["CREATE DATABASE IF NOT EXISTS test"],
        commit=True,
    )

    data_integrator_unit = get_app_units(juju, INTEGRATOR_APP_NAME)[0]
    task = juju.run(unit=data_integrator_unit, action="get-credentials")
    task.raise_on_failure()
    results = task.results

    logger.info("Checking that the instance-level DBA role can see all databases")
    rows = execute_queries_on_unit(
        juju,
        primary_unit_address,
        results["mysql"]["username"],
        results["mysql"]["password"],
        ["SHOW DATABASES"],
        commit=True,
    )

    assert "test" in rows, "Database is not visible to DBA user"
