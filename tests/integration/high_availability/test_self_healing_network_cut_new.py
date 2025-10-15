# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import logging
import subprocess

import jubilant_backports
import pytest
from jubilant_backports import Juju
from tenacity import (
    Retrying,
    retry,
    stop_after_attempt,
    wait_fixed,
)

from constants import CLUSTER_ADMIN_USERNAME

from ..helpers import (
    generate_random_string,
    is_connection_possible,
)
from .high_availability_helpers_new import (
    check_mysql_units_writes_increment,
    get_app_units,
    get_mysql_primary_unit,
    get_unit_ip,
    insert_mysql_test_data,
    remove_mysql_test_data,
    verify_mysql_test_data,
    wait_for_apps_status,
    wait_for_unit_status,
)

MYSQL_APP_NAME = "mysql"
MYSQL_TEST_APP_NAME = "mysql-test-app"

MINUTE_SECS = 60

logging.getLogger("jubilant.wait").setLevel(logging.WARNING)


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
async def test_network_cut(juju: Juju, continuous_writes_new) -> None:
    """Completely cut and restore network."""
    mysql_units = get_app_units(juju, MYSQL_APP_NAME)

    # Ensure continuous writes still incrementing for all units
    await check_mysql_units_writes_increment(juju, MYSQL_APP_NAME)

    mysql_primary_unit = get_mysql_primary_unit(juju, MYSQL_APP_NAME)
    mysql_primary_hostname = get_unit_hostname(juju, MYSQL_APP_NAME, mysql_primary_unit)
    mysql_primary_unit_ip = get_unit_ip(juju, MYSQL_APP_NAME, mysql_primary_unit)

    logging.info(f"Unit {mysql_primary_unit} is on machine {mysql_primary_hostname}")

    credentials_task = juju.run(
        unit=mysql_primary_unit,
        action="get-password",
        params={"username": CLUSTER_ADMIN_USERNAME},
    )
    credentials_task.raise_on_failure()

    config = {
        "username": credentials_task.results["username"],
        "password": credentials_task.results["password"],
        "host": mysql_primary_unit_ip,
    }

    # Verify that connection is possible
    assert is_connection_possible(config)

    logging.info(f"Cutting network for {mysql_primary_hostname}")
    cut_unit_network(mysql_primary_hostname)

    hostnames = [get_controller_hostname(juju)]
    for unit_name in set(mysql_units) - {mysql_primary_unit}:
        unit_hostname = get_unit_hostname(juju, MYSQL_APP_NAME, unit_name)
        hostnames.append(unit_hostname)

    for hostname in hostnames:
        assert not check_machine_connection(hostname, mysql_primary_hostname)

    # Verify that connection is not possible
    assert not is_connection_possible(config)

    logging.info(f"Restoring network for {mysql_primary_hostname}")
    set_unit_network(mysql_primary_hostname)

    # Wait until network is re-established for the unit
    wait_for_unit_network(juju, MYSQL_APP_NAME, mysql_primary_unit)

    # Wait for the unit to be ready
    for attempt in Retrying(stop=stop_after_attempt(60), wait=wait_fixed(10)):
        with attempt:
            new_primary_unit_ip = get_unit_ip(juju, MYSQL_APP_NAME, mysql_primary_unit)
            new_primary_unit_config = {
                "username": credentials_task.results["username"],
                "password": credentials_task.results["password"],
                "host": new_primary_unit_ip,
            }

            logging.debug(f"Waiting until connection possible on {new_primary_unit_ip}")
            assert is_connection_possible(new_primary_unit_config)

    logging.info(f"Waiting for {mysql_primary_unit} to enter active")
    juju.wait(
        ready=wait_for_unit_status(MYSQL_APP_NAME, mysql_primary_unit, "active"),
        timeout=20 * MINUTE_SECS,
    )

    # Ensure continuous writes still incrementing for all units
    await check_mysql_units_writes_increment(juju, MYSQL_APP_NAME)

    # Ensure that we are able to insert data into the primary
    table_name = "data"
    table_value = generate_random_string(255)

    await insert_mysql_test_data(juju, MYSQL_APP_NAME, table_name, table_value)
    await verify_mysql_test_data(juju, MYSQL_APP_NAME, table_name, table_value)
    await remove_mysql_test_data(juju, MYSQL_APP_NAME, table_name)


def check_machine_connection(source_machine: str, target_machine: str) -> bool:
    """Test network reachability between hosts.

    Args:
        source_machine: hostname of the machine to test connection from
        target_machine: hostname of the machine to test connection into
    """
    try:
        subprocess.check_call(f"lxc exec {source_machine} -- ping -c 3 {target_machine}".split())
        return True
    except subprocess.CalledProcessError:
        return False


def cut_unit_network(machine_hostname: str) -> None:
    """Cut network from a LXC container."""
    subprocess.check_call(f"lxc config device add {machine_hostname} eth0 none".split())


def set_unit_network(machine_hostname: str) -> None:
    """Restore network from a lxc container."""
    subprocess.check_call(f"lxc config device remove {machine_hostname} eth0".split())


def get_controller_hostname(juju: Juju) -> str:
    """Return controller machine hostname."""
    model_status = juju.status()

    output = subprocess.check_output(
        ["juju", "show-controller", "--format=json"],
        text=True,
    )

    controller_info = json.loads(output.strip())
    controller_machines = controller_info[model_status.model.controller]["controller-machines"]
    return next(machine.get("instance-id") for machine in controller_machines.values())


def get_unit_hostname(juju: Juju, app_name: str, unit_name: str) -> str:
    """Get hostname for a unit."""
    task = juju.exec("hostname", unit=unit_name)
    task.raise_on_failure()

    return task.stdout.strip()


@retry(stop=stop_after_attempt(20), wait=wait_fixed(15))
def wait_for_unit_network(juju: Juju, app_name: str, unit_name: str) -> None:
    """Wait until network is restored.

    Args:
        juju: The juju instance to use.
        app_name: The name of the app
        unit_name: The name of the unit
    """
    task = juju.exec("ip address", unit=unit_name)
    task.raise_on_failure()

    unit_ip = get_unit_ip(juju, app_name, unit_name)
    if unit_ip in task.stdout:
        raise Exception()
