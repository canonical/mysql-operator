# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import argparse


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
        raise argparse.ArgumentError(
            None, "--mysql-charm-series and --mysql-charm-bases-index must be given together"
        )
    # Note: Update defaults whenever charmcraft.yaml is changed
    if config.option.mysql_charm_series is None:
        config.option.mysql_charm_series = "jammy"
    if config.option.mysql_charm_bases_index is None:
        config.option.mysql_charm_bases_index = 0
