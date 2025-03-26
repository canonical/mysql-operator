# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.


import logging
from pathlib import Path

import pytest
import yaml
from pytest_operator.plugin import OpsTest

from ..helpers import (
    retrieve_database_variable_value,
)
from .high_availability_helpers import (
    get_application_name,
)

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = METADATA["name"]
ANOTHER_APP_NAME = f"second{APP_NAME}"
TIMEOUT = 17 * 60


@pytest.mark.abort_on_fail
async def test_custom_variables(ops_test: OpsTest, highly_available_cluster) -> None:
    """Query database for custom variables."""
    mysql_application_name = get_application_name(ops_test, "mysql")
    application = ops_test.model.applications[mysql_application_name]

    for unit in application.units:
        custom_vars = {}
        custom_vars["max_connections"] = 100
        for k, v in custom_vars.items():
            logger.info(f"Checking that {k} is set to {v} on {unit.name}")
            value = await retrieve_database_variable_value(ops_test, unit, k)
            assert value == v, f"Variable {k} is not set to {v}"
