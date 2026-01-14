# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import itertools
import json
import logging
import secrets
import string

import yaml
from juju.unit import Unit
from mysql.connector.errors import (
    DatabaseError,
    InterfaceError,
    OperationalError,
    ProgrammingError,
)
from pytest_operator.plugin import OpsTest
from tenacity import retry, stop_after_attempt, wait_fixed

from constants import SERVER_CONFIG_USERNAME

from . import juju_
from .connector import MysqlConnector

logger = logging.getLogger(__name__)

TIMEOUT = 16 * 60
TIMEOUT_BIG = 25 * 60


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
            timeout=TIMEOUT_BIG,
        )
        await ops_test.model.wait_for_idle(
            apps=[application_name],
            status="active",
            raise_on_blocked=True,
            timeout=TIMEOUT,
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
            timeout=TIMEOUT,
        )


@retry(stop=stop_after_attempt(30), wait=wait_fixed(5), reraise=True)
async def get_primary_unit(
    ops_test: OpsTest,
    unit: Unit,
    app_name: str,
) -> Unit:
    """Helper to retrieve the primary unit.

    Args:
        ops_test: The ops test object passed into every test case
        unit: A unit on which to run dba.get_cluster().status() on
        app_name: The name of the test application
        cluster_name: The name of the test cluster

    Returns:
        A juju unit that is a MySQL primary
    """
    units = ops_test.model.applications[app_name].units
    results = await juju_.run_action(unit, "get-cluster-status")

    primary_unit = None
    for k, v in results["status"]["defaultreplicaset"]["topology"].items():
        if v["memberrole"] == "primary" and v["status"] == "online":
            unit_name = f"{app_name}/{k.split('-')[-1]}"
            primary_unit = next(unit for unit in units if unit.name == unit_name)
            break

    if not primary_unit:
        raise ValueError("Unable to find primary unit")
    return primary_unit


async def get_server_config_credentials(unit: Unit) -> dict:
    """Helper to run an action to retrieve server config credentials.

    Args:
        unit: The juju unit on which to run the get-password action for server-config credentials

    Returns:
        A dictionary with the server config username and password
    """
    return await juju_.run_action(unit, "get-password", username=SERVER_CONFIG_USERNAME)


async def fetch_credentials(unit: Unit, username: str | None = None) -> dict:
    """Helper to run an action to fetch credentials.

    Args:
        unit: The juju unit on which to run the get-password action for credentials

    Returns:
        A dictionary with the server config username and password
    """
    if username is None:
        return await juju_.run_action(unit, "get-password")
    return await juju_.run_action(unit, "get-password", username=username)


async def rotate_credentials(
    unit: Unit, username: str | None = None, password: str | None = None
) -> dict:
    """Helper to run an action to rotate credentials.

    Args:
        unit: The juju unit on which to run the set-password action for credentials

    Returns:
        A dictionary with the action result
    """
    if username is None:
        return await juju_.run_action(unit, "set-password")
    elif password is None:
        return await juju_.run_action(unit, "set-password", username=username)
    else:
        return await juju_.run_action(unit, "set-password", username=username, password=password)


async def get_legacy_mysql_credentials(unit: Unit) -> dict:
    """Helper to run an action to retrieve legacy mysql config credentials.

    Args:
        unit: The juju unit on which to run the get-legacy-mysql-credentials action

    Returns:
        A dictionary with the credentials
    """
    return await juju_.run_action(unit, "get-legacy-mysql-credentials")


@retry(stop=stop_after_attempt(20), wait=wait_fixed(5), reraise=True)
async def get_system_user_password(unit: Unit, user: str) -> dict:
    """Helper to run an action to retrieve system user password.

    Args:
        unit: The juju unit on which to run the get-password action

    Returns:
        A dictionary with the credentials
    """
    results = await juju_.run_action(unit, "get-password", username=user)
    return results.get("password")


async def execute_queries_on_unit(
    unit_address: str,
    username: str,
    password: str,
    queries: list[str],
    commit: bool = False,
    raw: bool = False,
) -> list:
    """Execute given MySQL queries on a unit.

    Args:
        unit_address: The public IP address of the unit to execute the queries on
        username: The MySQL username
        password: The MySQL password
        queries: A list of queries to execute
        commit: A keyword arg indicating whether there are any writes queries
        raw: Whether MySQL results are returned as is, rather than converted to Python types.

    Returns:
        A list of rows that were potentially queried
    """
    config = {
        "user": username,
        "password": password,
        "host": unit_address,
        "raise_on_warnings": False,
        "raw": raw,
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


@retry(stop=stop_after_attempt(30), wait=wait_fixed(5), reraise=True)
def is_connection_possible(
    credentials: dict, *, retry_if_not_possible=False, **extra_opts
) -> bool:
    """Test a connection to a MySQL server.

    Args:
        credentials: A dictionary with the credentials to test
        retry_if_not_possible: Retry if connection not possible
        extra_opts: extra options for mysql connection
    """
    config = {
        "user": credentials["username"],
        "password": credentials["password"],
        "host": credentials["host"],
        "raise_on_warnings": False,
        "connection_timeout": 10,
        **extra_opts,
    }

    try:
        with MysqlConnector(config) as cursor:
            cursor.execute("SELECT 1")
            return cursor.fetchone()[0] == 1
    except (DatabaseError, InterfaceError, OperationalError, ProgrammingError):
        # Errors raised when the connection is not possible
        if retry_if_not_possible:
            # Retry
            raise
        return False


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


async def get_process_pid(ops_test: OpsTest, unit_name: str, process: str) -> int:
    """Return the pid of a process running in a given unit.

    Args:
        ops_test: The ops test object passed into every test case
        unit_name: The name of the unit
        process: The process name to search for
    Returns:
        A integer for the process id
    """
    try:
        _, raw_pid, _ = await ops_test.juju("ssh", unit_name, "pgrep", "-x", process)
        pid = int(raw_pid.strip())

        return pid
    except Exception:
        return None


async def get_primary_unit_wrapper(ops_test: OpsTest, app_name: str, unit_excluded=None) -> Unit:
    """Wrapper for getting primary.

    Args:
        ops_test: The ops test object passed into every test case
        app_name: The name of the application
        unit_excluded: excluded unit to run command on
    Returns:
        The primary Unit object
    """
    logger.info("Retrieving primary unit")
    units = ops_test.model.applications[app_name].units

    for unit in units:
        if unit_excluded and unit.name == unit_excluded.name:
            continue
        try:
            primary_unit = await get_primary_unit(ops_test, unit, app_name)
            return primary_unit
        except DatabaseError:
            continue
    raise ValueError("Primary unit found cannot be retrieved")


async def get_unit_ip(ops_test: OpsTest, unit_name: str) -> str:
    """Wrapper for getting unit ip.

    Args:
        ops_test: The ops test object passed into every test case
        unit_name: The name of the unit to get the address
    Returns:
        The (str) ip of the unit
    """
    app_name = unit_name.split("/")[0]
    unit_num = unit_name.split("/")[1]
    status = await ops_test.model.get_status()
    address = status["applications"][app_name]["units"][f"{app_name}/{unit_num}"]["public-address"]
    return address


async def get_relation_data(
    ops_test: OpsTest,
    application_name: str,
    relation_name: str,
) -> list:
    """Returns a list that contains the relation-data.

    Args:
        ops_test: The ops test framework instance
        application_name: The name of the application
        relation_name: name of the relation to get connection data from
    Returns:
        a list that contains the relation-data
    """
    # get available unit id for the desired application
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


def get_read_only_endpoints(relation_data: list) -> set[str]:
    """Returns the read-only-endpoints from the relation data.

    Args:
        relation_data: The dictionary that contains the info
    Returns:
        a set that contains the read-only-endpoints
    """
    related_units = relation_data[0]["related-units"]
    read_only_endpoints = set()
    for _, relation_data in related_units.items():
        assert "data" in relation_data
        data = relation_data["data"]["data"]

        try:
            j_data = json.loads(data)
            if "read-only-endpoints" in j_data:
                read_only_endpoint_field = j_data["read-only-endpoints"]
                if read_only_endpoint_field.strip() == "":
                    continue
                for ep in read_only_endpoint_field.split(","):
                    read_only_endpoints.add(ep)
        except json.JSONDecodeError as e:
            raise ValueError("Relation data are not valid JSON.") from e

    return read_only_endpoints


def get_read_only_endpoint_ips(relation_data: list) -> list[str]:
    """Returns the read-only-endpoint hostnames from the relation data.

    Args:
        relation_data: The dictionary that contains the info
    Returns:
        a set that contains the read-only-endpoint hostnames
    """
    read_only_endpoints = get_read_only_endpoints(relation_data)
    read_only_endpoint_hostnames = []
    for read_only_endpoint in read_only_endpoints:
        if ":" in read_only_endpoint:
            read_only_endpoint_hostnames.append(read_only_endpoint.split(":")[0])
        else:
            raise ValueError("Malformed endpoint")
    return read_only_endpoint_hostnames


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

    await ops_test.model.destroy_units(leader_unit)

    count = len(ops_test.model.applications[application_name].units)

    application = ops_test.model.applications[application_name]
    await ops_test.model.block_until(lambda: len(application.units) == count)

    if count > 0:
        await ops_test.model.wait_for_idle(
            apps=[application_name],
            status="active",
            raise_on_blocked=True,
            timeout=TIMEOUT,
        )


async def get_units_ip_addresses(ops_test: OpsTest, app_name: str) -> list[str]:
    """Retrieves hostnames of given application units.

    Args:
        ops_test: The ops test framework instance
        app_name: The name of the application
    Returns:
        a list that contains the hostnames of a given application
    """
    return [
        await get_unit_ip(ops_test, app_unit.name)
        for app_unit in ops_test.model.applications[app_name].units
    ]


async def check_read_only_endpoints(ops_test: OpsTest, app_name: str, relation_name: str):
    """Checks that read-only-endpoints are correctly set.

    Args:
        ops_test: The ops test framework instance
        app_name: The name of the application
        relation_name: The name of the relation
    """
    # check update for read-only-endpoints
    relation_data = await get_relation_data(
        ops_test=ops_test, application_name=app_name, relation_name=relation_name
    )
    read_only_endpoint_ips = get_read_only_endpoint_ips(relation_data)
    # check that the number of read-only-endpoints is correct
    assert len(ops_test.model.applications[app_name].units) - 1 == len(read_only_endpoint_ips)
    app_ips = await get_units_ip_addresses(ops_test=ops_test, app_name=app_name)
    # check that endpoints are the one of the application
    for read_endpoint_ip in read_only_endpoint_ips:
        assert read_endpoint_ip in app_ips


# TODO: Delete before merging
async def get_tls_ca(ops_test: OpsTest, unit_name: str) -> str:
    """Returns the TLS CA used by the unit.

    Args:
        ops_test: The ops test framework instance
        unit_name: The name of the unit

    Returns:
        TLS CA or an empty string if there is no CA.
    """
    raw_data = (await ops_test.juju("show-unit", unit_name))[1]
    if not raw_data:
        raise ValueError(f"no unit info could be grabbed for {unit_name}")
    data = yaml.safe_load(raw_data)
    # Filter the data based on the relation name.
    relation_data = [
        v for v in data[unit_name]["relation-info"] if v["endpoint"] == "certificates"
    ]
    if len(relation_data) == 0:
        return ""
    return json.loads(relation_data[0]["application-data"]["certificates"])[0].get("ca")


# TODO: Delete before merging
async def unit_file_md5(ops_test: OpsTest, unit_name: str, file_path: str) -> str:
    """Return md5 hash for given file.

    Args:
        ops_test: The ops test framework instance
        unit_name: The name of the unit
        file_path: The path to the file

    Returns:
        md5sum hash string
    """
    try:
        _, md5sum_raw, _ = await ops_test.juju("ssh", unit_name, "sudo", "md5sum", file_path)

        return md5sum_raw.strip().split()[0]

    except Exception:
        return None
