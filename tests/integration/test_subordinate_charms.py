# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Test charms subordinated to MySQL charm."""

import asyncio
import os

from .relations.test_database import APPLICATION_APP_NAME, CLUSTER_NAME, DATABASE_APP_NAME, TIMEOUT

UBUNTU_PRO_APP_NAME = "ubuntu-advantage"
LANDSCAPE_CLIENT_APP_NAME = "landscape-client"


async def test_ubuntu_pro(ops_test, charm):
    await asyncio.gather(
        ops_test.model.deploy(
            charm,
            application_name=DATABASE_APP_NAME,
            config={"cluster-name": CLUSTER_NAME, "profile": "testing"},
            base="ubuntu@22.04",
        ),
        ops_test.model.deploy(
            APPLICATION_APP_NAME,
            application_name=APPLICATION_APP_NAME,
            channel="latest/edge",
            base="ubuntu@22.04",
        ),
        ops_test.model.deploy(
            UBUNTU_PRO_APP_NAME,
            application_name=UBUNTU_PRO_APP_NAME,
            channel="latest/edge",
            config={"token": os.environ["UBUNTU_PRO_TOKEN"]},
            base="ubuntu@22.04",
        ),
    )
    await ops_test.model.relate(
        f"{DATABASE_APP_NAME}:database", f"{APPLICATION_APP_NAME}:database"
    )
    await ops_test.model.relate(DATABASE_APP_NAME, UBUNTU_PRO_APP_NAME)
    async with ops_test.fast_forward("60s"):
        await ops_test.model.wait_for_idle(
            apps=[DATABASE_APP_NAME, APPLICATION_APP_NAME, UBUNTU_PRO_APP_NAME],
            status="active",
            raise_on_blocked=True,
            timeout=TIMEOUT,
        )


async def test_landscape_client(ops_test):
    await ops_test.model.deploy(
        LANDSCAPE_CLIENT_APP_NAME,
        application_name=LANDSCAPE_CLIENT_APP_NAME,
        channel="latest/edge",
        config={
            "account-name": os.environ["LANDSCAPE_ACCOUNT_NAME"],
            "registration-key": os.environ["LANDSCAPE_REGISTRATION_KEY"],
            "ppa": "ppa:landscape/self-hosted-beta",
        },
        base="ubuntu@22.04",
    )
    await ops_test.model.relate(DATABASE_APP_NAME, LANDSCAPE_CLIENT_APP_NAME)
    async with ops_test.fast_forward("60s"):
        await ops_test.model.wait_for_idle(
            apps=[DATABASE_APP_NAME, APPLICATION_APP_NAME, LANDSCAPE_CLIENT_APP_NAME],
            status="active",
            raise_on_blocked=True,
            timeout=TIMEOUT,
        )
