# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import pytest
from pytest_operator.plugin import OpsTest

from .backups import build_and_deploy_operations, pitr_operations


@pytest.mark.abort_on_fail
async def test_build_and_deploy_gcp(
    ops_test: OpsTest, cloud_configs_gcp: tuple[dict[str, str], dict[str, str]], charm
) -> None:
    """Build and deploy for AWS."""
    await build_and_deploy_operations(
        ops_test,
        charm,
        cloud_configs_gcp[0],
        cloud_configs_gcp[1],
    )


async def test_pitr_aws(
    ops_test: OpsTest, cloud_configs_gcp: tuple[dict[str, str], dict[str, str]]
) -> None:
    """Pitr tests."""
    await pitr_operations(ops_test, cloud_configs_gcp[0], cloud_configs_gcp[1])
