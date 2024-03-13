# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Test charms subordinated to MySQL charm."""

import asyncio

import pytest

from .relations.test_database import APPLICATION_APP_NAME, CLUSTER_NAME, DATABASE_APP_NAME, TIMEOUT

UBUNTU_PRO_APP_NAME = "ubuntu-pro"


@pytest.mark.group(1)
async def test_ubuntu_pro(ops_test, mysql_charm_series, github_secrets):
    db_charm = await ops_test.build_charm(".")
    await asyncio.gather(
        ops_test.model.deploy(
            db_charm,
            application_name=DATABASE_APP_NAME,
            config={"cluster-name": CLUSTER_NAME, "profile": "testing"},
            series=mysql_charm_series,
        ),
        ops_test.model.deploy(
            APPLICATION_APP_NAME,
            application_name=APPLICATION_APP_NAME,
            channel="latest/edge",
        ),
        ops_test.model.deploy(
            UBUNTU_PRO_APP_NAME,
            application_name=UBUNTU_PRO_APP_NAME,
            channel="latest/edge",
            config={"token": github_secrets["UBUNTU_PRO_TOKEN"]},
        ),
    )
    await ops_test.model.relate(
        f"{DATABASE_APP_NAME}:database", f"{APPLICATION_APP_NAME}:database"
    )
    await ops_test.model.relate(f"{DATABASE_APP_NAME}", f"{UBUNTU_PRO_APP_NAME}")
    async with ops_test.fast_forward("60s"):
        await ops_test.model.wait_for_idle(
            apps=[DATABASE_APP_NAME, APPLICATION_APP_NAME, UBUNTU_PRO_APP_NAME],
            status="active",
            raise_on_blocked=True,
            timeout=TIMEOUT,
        )
