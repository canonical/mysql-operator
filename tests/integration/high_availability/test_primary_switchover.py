# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from subprocess import run

import pytest
from jubilant import Juju, all_active

from ..markers import juju3


@juju3
@pytest.mark.abort_on_fail
def test_cluster_switchover(juju: Juju, highly_available_cluster) -> None:
    """Test that the primary node can be switched over."""
    logging.info("Testing cluster switchover...")
    app_name = get_app_name(juju, "mysql")
    assert app_name, "MySQL application not found in the cluster"

    app_units = get_app_units(juju, app_name)
    assert len(app_units) > 1, "Not enough units to perform a switchover"

    primary_unit = get_primary_unit_name(juju, next(iter(app_units)))
    assert primary_unit, "No primary unit found in the cluster"
    logging.info(f"Current primary unit: {primary_unit}")

    logging.info("Selecting a new primary unit for switchover...")
    app_units.discard(primary_unit)
    new_primary_unit = app_units.pop()
    logging.info(f"New primary unit selected: {new_primary_unit}")

    switchover_task = juju.run(new_primary_unit, "promote-to-primary", {"scope": "unit"})
    assert switchover_task.status == "completed", "Switchover failed"

    assert get_primary_unit_name(juju, primary_unit) == new_primary_unit, "Switchover failed"


@juju3
@pytest.mark.abort_on_fail
def test_cluster_failover_after_majority_loss(juju: Juju, highly_available_cluster) -> None:
    """Test the promote-to-primary command after losing the majority of nodes, with force flag."""
    app_name = get_app_name(juju, "mysql")
    assert app_name, "MySQL application not found in the cluster"

    app_units = get_app_units(juju, app_name)
    assert len(app_units) > 1, "Not enough units to perform a switchover"

    primary_unit = get_primary_unit_name(juju, next(iter(app_units)))
    assert primary_unit, "No primary unit found in the cluster"
    logging.info(f"Current primary unit: {primary_unit}")

    non_primary_units = app_units - {primary_unit}

    unit_to_promote = non_primary_units.pop()

    logging.info(f"Unit selected for promotion: {unit_to_promote}")

    logging.info("Rebooting all but one unit to simulate majority loss...")
    for unit in [non_primary_units.pop(), primary_unit]:
        machine_name = get_unit_machine(juju, app_name, unit)
        run(["lxc", "restart", machine_name], check=True)

    failover_task = juju.run(
        unit_to_promote, "promote-to-primary", {"scope": "unit", "force": True}
    )

    juju.model_config({"update-status-hook-interval": "15s"})

    assert failover_task.status == "completed", "Switchover failed"
    logging.info("Waiting for all units to become active after switchover...")
    juju.wait(all_active, timeout=60 * 10, delay=5)

    assert get_primary_unit_name(juju, primary_unit) == unit_to_promote, "Failover failed"


def get_primary_unit_name(juju: Juju, mysql_unit) -> str | None:
    """Get the current primary node of the cluster."""
    cluster_status_task = juju.run(mysql_unit, "get-cluster-status")
    assert cluster_status_task.status == "completed", "Failed to retrieve cluster status"
    for label, value in cluster_status_task.results["status"]["defaultreplicaset"][
        "topology"
    ].items():
        if value["memberrole"] == "primary":
            return label.replace("-", "/")


def get_app_name(juju: Juju, charm_name: str) -> str | None:
    """Get the application name for the given charm."""
    status = juju.status()
    for app, value in status.apps.items():
        if value.charm_name == charm_name:
            return app


def get_app_units(juju: Juju, app_name: str) -> set[str]:
    """Get the units for the given application."""
    status = juju.status()
    assert app_name in status.apps, f"Application {app_name} not found in status"
    return set(status.apps[app_name].units.keys())


def get_unit_machine(juju: Juju, app_name: str, unit_name: str) -> str:
    """Get the machine name for the given unit."""
    status = juju.status()
    machine_id = status.apps[app_name].units[unit_name].machine
    return status.machines[machine_id].instance_id
