# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import time

import jubilant_backports
import pytest
import urllib3
from jubilant_backports import Juju
from tenacity import (
    Retrying,
    stop_after_attempt,
    wait_fixed,
)

from constants import (
    CHARMED_MYSQL_SNAP_NAME,
    CHARMED_MYSQLD_EXPORTER_SERVICE,
    MONITORING_USERNAME,
    MYSQL_EXPORTER_PORT,
)

from ...helpers_ha import (
    get_app_units,
    get_unit_ip,
    wait_for_apps_status,
)

MYSQL_APP_NAME = "mysql"
MYSQL_TEST_APP_NAME = "mysql-test-app"

MINUTE_SECS = 60


@pytest.mark.abort_on_fail
def test_deploy_highly_available_cluster(juju: Juju, charm: str) -> None:
    """Simple test to ensure that the MySQL and application charms get deployed."""
    logging.info("Deploying MySQL cluster")
    juju.deploy(
        charm=charm,
        app=MYSQL_APP_NAME,
        base="ubuntu@22.04",
        config={"profile": "testing"},
        num_units=3,
    )
    juju.deploy(
        charm=MYSQL_TEST_APP_NAME,
        app=MYSQL_TEST_APP_NAME,
        base="ubuntu@22.04",
        channel="latest/edge",
        config={"sleep_interval": 500},
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


@pytest.mark.abort_on_fail
def test_exporter_endpoints(juju: Juju) -> None:
    """Test that endpoints are running."""
    http_client = urllib3.PoolManager()
    service_name = f"{CHARMED_MYSQL_SNAP_NAME}.{CHARMED_MYSQLD_EXPORTER_SERVICE}"

    for unit_name in get_app_units(juju, MYSQL_APP_NAME):
        task = juju.exec(f"sudo snap services {service_name}", unit=unit_name)

        assert task.stdout.split("\n")[1].split()[2] == "inactive"

        credentials_task = juju.run(
            unit=unit_name,
            action="get-password",
            params={"username": MONITORING_USERNAME},
        )

        username = credentials_task.results["username"]
        password = credentials_task.results["password"]

        juju.exec(f"sudo snap set charmed-mysql exporter.user={username}", unit=unit_name)
        juju.exec(f"sudo snap set charmed-mysql exporter.password={password}", unit=unit_name)
        juju.exec(f"sudo snap start {service_name}", unit=unit_name)

        for attempt in Retrying(stop=stop_after_attempt(45), wait=wait_fixed(2)):
            with attempt:
                task = juju.exec(f"sudo snap services {service_name}", unit=unit_name)

        assert task.stdout.split("\n")[1].split()[2] == "active"

        time.sleep(30)

        mysql_unit_address = get_unit_ip(juju, MYSQL_APP_NAME, unit_name)
        mysql_unit_exporter_url = f"http://{mysql_unit_address}:{MYSQL_EXPORTER_PORT}/metrics"
        mysql_unit_response = http_client.request("GET", mysql_unit_exporter_url)

        assert mysql_unit_response.status == 200
