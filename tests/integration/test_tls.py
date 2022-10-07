#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.


import logging
from pathlib import Path

import pytest
import yaml
from pytest_operator.plugin import OpsTest

from constants import CLUSTER_ADMIN_USERNAME
from tests.integration.helpers import (
    app_name,
    get_system_user_password,
    get_tls_ca,
    get_unit_ip,
    is_connection_possible,
    scale_application,
)

logger = logging.getLogger(__name__)


METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = METADATA["name"]
TLS_APP_NAME = "tls-certificates-operator"


@pytest.mark.order(1)
@pytest.mark.abort_on_fail
@pytest.mark.tls_tests
async def test_build_and_deploy(ops_test: OpsTest) -> None:
    """Build the charm and deploy 3 units to ensure a cluster is formed."""
    if app := await app_name(ops_test):
        if len(ops_test.model.applications[app].units) == 3:
            return
        else:
            async with ops_test.fast_forward():
                await scale_application(ops_test, app, 3)
            return

    # Build and deploy charm from local source folder
    charm = await ops_test.build_charm(".")
    await ops_test.model.deploy(charm, application_name=APP_NAME, num_units=3)

    # Reduce the update_status frequency until the cluster is deployed
    async with ops_test.fast_forward():

        await ops_test.model.block_until(
            lambda: len(ops_test.model.applications[APP_NAME].units) == 3
        )
        await ops_test.model.wait_for_idle(
            apps=[APP_NAME],
            status="active",
            raise_on_blocked=True,
            timeout=1000,
        )


@pytest.mark.order(2)
@pytest.mark.abort_on_fail
@pytest.mark.tls_tests
async def test_encryption_enabled(ops_test: OpsTest) -> None:
    """Test for encryption enablement when relation to TLS charm."""
    app = await app_name(ops_test)
    all_units = ops_test.model.applications[app].units

    # Deploy TLS Certificates operator.
    logger.info("Deploy TLS operator")
    async with ops_test.fast_forward():
        config = {"generate-self-signed-certificates": "true", "ca-common-name": "Test CA"}
        await ops_test.model.deploy(TLS_APP_NAME, channel="edge", config=config)
        await ops_test.model.wait_for_idle(apps=[TLS_APP_NAME], status="active", timeout=1000)

    config = {
        "username": CLUSTER_ADMIN_USERNAME,
        "password": await get_system_user_password(all_units[0], CLUSTER_ADMIN_USERNAME),
    }

    # Before relating to TLS charm both encrypted and unencrypted connection should be possible
    logger.info("Asserting connections before relation")
    for unit in all_units:
        unit_ip = await get_unit_ip(ops_test, unit.name)
        config["host"] = unit_ip

        assert is_connection_possible(
            config, **{"ssl_disabled": False}
        ), f"❌ Encrypted connection not possible to unit {unit.name} with disabled TLS"

        assert is_connection_possible(
            config, **{"ssl_disabled": True}
        ), f"❌ Unencrypted connection not possible to unit {unit.name} with disabled TLS"

    # Relate with TLS charm
    logger.info("Relate to TLS operator")
    await ops_test.model.relate(app, TLS_APP_NAME)

    # Wait for hooks start reconfiguring app
    await ops_test.model.block_until(
        lambda: ops_test.model.applications[app].status != "active", timeout=3 * 60
    )

    await ops_test.model.wait_for_idle(status="active", timeout=1000)

    # After relating to only encrypted connection should be possible
    logger.info("Asserting connections after relation")
    for unit in all_units:
        unit_ip = await get_unit_ip(ops_test, unit.name)
        config["host"] = unit_ip
        assert is_connection_possible(
            config, **{"ssl_disabled": False}
        ), f"❌ Encrypted connection not possible to unit {unit.name} with enabled TLS"

        assert not is_connection_possible(
            config, **{"ssl_disabled": True}
        ), f"❌ Unencrypted connection possible to unit {unit.name} with enabled TLS"

    # test for ca presence in a given unit
    logger.info("Assert TLS file exists")
    assert await get_tls_ca(ops_test, all_units[0].name), "❌ No CA found after TLS relation"

    # Remove the relation
    logger.info("Removing relation")
    await ops_test.model.applications[app].remove_relation(
        f"{app}:certificates", f"{TLS_APP_NAME}:certificates"
    )

    # Wait for hooks start reconfiguring app
    await ops_test.model.block_until(
        lambda: ops_test.model.applications[app].status != "active", timeout=3 * 60
    )
    await ops_test.model.wait_for_idle(apps=[app], status="active", timeout=1000)

    # After relation removal both encrypted and unencrypted connection should be possible
    for unit in all_units:
        unit_ip = await get_unit_ip(ops_test, unit.name)
        config["host"] = unit_ip
        assert is_connection_possible(
            config, **{"ssl_disabled": False}
        ), f"❌ Encrypted connection not possible to unit {unit.name} after relation removal"

        assert is_connection_possible(
            config, **{"ssl_disabled": True}
        ), f"❌ Unencrypted connection not possible to unit {unit.name} after relation removal"
