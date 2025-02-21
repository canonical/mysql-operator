# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.


import logging
from pathlib import Path

import pytest
import yaml
from pytest_operator.plugin import OpsTest

from .high_availability_helpers import (
    clean_up_database_and_table,
    ensure_all_units_continuous_writes_incrementing,
    get_application_name,
    insert_data_into_mysql_and_validate_replication,
)

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = METADATA["name"]
ANOTHER_APP_NAME = f"second{APP_NAME}"
TIMEOUT = 17 * 60


@pytest.mark.abort_on_fail
async def test_consistent_data_replication_across_cluster(
    ops_test: OpsTest, highly_available_cluster
) -> None:
    """Confirm that data is replicated from the primary node to all the replicas."""
    mysql_application_name = get_application_name(ops_test, "mysql")

    # assert that there are 3 units in the mysql cluster
    assert len(ops_test.model.applications[mysql_application_name].units) == 3

    database_name, table_name = "test-check-consistency", "data"
    await insert_data_into_mysql_and_validate_replication(ops_test, database_name, table_name)
    await clean_up_database_and_table(ops_test, database_name, table_name)

    await ensure_all_units_continuous_writes_incrementing(ops_test)
