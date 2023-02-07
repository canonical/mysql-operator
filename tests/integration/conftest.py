#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import os
from pathlib import Path

import pytest
from pytest_operator.plugin import OpsTest

from .integration_constants import SERIES_TO_VERSION
from .read_charm_yaml import get_base_versions, get_charm_name


def pytest_addoption(parser):
    parser.addoption("--series", default="jammy")


@pytest.fixture
def series(pytestconfig) -> str:
    return pytestconfig.option.series


@pytest.fixture
def ops_test(ops_test: OpsTest, series: str) -> OpsTest:
    _build_charm_original = ops_test.build_charm
    if os.environ.get("CI") == "true":
        # Running in GitHub Actions; skip build step
        # (GitHub Actions uses a separate, cached build step. See .github/workflows/ci.yaml)
        async def build_charm(charm_path) -> Path:
            # Partially copied from
            # https://github.com/charmed-kubernetes/pytest-operator/blob/d78d6a3158f1ccb7c69ad8c19a0ce573dddbc4c3/pytest_operator/plugin.py#L913
            charm_path = Path(charm_path)
            charm_name = get_charm_name(charm_path / "metadata.yaml")
            available_versions = get_base_versions(charm_path / "charmcraft.yaml")
            version = SERIES_TO_VERSION[series]
            # "series" is only for the mysql charm, not the application charms
            if version not in available_versions:
                # Application charm version does not match mysql charm version
                # Use latest available version for application charm
                version = available_versions[-1]
            return f"local:./{charm_path/charm_name}_ubuntu-{version}-amd64.charm"

    else:

        async def build_charm(charm_path) -> Path:
            # Partially copied from
            # https://github.com/charmed-kubernetes/pytest-operator/blob/d78d6a3158f1ccb7c69ad8c19a0ce573dddbc4c3/pytest_operator/plugin.py#L913
            charm_path = Path(charm_path)
            available_versions = get_base_versions(charm_path / "charmcraft.yaml")
            version = SERIES_TO_VERSION[series]
            # "series" is only for the mysql charm, not the application charms
            if version not in available_versions:
                # Application charm version does not match mysql charm version
                # Use latest available version for application charm
                version = available_versions[-1]
            return await _build_charm_original(
                charm_path,
                bases_index=available_versions.index(version),
            )

    ops_test.build_charm = build_charm
    return ops_test
