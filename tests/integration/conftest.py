# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import pathlib

import pytest
import pytest_operator.plugin


@pytest.fixture(scope="session")
def mysql_charm_series(pytestconfig) -> str:
    return pytestconfig.option.mysql_charm_series


@pytest.fixture(scope="module")
def ops_test(
    ops_test: pytest_operator.plugin.OpsTest, pytestconfig
) -> pytest_operator.plugin.OpsTest:
    _build_charm = ops_test.build_charm

    async def build_charm(charm_path) -> pathlib.Path:
        if pathlib.Path(charm_path) == pathlib.Path("."):
            # Building mysql charm
            return await _build_charm(
                charm_path,
                bases_index=pytestconfig.option.mysql_charm_bases_index,
            )
        else:
            return await _build_charm(charm_path)

    ops_test.build_charm = build_charm
    return ops_test
