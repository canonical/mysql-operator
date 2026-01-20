# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import subprocess

import jubilant_backports
import pytest
from jubilant_backports import Juju

from ...helpers_ha import (
    get_app_name,
    get_app_units,
    get_mysql_primary_unit,
    get_unit_machine,
    update_interval,
    wait_for_apps_status,
    wait_for_unit_message,
    wait_for_unit_status,
)

MYSQL_APP_NAME = "mysql"
MYSQL_TEST_APP_NAME = "mysql-test-app"

MINUTE_SECS = 60


@pytest.mark.abort_on_fail
def test_deploy_highly_available_cluster(juju: Juju, charm: str) -> None:
    """Simple test to ensure that the MySQL and application charms get deployed."""
    logging.info("Deploying MySQL cluster")
    juju.deploy(
        charm=charm,
        app=MYSQL_APP_NAME,
        base="ubuntu@22.04",
        config={"profile": "testing"},
        num_units=3,
    )
    juju.deploy(
        charm=MYSQL_TEST_APP_NAME,
        app=MYSQL_TEST_APP_NAME,
        base="ubuntu@22.04",
        channel="latest/edge",
        config={"sleep_interval": 500},
        num_units=1,
    )

    juju.integrate(
        f"{MYSQL_APP_NAME}:database",
        f"{MYSQL_TEST_APP_NAME}:database",
    )

    logging.info("Wait for applications to become active")
    juju.wait(
        ready=wait_for_apps_status(
            jubilant_backports.all_active, MYSQL_APP_NAME, MYSQL_TEST_APP_NAME
        ),
        error=jubilant_backports.any_blocked,
        timeout=20 * MINUTE_SECS,
    )


@pytest.mark.abort_on_fail
def test_cluster_switchover(juju: Juju) -> None:
    """Test that the primary node can be switched over."""
    logging.info("Testing cluster switchover...")
    app_name = get_app_name(juju, "mysql")
    assert app_name, "MySQL application not found in the cluster"

    app_units = set(get_app_units(juju, app_name))
    assert len(app_units) > 1, "Not enough units to perform a switchover"

    primary_unit = get_mysql_primary_unit(juju, app_name)
    assert primary_unit, "No primary unit found in the cluster"
    logging.info(f"Current primary unit: {primary_unit}")

    logging.info("Selecting a new primary unit for switchover...")
    app_units.discard(primary_unit)
    new_primary_unit = app_units.pop()
    logging.info(f"New primary unit selected: {new_primary_unit}")

    juju.run(
        unit=new_primary_unit,
        action="promote-to-primary",
        params={"scope": "unit"},
    )

    assert get_mysql_primary_unit(juju, app_name) == new_primary_unit, "Switchover failed"


@pytest.mark.abort_on_fail
def test_cluster_failover_after_majority_loss(juju: Juju) -> None:
    """Test the promote-to-primary command after losing the majority of nodes, with force flag."""
    app_name = get_app_name(juju, "mysql")
    assert app_name, "MySQL application not found in the cluster"

    app_units = set(get_app_units(juju, app_name))
    assert len(app_units) > 1, "Not enough units to perform a switchover"

    primary_unit = get_mysql_primary_unit(juju, app_name)
    assert primary_unit, "No primary unit found in the cluster"
    logging.info(f"Current primary unit: {primary_unit}")

    non_primary_units = app_units - {primary_unit}

    unit_to_promote = non_primary_units.pop()

    logging.info(f"Unit selected for promotion: {unit_to_promote}")

    logging.info("Kill all but one unit to simulate majority loss...")
    units_to_kill = [non_primary_units.pop(), primary_unit]
    machine_name = []
    for unit in units_to_kill:
        machine_name.append(get_unit_machine(juju, app_name, unit))

    subprocess.run(["lxc", "restart", "--force", machine_name[0], machine_name[1]], check=True)

    with update_interval(juju, "45s"):
        logging.info("Waiting to settle in error state")
        juju.wait(
            ready=lambda status: all((
                wait_for_unit_status(app_name, unit_to_promote, "active")(status),
                wait_for_unit_message(app_name, units_to_kill[0], "OFFLINE")(status),
                wait_for_unit_message(app_name, units_to_kill[1], "OFFLINE")(status),
            )),
            timeout=15 * MINUTE_SECS,
            delay=15,
        )

    juju.run(
        unit=unit_to_promote,
        action="promote-to-primary",
        params={"scope": "unit", "force": True},
        wait=600,
    )

    with update_interval(juju, "15s"):
        logging.info("Waiting for all units to become active after switchover...")
        juju.wait(
            ready=jubilant_backports.all_active,
            timeout=10 * MINUTE_SECS,
            delay=5,
        )

    assert get_mysql_primary_unit(juju, app_name) == unit_to_promote, "Failover failed"
