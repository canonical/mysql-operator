# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
from argparse import ArgumentError


def pytest_addoption(parser):
    parser.addoption(
        "--collect-groups",
        action="store_true",
        help="Collect test groups (used by GitHub Actions)",
    )
    parser.addoption("--group", type=int, help="Integration test group number")
    parser.addoption("--mysql-charm-series", help="Ubuntu series for mysql charm (e.g. jammy)")
    parser.addoption(
        "--mysql-charm-bases-index",
        type=int,
        help="Index of charmcraft.yaml base that matches --mysql-charm-series",
    )


def pytest_configure(config):
    if config.option.collect_groups:
        config.option.collectonly = True
    if (config.option.mysql_charm_series is None) ^ (
        config.option.mysql_charm_bases_index is None
    ):
        raise ArgumentError(
            None, "--mysql-charm-series and --mysql-charm-bases-index must be given together"
        )
    # Note: Update defaults whenever charmcraft.yaml is changed
    if config.option.mysql_charm_series is None:
        config.option.mysql_charm_series = "jammy"
    if config.option.mysql_charm_bases_index is None:
        config.option.mysql_charm_bases_index = 0
