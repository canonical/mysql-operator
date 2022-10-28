#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.


def pytest_addoption(parser):
    parser.addoption("--series", action="store", type=str, default="jammy")


def pytest_generate_tests(metafunc):
    series = metafunc.config.option.series
    # Only set "series" if it exists as a fixture for a test
    if "series" in metafunc.fixturenames:
        metafunc.parametrize("series", [series])
