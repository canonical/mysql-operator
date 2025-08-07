# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.


import logging
from pathlib import Path

import pytest
import yaml
from pytest_operator.plugin import OpsTest

from ..helpers import (
    get_primary_unit_wrapper,
    scale_application,
)
from .high_availability_helpers import (
    clean_up_database_and_table,
    ensure_all_units_continuous_writes_incrementing,
    ensure_n_online_mysql_members,
    get_application_name,
    insert_data_into_mysql_and_validate_replication,
)

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = METADATA["name"]
ANOTHER_APP_NAME = f"second{APP_NAME}"
TIMEOUT = 17 * 60


@pytest.mark.abort_on_fail
async def test_kill_primary_check_reelection(ops_test: OpsTest, highly_available_cluster) -> None:
    """Confirm that a new primary is elected when the current primary is torn down."""
    mysql_application_name = get_application_name(ops_test, "mysql")
    application = ops_test.model.applications[mysql_application_name]

    await ensure_all_units_continuous_writes_incrementing(ops_test)

    primary_unit = await get_primary_unit_wrapper(ops_test, mysql_application_name)
    primary_unit_name = primary_unit.name

    # Destroy the primary unit and block to ensure that the
    # juju status changed from active
    logger.info("Destroying leader unit")
    await ops_test.model.destroy_units(primary_unit.name)

    async with ops_test.fast_forward("60s"):
        await ops_test.model.block_until(lambda: len(application.units) == 2)
        await ops_test.model.wait_for_idle(
            apps=[mysql_application_name],
            status="active",
            raise_on_blocked=True,
            timeout=TIMEOUT,
        )

    # Wait for unit to be destroyed and confirm that the new primary unit is different
    new_primary_unit = await get_primary_unit_wrapper(ops_test, mysql_application_name)

    assert primary_unit_name != new_primary_unit.name, "Primary has not changed"

    # Add the unit back and wait until it is active
    async with ops_test.fast_forward("60s"):
        logger.info("Scaling back to 3 units")
        await scale_application(ops_test, mysql_application_name, 3)

        # wait (and retry) until the killed pod is back online in the mysql cluster
        assert await ensure_n_online_mysql_members(ops_test, 3), (
            "Old primary has not come back online after being killed"
        )

    await ensure_all_units_continuous_writes_incrementing(ops_test)

    database_name, table_name = "test-kill-primary-check-reelection", "data"
    await insert_data_into_mysql_and_validate_replication(ops_test, database_name, table_name)
    await clean_up_database_and_table(ops_test, database_name, table_name)
