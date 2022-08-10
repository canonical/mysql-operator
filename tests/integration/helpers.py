# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.


import itertools
import json
import re
import secrets
import string
from typing import Dict, List, Optional

from connector import MysqlConnector
from juju.unit import Unit
from pytest_operator.plugin import OpsTest


async def run_command_on_unit(unit, command: str) -> Optional[str]:
    """Run a command in one Juju unit.

    Args:
        unit: the Juju unit instance.
        command: the command to run.

    Returns:
        command execution output or none if
        the command produces no output.
    """
    action = await unit.run(command)
    return action.results.get("Stdout", None)


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

        await ops_test.model.block_until(lambda: len(application.units) == count)
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
        unit: The juju unit on which to run the get-server-config-credentials action

    Returns:
        A dictionary with the server config username and password
    """
    action = await unit.run_action("get-server-config-credentials")
    result = await action.wait()

    return {
        "username": result.results["server-config-username"],
        "password": result.results["server-config-password"],
    }


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
