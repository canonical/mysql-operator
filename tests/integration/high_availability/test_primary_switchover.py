# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from typing import Optional

import pytest
from jubilant import Juju

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


def get_primary_unit_name(juju: Juju, mysql_unit) -> Optional[str]:
    """Get the current primary node of the cluster."""
    cluster_status_task = juju.run(mysql_unit, "get-cluster-status")
    assert cluster_status_task.status == "completed", "Failed to retrieve cluster status"
    for label, value in cluster_status_task.results["status"]["defaultreplicaset"][
        "topology"
    ].items():
        if value["memberrole"] == "primary":
            return label.replace("-", "/")


def get_app_name(juju: Juju, charm_name: str) -> Optional[str]:
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
