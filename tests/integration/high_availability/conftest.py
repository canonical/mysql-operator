#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import pytest
from pytest_operator.plugin import OpsTest

from .high_availability_helpers import (
    APPLICATION_DEFAULT_APP_NAME,
    get_application_name,
)


@pytest.fixture()
async def continuous_writes(ops_test: OpsTest):
    """Starts continuous writes to the MySQL cluster for a test and clear the writes at the end."""
    application_name = get_application_name(ops_test, APPLICATION_DEFAULT_APP_NAME)

    application_unit = ops_test.model.applications[application_name].units[0]

    clear_writes_action = await application_unit.run_action("clear-continuous-writes")
    await clear_writes_action.wait()

    start_writes_action = await application_unit.run_action("start-continuous-writes")
    await start_writes_action.wait()

    yield

    clear_writes_action = await application_unit.run_action("clear-continuous-writes")
    await clear_writes_action.wait()
