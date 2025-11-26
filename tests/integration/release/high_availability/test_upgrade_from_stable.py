# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import os
from collections.abc import Generator
from contextlib import contextmanager

import jubilant_backports
import pytest
from jubilant_backports import Juju

from ... import architecture, markers
from ...helpers_ha import (
    check_mysql_units_writes_increment,
    get_app_leader,
    get_mysql_primary_unit,
    wait_for_apps_status,
)

MYSQL_APP_NAME = "mysql"
MYSQL_TEST_APP_NAME = "mysql-test-app"

MINUTE_SECS = 60

logging.getLogger("jubilant.wait").setLevel(logging.WARNING)


@contextmanager
def continuous_writes(juju: Juju) -> Generator:
    """Starts continuous writes to the MySQL cluster for a test and clear the writes at the end."""
    test_app_leader = get_app_leader(juju, MYSQL_TEST_APP_NAME)

    logging.info("Clearing continuous writes")
    juju.run(test_app_leader, "clear-continuous-writes")
    logging.info("Starting continuous writes")
    juju.run(test_app_leader, "start-continuous-writes")

    yield

    logging.info("Clearing continuous writes")
    juju.run(test_app_leader, "clear-continuous-writes")


@markers.amd64_only
def test_upgrade_from_stable_amd(juju: Juju, charm: str):
    """Simple test to ensure that all MySQL stable revisions can be upgraded."""
    revision = os.getenv("CHARM_REVISION_AMD64")
    if revision is None:
        pytest.skip(f"No revision for {architecture.architecture} architecture")

    deploy_stable(juju, int(revision))
    run_upgrade_check(juju)

    with continuous_writes(juju):
        upgrade_from_stable(juju, charm)


@markers.arm64_only
def test_upgrade_from_stable_arm(juju: Juju, charm: str):
    """Simple test to ensure that all MySQL stable revisions can be upgraded."""
    revision = os.getenv("CHARM_REVISION_ARM64")
    if revision is None:
        pytest.skip(f"No revision for {architecture.architecture} architecture")

    deploy_stable(juju, int(revision))
    run_upgrade_check(juju)

    with continuous_writes(juju):
        upgrade_from_stable(juju, charm)


# TODO: add s390x test


def deploy_stable(juju: Juju, revision: int) -> None:
    """Ensure that the MySQL and application charms get deployed."""
    logging.info("Deploying MySQL cluster")
    juju.deploy(
        charm=MYSQL_APP_NAME,
        app=MYSQL_APP_NAME,
        base="ubuntu@22.04",
        channel="8.0/stable",
        config={"profile": "testing"} if revision >= 196 else {},
        revision=revision,
        num_units=3,
    )
    juju.deploy(
        charm=MYSQL_TEST_APP_NAME,
        app=MYSQL_TEST_APP_NAME,
        base="ubuntu@22.04",
        channel="latest/edge",
        num_units=1,
    )

    juju.integrate(
        f"{MYSQL_APP_NAME}:database",
        f"{MYSQL_TEST_APP_NAME}:database",
    )

    logging.info("Wait for applications to become active")
    juju.wait(
        ready=wait_for_apps_status(
            jubilant_backports.all_active, MYSQL_APP_NAME, MYSQL_TEST_APP_NAME
        ),
        error=jubilant_backports.any_blocked,
        timeout=20 * MINUTE_SECS,
    )


async def run_upgrade_check(juju: Juju) -> None:
    """Run the pre-upgrade-check action runs successfully."""
    mysql_leader = get_app_leader(juju, MYSQL_APP_NAME)

    logging.info("Run pre-upgrade-check action")
    task = juju.run(unit=mysql_leader, action="pre-upgrade-check")
    task.raise_on_failure()

    logging.info("Assert primary is set to leader")
    mysql_primary = get_mysql_primary_unit(juju, MYSQL_APP_NAME)
    assert mysql_primary == mysql_leader, "Primary unit not set to leader"


async def upgrade_from_stable(juju: Juju, charm: str) -> None:
    """Update the cluster."""
    logging.info("Ensure continuous writes are incrementing")
    await check_mysql_units_writes_increment(juju, MYSQL_APP_NAME)

    logging.info("Refresh the charm")
    juju.refresh(app=MYSQL_APP_NAME, path=charm)

    logging.info("Wait for upgrade to start")
    juju.wait(
        ready=lambda status: jubilant_backports.any_maintenance(status, MYSQL_APP_NAME),
        timeout=10 * MINUTE_SECS,
    )

    logging.info("Wait for upgrade to complete")
    juju.wait(
        ready=lambda status: jubilant_backports.all_active(status, MYSQL_APP_NAME),
        timeout=20 * MINUTE_SECS,
    )

    logging.info("Ensure continuous writes are incrementing")
    await check_mysql_units_writes_increment(juju, MYSQL_APP_NAME)
