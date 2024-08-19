#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import logging

import pytest
from pytest_operator.plugin import OpsTest

from .. import juju_
from .high_availability_helpers import (
    APPLICATION_DEFAULT_APP_NAME,
    deploy_and_scale_application,
    deploy_and_scale_mysql,
    get_application_name,
    relate_mysql_and_application,
)

logger = logging.getLogger(__name__)


@pytest.fixture()
async def continuous_writes(ops_test: OpsTest):
    """Starts continuous writes to the MySQL cluster for a test and clear the writes at the end."""
    application_name = get_application_name(ops_test, APPLICATION_DEFAULT_APP_NAME)

    application_unit = ops_test.model.applications[application_name].units[0]

    logger.info("Clearing continuous writes")
    await juju_.run_action(application_unit, "clear-continuous-writes", **{"timeout": 120})

    logger.info("Starting continuous writes")
    await juju_.run_action(application_unit, "start-continuous-writes")

    yield

    logger.info("Clearing continuous writes")
    await juju_.run_action(application_unit, "clear-continuous-writes")


@pytest.fixture()
async def highly_available_cluster(ops_test: OpsTest) -> None:
    """Run the set up for high availability tests.

    Args:
        ops_test: The ops test framework
    """
    logger.info("Deploying mysql and scaling to 3 units")
    mysql_application_name = await deploy_and_scale_mysql(ops_test)

    logger.info("Deploying mysql-test-app")
    application_name = await deploy_and_scale_application(ops_test)

    logger.info("Relating mysql with mysql-test-app")
    await relate_mysql_and_application(ops_test, mysql_application_name, application_name)

    yield
