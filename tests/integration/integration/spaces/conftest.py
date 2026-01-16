# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import os
import subprocess

import pytest
from pytest_operator.plugin import OpsTest

DEFAULT_LXD_NETWORK = "lxdbr0"
RAW_DNSMASQ = """
dhcp-option=3
dhcp-option=6
"""

logger = logging.getLogger(__name__)


def _lxd_network_up(name: str, subnet: str, external: bool = True):
    try:
        process = subprocess.run(
            [
                "sudo",
                "lxc",
                "network",
                "create",
                name,
                "--type=bridge",
                f"ipv4.address={subnet}",
                f"ipv4.nat={external}".lower(),
                "ipv6.address=none",
                "dns.mode=none",
            ],
            capture_output=True,
            check=True,
            encoding="utf-8",
        )
        logger.info(f"LXD network created: {process.stdout}")

        process = subprocess.run(
            ["sudo", "lxc", "network", "show", name],
            capture_output=True,
            check=True,
            encoding="utf-8",
        )
        logger.debug(f"LXD network status: {process.stdout}")

        if not external:
            subprocess.check_output(
                ["sudo", "lxc", "network", "set", name, "raw.dnsmasq", RAW_DNSMASQ],
            )

        subprocess.check_output(["sudo", "ip", "link", "set", "up", "dev", name])
    except subprocess.CalledProcessError as e:
        logger.error(f"Error creating LXD network {name} with: {e.returncode} {e.stderr}")
        raise


def _lxd_network_down(name: str):
    try:
        subprocess.check_output(["sudo", "lxc", "network", "delete", name])
    except subprocess.CalledProcessError as e:
        logger.warning(f"Error deleting LXD network with: {e.returncode} {e.stderr}")


@pytest.hookimpl()
def pytest_sessionstart(session):
    subprocess.run(
        ["sudo", "lxc", "network", "set", DEFAULT_LXD_NETWORK, "dns.mode=none"],
        check=True,
    )

    _lxd_network_up("client", "10.0.0.1/24", True)
    _lxd_network_up("peers", "10.10.10.1/24", False)
    _lxd_network_up("isolated", "10.20.20.1/24", False)


@pytest.hookimpl()
def pytest_sessionfinish(session, exitstatus):
    # Nothing to do, as this is a temp runner only
    if os.environ.get("CI", "").lower() == "true":
        return

    _lxd_network_down("client")
    _lxd_network_down("peers")
    _lxd_network_down("isolated")

    subprocess.run(
        ["sudo", "lxc", "network", "unset", DEFAULT_LXD_NETWORK, "dns.mode=none"],
        check=True,
    )


# TODO: Delete before merging
@pytest.fixture(scope="module")
async def lxd_spaces(ops_test: OpsTest):
    await ops_test.juju("reload-spaces")
    await ops_test.model.add_space("client", cidrs=["10.0.0.0/24"])
    await ops_test.model.add_space("peers", cidrs=["10.10.10.0/24"])
    await ops_test.model.add_space("isolated", cidrs=["10.20.20.0/24"])
