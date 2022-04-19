#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.


import logging
from pathlib import Path

import pytest
import yaml
from pytest_operator.plugin import OpsTest

from tests.integration.helpers import run_command_on_unit

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = METADATA["name"]


@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest):
    """Build the charm-under-test and deploy it together with related charms.

    Assert on the unit status before any relations/configurations take place.
    """
    # build and deploy charm from local source folder
    charm = await ops_test.build_charm(".")
    await ops_test.model.deploy(charm, application_name=APP_NAME, num_units=3)

    # issuing dummy update_status just to trigger an event
    await ops_test.model.set_config({"update-status-hook-interval": "10s"})

    await ops_test.model.wait_for_idle(
        apps=[APP_NAME],
        status="active",
        raise_on_blocked=True,
        timeout=1000,
    )
    assert len(ops_test.model.applications[APP_NAME].units) == 3
    assert ops_test.model.applications[APP_NAME].units[0].workload_status == "active"
    assert ops_test.model.applications[APP_NAME].units[1].workload_status == "active"
    assert ops_test.model.applications[APP_NAME].units[2].workload_status == "active"

    # effectively disable the update status from firing
    await ops_test.model.set_config({"update-status-hook-interval": "60m"})


@pytest.mark.abort_on_fail
async def test_database_package_installation(ops_test: OpsTest):
    """Confirm that the charm units contain installed software."""
    # Test each MySQL unit
    for unit in ops_test.model.applications[APP_NAME].units:
        # Ensure that mysql-server is installed correctly
        result = await run_command_on_unit(unit, "mysqld --version")
        mysql_version = result.strip().split()
        assert mysql_version[2] == "8.0.28-0ubuntu0.20.04.3"

        # Ensure that mysql-shell is installed correctly
        result = await run_command_on_unit(unit, "mysqlsh --version")
        mysqlsh_version = result.strip().split()
        assert mysqlsh_version[2] == "8.0.23"
