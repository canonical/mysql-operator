#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import os
from argparse import ArgumentError
from pathlib import Path

import pytest
from pytest_operator.plugin import OpsTest


def pytest_addoption(parser):
    parser.addoption("--mysql-charm-series", help="Ubuntu series for mysql charm (e.g. jammy)")
    parser.addoption(
        "--mysql-charm-bases-index",
        type=int,
        help="Index of charmcraft.yaml base that matches --mysql-charm-series",
    )


def pytest_configure(config):
    if (config.option.mysql_charm_series is None) ^ (
        config.option.mysql_charm_bases_index is None
    ):
        raise ArgumentError(
            None, "--mysql-charm-series and --mysql-charm-bases-index must be given together"
        )
    # Update defaults whenever charmcraft.yaml is changed
    if config.option.mysql_charm_series is None:
        config.option.mysql_charm_series = "jammy"
    if config.option.mysql_charm_bases_index is None:
        config.option.mysql_charm_bases_index = 1


@pytest.fixture
def mysql_charm_series(pytestconfig) -> str:
    return pytestconfig.option.mysql_charm_series


@pytest.fixture
def ops_test(ops_test: OpsTest, pytestconfig) -> OpsTest:
    if os.environ.get("CI") == "true":
        # Running in GitHub Actions; skip build step
        # (GitHub Actions uses a separate, cached build step. See .github/workflows/ci.yaml)
        build_matrix = json.loads(os.environ["CI_BUILD_MATRIX"])

        async def _build_charm(charm_path, bases_index: int = None) -> Path:
            for charm in build_matrix.values():
                if Path(charm_path) == Path(charm["directory_path"]):
                    if bases_index is None or bases_index == charm["bases_index"]:
                        return charm["file_name"]
            raise ValueError(f"Unable to find .charm file for {bases_index=} at {charm_path=}")

    else:
        _build_charm = ops_test.build_charm

    async def build_charm(charm_path) -> Path:
        if Path(charm_path) == Path("."):
            # Building mysql charm
            return await _build_charm(
                charm_path,
                bases_index=pytestconfig.option.mysql_charm_bases_index,
            )
        else:
            return await _build_charm(charm_path)

    ops_test.build_charm = build_charm
    return ops_test
