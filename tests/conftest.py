#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
import os
from pathlib import Path

import pytest
import yaml
from pytest_operator.plugin import OpsTest

from tests.integration.integration_constants import SERIES_TO_VERSION


def pytest_addoption(parser):
    parser.addoption("--series", action="store", type=str, default="jammy")


def pytest_generate_tests(metafunc):
    series = metafunc.config.option.series
    # Only set "series" if it exists as a fixture for a test
    if "series" in metafunc.fixturenames:
        metafunc.parametrize("series", [series])


@pytest.fixture
def ops_test(ops_test: OpsTest, series: str) -> OpsTest:
    if os.environ.get("CI") == "true":
        # Running in GitHub Actions; skip build step
        # (GitHub Actions uses a separate, cached build step. See .github/workflows/ci.yaml)
        def build_charm(charm_path):
            # Partially copied from
            # https://github.com/charmed-kubernetes/pytest-operator/blob/main/pytest_operator/plugin.py#L920
            charm_path = Path(charm_path)
            metadata_path = charm_path / "metadata.yaml"
            charm_name = yaml.safe_load(metadata_path.read_text())["name"]
            return f"local:{charm_name}_ubuntu-{SERIES_TO_VERSION[series]}-amd64.charm"

        ops_test.build_charm = build_charm
    return ops_test
