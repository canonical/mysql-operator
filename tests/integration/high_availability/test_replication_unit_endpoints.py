# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.


import logging
import time
from pathlib import Path

import pytest
import urllib3
import yaml
from pytest_operator.plugin import OpsTest
from tenacity import RetryError, Retrying, stop_after_attempt, wait_fixed

from ..helpers import (
    fetch_credentials,
)
from .high_availability_helpers import (
    get_application_name,
)

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = METADATA["name"]
ANOTHER_APP_NAME = f"second{APP_NAME}"
TIMEOUT = 17 * 60


@pytest.mark.abort_on_fail
async def test_exporter_endpoints(ops_test: OpsTest, highly_available_cluster) -> None:
    """Test that endpoints are running."""
    mysql_application_name = get_application_name(ops_test, "mysql")
    application = ops_test.model.applications[mysql_application_name]
    http = urllib3.PoolManager()

    for unit in application.units:
        _, output, _ = await ops_test.juju(
            "ssh", unit.name, "sudo", "snap", "services", "charmed-mysql.mysqld-exporter"
        )
        assert output.split("\n")[1].split()[2] == "inactive"

        return_code, _, _ = await ops_test.juju(
            "ssh", unit.name, "sudo", "snap", "set", "charmed-mysql", "exporter.user=monitoring"
        )
        assert return_code == 0

        monitoring_credentials = await fetch_credentials(unit, "monitoring")
        return_code, _, _ = await ops_test.juju(
            "ssh",
            unit.name,
            "sudo",
            "snap",
            "set",
            "charmed-mysql",
            f"exporter.password={monitoring_credentials['password']}",
        )
        assert return_code == 0

        return_code, _, _ = await ops_test.juju(
            "ssh", unit.name, "sudo", "snap", "start", "charmed-mysql.mysqld-exporter"
        )
        assert return_code == 0

        try:
            for attempt in Retrying(stop=stop_after_attempt(45), wait=wait_fixed(2)):
                with attempt:
                    _, output, _ = await ops_test.juju(
                        "ssh",
                        unit.name,
                        "sudo",
                        "snap",
                        "services",
                        "charmed-mysql.mysqld-exporter",
                    )
                    assert output.split("\n")[1].split()[2] == "active"
        except RetryError:
            raise Exception("Failed to start the mysqld-exporter snap service")

        time.sleep(30)

        unit_address = await unit.get_public_address()
        mysql_exporter_url = f"http://{unit_address}:9104/metrics"

        jmx_resp = http.request("GET", mysql_exporter_url)

        assert jmx_resp.status == 200
