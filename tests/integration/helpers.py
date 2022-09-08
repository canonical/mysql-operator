# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.


import itertools
import json
import logging
import re
import secrets
import string
import subprocess
from typing import Dict, List, Optional, Set

import yaml
from connector import MysqlConnector
from juju.unit import Unit
from mysql.connector.errors import InterfaceError, OperationalError, ProgrammingError
from pytest_operator.plugin import OpsTest
from tenacity import retry, stop_after_attempt, wait_fixed

from constants import SERVER_CONFIG_USERNAME


async def run_command_on_unit(unit, command: str) -> Optional[str]:
    """Run a command in one Juju unit.

    Args:
        unit: the Juju unit instance.
        command: the command to run.

    Returns:
        command execution output or none if
        the command produces no output.
    """
    # workaround for https://github.com/juju/python-libjuju/issues/707
    action = await unit.run(command)
    result = await action.wait()
    code = str(result.results.get("Code") or result.results.get("return-code"))
    stdout = result.results.get("Stdout") or result.results.get("stdout")
    stderr = result.results.get("Stderr") or result.results.get("stderr")
    assert code == "0", f"{command} failed ({code}): {stderr or stdout}"
    return stdout


def generate_random_string(length: int) -> str:
    """Generate a random string of the provided length.

    Args:
        length: the length of the random string to generate

    Returns:
        A random string comprised of letters and digits
    """
    choices = string.ascii_letters + string.digits
    return "".join([secrets.choice(choices) for i in range(length)])


async def scale_application(
    ops_test: OpsTest,
    application_name: str,
    count: int,
):
    """Scale a given application to a unit count.

    Args:
        ops_test: The ops test framework
        application_name: The name of the application
        count: The number of units to scale to
    """
    application = ops_test.model.applications[application_name]
    count_existing_units = len(application.units)

    # Do nothing if already in the desired state
    if count == count_existing_units:
        return

    # Scale up
    if count > count_existing_units:
        for _ in range(count - count_existing_units):
            await application.add_unit()

        await ops_test.model.block_until(
            lambda: len(application.units) == count,
            timeout=1500,
        )
        await ops_test.model.wait_for_idle(
            apps=[application_name],
            status="active",
            raise_on_blocked=True,
            timeout=1000,
        )

        return

    # Scale down
    units_to_destroy = [unit.name for unit in application.units[count:]]

    for unit_to_destroy in units_to_destroy:
        await ops_test.model.destroy_units(unit_to_destroy)

    await ops_test.model.block_until(lambda: len(application.units) == count)

    if count > 0:
        await ops_test.model.wait_for_idle(
            apps=[application_name],
            status="active",
            raise_on_blocked=True,
            timeout=1000,
        )


async def get_primary_unit(
    ops_test: OpsTest,
    unit: Unit,
    app_name: str,
    cluster_name: str,
    server_config_username: str,
    server_config_password: str,
) -> str:
    """Helper to retrieve the primary unit.

    Args:
        ops_test: The ops test object passed into every test case
        unit: A unit on which to run dba.get_cluster().status() on
        app_name: The name of the test application
        cluster_name: The name of the test cluster
        server_config_username: The server config username
        server_config_password: The server config password

    Returns:
        A juju unit that is a MySQL primary
    """
    commands = [
        "mysqlsh",
        "--python",
        f"{server_config_username}:{server_config_password}@127.0.0.1",
        "-e",
        f"\"print('<CLUSTER_STATUS>' + dba.get_cluster('{cluster_name}').status().__repr__() + '</CLUSTER_STATUS>')\"",
    ]
    raw_output = await run_command_on_unit(unit, " ".join(commands))

    if not raw_output:
        return None

    matches = re.search("<CLUSTER_STATUS>(.+)</CLUSTER_STATUS>", raw_output)
    if not matches:
        return None

    cluster_status = json.loads(matches.group(1).strip())

    primary_name = [
        label
        for label, member in cluster_status["defaultReplicaSet"]["topology"].items()
        if member["mode"] == "R/W"
    ][0].replace("-", "/")

    for unit in ops_test.model.applications[app_name].units:
        if unit.name == primary_name:
            return unit

    return None


async def get_server_config_credentials(unit: Unit) -> Dict:
    """Helper to run an action to retrieve server config credentials.

    Args:
        unit: The juju unit on which to run the get-password action for server-config credentials

    Returns:
        A dictionary with the server config username and password
    """
    action = await unit.run_action(action_name="get-password", username=SERVER_CONFIG_USERNAME)
    result = await action.wait()

    return result.results


async def fetch_credentials(unit: Unit, username: str = None) -> Dict:
    """Helper to run an action to fetch credentials.

    Args:
        unit: The juju unit on which to run the get-password action for credentials

    Returns:
        A dictionary with the server config username and password
    """
    if username is None:
        action = await unit.run_action(action_name="get-password")
    else:
        action = await unit.run_action(action_name="get-password", username=username)

    result = await action.wait()

    return result.results


async def rotate_credentials(unit: Unit, username: str = None, password: str = None) -> Dict:
    """Helper to run an action to rotate credentials.

    Args:
        unit: The juju unit on which to run the set-password action for credentials

    Returns:
        A dictionary with the action result
    """
    if username is None:
        action = await unit.run_action(action_name="set-password")
    elif password is None:
        action = await unit.run_action(action_name="set-password", username=username)
    else:
        action = await unit.run_action(
            action_name="set-password", username=username, password=password
        )
    result = await action.wait()

    return result.results


async def get_legacy_mysql_credentials(unit: Unit) -> Dict:
    """Helper to run an action to retrieve legacy mysql config credentials.

    Args:
        unit: The juju unit on which to run the get-legacy-mysql-credentials action

    Returns:
        A dictionary with the credentials
    """
    action = await unit.run_action("get-legacy-mysql-credentials")
    result = await action.wait()

    return result.results


async def execute_commands_on_unit(
    unit_address: str,
    username: str,
    password: str,
    queries: List[str],
    commit: bool = False,
) -> List:
    """Execute given MySQL queries on a unit.

    Args:
        unit_address: The public IP address of the unit to execute the queries on
        username: The MySQL username
        password: The MySQL password
        queries: A list of queries to execute
        commit: A keyword arg indicating whether there are any writes queries

    Returns:
        A list of rows that were potentially queried
    """
    config = {
        "user": username,
        "password": password,
        "host": unit_address,
        "raise_on_warnings": False,
    }

    with MysqlConnector(config, commit) as cursor:
        for query in queries:
            cursor.execute(query)
        output = list(itertools.chain(*cursor.fetchall()))

    return output


def is_relation_joined(ops_test: OpsTest, endpoint_one: str, endpoint_two: str) -> bool:
    """Check if a relation is joined.

    Args:
        ops_test: The ops test object passed into every test case
        endpoint_one: The first endpoint of the relation
        endpoint_two: The second endpoint of the relation
    """
    for rel in ops_test.model.relations:
        endpoints = [endpoint.name for endpoint in rel.endpoints]
        if endpoint_one in endpoints and endpoint_two in endpoints:
            return True
    return False


def is_relation_broken(ops_test: OpsTest, endpoint_one: str, endpoint_two: str) -> bool:
    """Check if a relation is broken.

    Args:
        ops_test: The ops test object passed into every test case
        endpoint_one: The first endpoint of the relation
        endpoint_two: The second endpoint of the relation
    """
    for rel in ops_test.model.relations:
        endpoints = [endpoint.name for endpoint in rel.endpoints]
        if endpoint_one not in endpoints and endpoint_two not in endpoints:
            return True
    return False


@retry(stop=stop_after_attempt(3), wait=wait_fixed(5), reraise=True)
def is_connection_possible(credentials: Dict) -> bool:
    """Test a connection to a MySQL server.

    Args:
        credentials: A dictionary with the credentials to test
    """
    config = {
        "user": credentials["username"],
        "password": credentials["password"],
        "host": credentials["host"],
        "raise_on_warnings": False,
    }

    try:
        with MysqlConnector(config) as cursor:
            cursor.execute("SELECT 1")
            return cursor.fetchone()[0] == 1
    except (InterfaceError, OperationalError, ProgrammingError):
        # Errors raised when the connection is not possible
        return False


def instance_ip(model: str, instance: str) -> str:
    """Translate juju instance name to IP.

    Args:
        model: The name of the model
        instance: The name of the instance
    Returns:
        The (str) IP address of the instance
    """
    output = subprocess.check_output(f"juju machines --model {model}".split())

    for line in output.decode("utf8").splitlines():
        if instance in line:
            return line.split()[2]


async def app_name(ops_test: OpsTest) -> str:
    """Returns the name of the application running MySQL.

    This is important since not all deployments of the MySQL charm have the application name
    "mysql".

    Note: if multiple clusters are running MySQL this will return the one first found.
    """
    status = await ops_test.model.get_status()
    for app in ops_test.model.applications:
        # note that format of the charm field is not exactly "mysql" but instead takes the form
        # of `local:focal/mysql-6`
        if "mysql" in status["applications"][app]["charm"]:
            return app

    return None


def cluster_name(unit: Unit, model_name: str) -> str:
    """Returns the MySQL cluster name.

    Args:
        unit: A unit to get data from
        model_name: The current model name
    Returns:
        The (str) mysql cluster name
    """
    output = subprocess.check_output(
        [
            "juju",
            "show-unit",
            unit.name,
            "--format=json",
            f"--model={model_name}",
        ]
    )
    output = json.loads(output.decode("utf-8"))

    return output[unit.name]["relation-info"][0]["application-data"]["cluster-name"]


async def get_relation_data(
    ops_test: OpsTest,
    application_name: str,
    relation_name: str,
) -> list:
    """Returns a that contains the relation-data.

    Args:
        ops_test: The ops test framework instance
        application_name: The name of the application
        relation_name: name of the relation to get connection data from
    Returns:
        a dictionary that contains the relation-data
    """
    # get available unit id for the desidered application
    units_ids = [
        app_unit.name.split("/")[1]
        for app_unit in ops_test.model.applications[application_name].units
    ]
    assert len(units_ids) > 0
    unit_name = f"{application_name}/{units_ids[0]}"
    raw_data = (await ops_test.juju("show-unit", unit_name))[1]
    if not raw_data:
        raise ValueError(f"no unit info could be grabbed for {unit_name}")
    data = yaml.safe_load(raw_data)
    # Filter the data based on the relation name.
    relation_data = [v for v in data[unit_name]["relation-info"] if v["endpoint"] == relation_name]
    if len(relation_data) == 0:
        raise ValueError(
            f"no relation data could be grabbed on relation with endpoint {relation_name}"
        )

    return relation_data


def get_read_only_endpoint(relation_data: list) -> Set[str]:
    """Returns the read-only-endpoints from the relation data.

    Args:
        relation_data: The dictionary that contains the info
    Returns:
        a set that contains the read-only-endpoints
    """
    related_units = relation_data[0]["related-units"]
    roe = set()
    for _, r_data in related_units.items():
        assert "data" in r_data
        data = r_data["data"]["data"]

        try:
            j_data = json.loads(data)
            if "read-only-endpoints" in j_data:
                read_only_endpoints = j_data["read-only-endpoints"]
                if read_only_endpoints.strip() == "":
                    continue
                for ep in read_only_endpoints.split(","):
                    roe.add(ep)
        except json.JSONDecodeError:
            raise ValueError("Relation data are not valid JSON.")

    return roe


def get_read_only_endpoint_hostnames(relation_data: list) -> List[str]:
    """Returns the read-only-endpoint hostnames from the relation data.

    Args:
        relation_data: The dictionary that contains the info
    Returns:
        a set that contains the read-only-endpoint hostnames
    """
    roe = get_read_only_endpoint(relation_data)
    roe_hostnames = []
    for r in roe:
        if ":" in r:
            roe_hostnames.append(r.split(":")[0])
        else:
            raise ValueError("Malformed endpoint")
    return roe_hostnames

async def remove_leader_unit(ops_test: OpsTest, application_name: str):
    """Removes the leader unit of a specified application.

    Args:
        ops_test: The ops test framework instance
        application_name: The name of the application
    """
    leader_unit = None
    for app_unit in ops_test.model.applications[application_name].units:
        is_leader = await app_unit.is_leader_from_status()
        if is_leader:
            leader_unit = app_unit.name

    units_to_destroy = [leader_unit]

    for unit_to_destroy in units_to_destroy:
        await ops_test.model.destroy_units(unit_to_destroy)

    count = len(ops_test.model.applications[application_name].units)

    application = ops_test.model.applications[application_name]
    await ops_test.model.block_until(lambda: len(application.units) == count)

    if count > 0:
        await ops_test.model.wait_for_idle(
            apps=[application_name],
            status="active",
            raise_on_blocked=True,
            timeout=1000,
        )
    


async def get_unit_hostname(ops_test: OpsTest, app_name: str) -> List[str]:
    """Retrieves hostnames of given application units.
    
    Args:
        ops_test: The ops test framework instance
        application_name: The name of the application
    """
    units = [app_unit.name for app_unit in ops_test.model.applications[app_name].units]
    status = await ops_test.model.get_status()  # noqa: F821
    machine_hostname = {}

    for machine_id, v in status["machines"].items():
        machine_hostname[machine_id] = v["hostname"]

    unit_machine = {}
    for unit in units:
        unit_machine[unit] = status["applications"][app_name]["units"][f"{unit}"]["machine"]
    hostnames = []
    for unit, machine in unit_machine.items():
        if machine in machine_hostname:
            hostnames.append(machine_hostname[machine])
    return hostnames
