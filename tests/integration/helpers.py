# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import itertools
import json
import logging
import secrets
import string
import subprocess
import tempfile
from typing import Dict, List, Optional, Set

import juju.unit
import yaml
from juju.model import Model
from juju.unit import Unit
from mysql.connector.errors import (
    DatabaseError,
    InterfaceError,
    OperationalError,
    ProgrammingError,
)
from pytest_operator.plugin import OpsTest
from tenacity import RetryError, Retrying, retry, stop_after_attempt, wait_fixed

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
            primary_unit = [unit for unit in units if unit.name == unit_name][0]
            break

    if not primary_unit:
        raise ValueError("Unable to find primary unit")
    return primary_unit


async def get_server_config_credentials(unit: Unit) -> Dict:
    """Helper to run an action to retrieve server config credentials.

    Args:
        unit: The juju unit on which to run the get-password action for server-config credentials

    Returns:
        A dictionary with the server config username and password
    """
    return await juju_.run_action(unit, "get-password", username=SERVER_CONFIG_USERNAME)


async def fetch_credentials(unit: Unit, username: str = None) -> Dict:
    """Helper to run an action to fetch credentials.

    Args:
        unit: The juju unit on which to run the get-password action for credentials

    Returns:
        A dictionary with the server config username and password
    """
    if username is None:
        return await juju_.run_action(unit, "get-password")
    return await juju_.run_action(unit, "get-password", username=username)


async def rotate_credentials(unit: Unit, username: str = None, password: str = None) -> Dict:
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


async def get_legacy_mysql_credentials(unit: Unit) -> Dict:
    """Helper to run an action to retrieve legacy mysql config credentials.

    Args:
        unit: The juju unit on which to run the get-legacy-mysql-credentials action

    Returns:
        A dictionary with the credentials
    """
    return await juju_.run_action(unit, "get-legacy-mysql-credentials")


@retry(stop=stop_after_attempt(20), wait=wait_fixed(5), reraise=True)
async def get_system_user_password(unit: Unit, user: str) -> Dict:
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
    queries: List[str],
    commit: bool = False,
    raw: bool = False,
) -> List:
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
    credentials: Dict, *, retry_if_not_possible=False, **extra_opts
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


async def get_model_logs(ops_test: OpsTest, log_level: str, log_lines: int = 100) -> str:
    """Return the juju logs from a specific model.

    Args:
        ops_test: The ops test object passed into every test case
        log_level: The logging level to return messages from
        log_lines: The maximum lines to return at once
    """
    _, output, _ = await ops_test.juju(
        "debug-log",
        f"--model={ops_test.model.info.name}",
        f"--level={log_level}",
        f"--lines={log_lines}",
        "--no-tail",
    )

    return output


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


@retry(stop=stop_after_attempt(12), wait=wait_fixed(15), reraise=True)
async def is_unit_in_cluster(unit_name: str, action_unit: juju.unit.Unit) -> bool:
    """Check is unit is online in the cluster.

    Args:
        unit_name: The name of the unit to be tested
        action_unit: a different unit to run get status action
    Returns:
        A boolean
    """
    results = await juju_.run_action(action_unit, action_name="get-cluster-status")
    cluster_topology = results["status"]["defaultreplicaset"]["topology"]

    for k, v in cluster_topology.items():
        if k.replace("-", "/") == unit_name and v.get("status") == "online":
            return True
    raise TimeoutError


def cut_network_from_unit(machine_name: str) -> None:
    """Cut network from a lxc container.

    Args:
        machine_name: lxc container hostname
    """
    # apply a mask (device type `none`)
    cut_network_command = f"lxc config device add {machine_name} eth0 none"
    subprocess.check_call(cut_network_command.split())


def restore_network_for_unit(machine_name: str) -> None:
    """Restore network from a lxc container.

    Args:
        machine_name: lxc container hostname
    """
    # remove mask from eth0
    restore_network_command = f"lxc config device remove {machine_name} eth0"
    subprocess.check_call(restore_network_command.split())


async def unit_hostname(ops_test: OpsTest, unit_name: str) -> str:
    """Get hostname for a unit.

    Args:
        ops_test: The ops test object passed into every test case
        unit_name: The name of the unit to be tested
    Returns:
        The machine/container hostname
    """
    _, raw_hostname, _ = await ops_test.juju("ssh", unit_name, "hostname")
    return raw_hostname.strip()


@retry(stop=stop_after_attempt(20), wait=wait_fixed(15))
async def wait_network_restore(ops_test: OpsTest, unit_name: str) -> None:
    """Wait until network is restored.

    Args:
        ops_test: The ops test object passed into every test case
        unit_name: The name of the unit
        old_ip: old registered IP address
    """
    return_code, stdout, _ = await ops_test.juju("ssh", unit_name, "ip", "a")
    if return_code != 0:
        raise Exception

    juju_unit_ip = await get_unit_ip(ops_test, unit_name)

    if juju_unit_ip in stdout:
        raise Exception


async def graceful_stop_server(ops_test: OpsTest, unit_name: str) -> None:
    """Gracefully stop server.

    Args:
        ops_test: The ops test object passed into every test case
        unit_name: The name of the unit to be tested
    """
    # send TERM signal to mysql daemon, which trigger shutdown process
    await ops_test.juju("ssh", unit_name, "sudo", "pkill", "-15", "mysqld")

    # hold execution until process is stopped
    try:
        for attempt in Retrying(stop=stop_after_attempt(45), wait=wait_fixed(2)):
            with attempt:
                if await get_process_pid(ops_test, unit_name, "mysqld"):
                    raise Exception
    except RetryError:
        raise Exception("Failed to gracefully stop server.")


async def start_server(ops_test: OpsTest, unit_name: str) -> None:
    """Start a previously stopped machine.

    Args:
        ops_test: The ops test object passed into every test case
        unit_name: The name of the unit to be tested
    """
    await ops_test.juju("ssh", unit_name, "sudo", "snap", "restart", "charmed-mysql.mysqld")

    # hold execution until process is started
    try:
        for attempt in Retrying(stop=stop_after_attempt(12), wait=wait_fixed(5)):
            with attempt:
                if not await get_process_pid(ops_test, unit_name, "mysqld"):
                    raise Exception
    except RetryError:
        raise Exception("Failed to start server.")


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
    status = await ops_test.model.get_status()  # noqa: F821
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


def get_read_only_endpoints(relation_data: list) -> Set[str]:
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
        except json.JSONDecodeError:
            raise ValueError("Relation data are not valid JSON.")

    return read_only_endpoints


async def get_leader_unit(
    ops_test: Optional[OpsTest], app_name: str, model: Optional[Model] = None
) -> Optional[Unit]:
    """Get the leader unit of a given application.

    Args:
        ops_test: The ops test framework instance
        app_name: The name of the application
        model: The model to use (overrides ops_test.model)
    """
    leader_unit = None
    if not model:
        model = ops_test.model
    for unit in model.applications[app_name].units:
        if await unit.is_leader_from_status():
            leader_unit = unit
            break

    return leader_unit


def get_read_only_endpoint_ips(relation_data: list) -> List[str]:
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


async def get_units_ip_addresses(ops_test: OpsTest, app_name: str) -> List[str]:
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


async def get_controller_machine(ops_test: OpsTest) -> str:
    """Return controller machine hostname.

    Args:
        ops_test: The ops test framework instance
    Returns:
        Controller hostname (str)
    """
    _, raw_controller, _ = await ops_test.juju("show-controller")

    controller = yaml.safe_load(raw_controller.strip())

    return [
        machine.get("instance-id")
        for machine in controller[ops_test.controller_name]["controller-machines"].values()
    ][0]


def is_machine_reachable_from(origin_machine: str, target_machine: str) -> bool:
    """Test network reachability between hosts.

    Args:
        origin_machine: hostname of the machine to test connection from
        target_machine: hostname of the machine to test connection to
    """
    try:
        subprocess.check_call(f"lxc exec {origin_machine} -- ping -c 3 {target_machine}".split())
        return True
    except subprocess.CalledProcessError:
        return False


async def write_random_chars_to_test_table(ops_test: OpsTest, primary_unit: Unit) -> str:
    """Writes to common test table.

    Args:
        ops_test: The ops test framework instance
        primary_unit: the R/W unit to write the data
    Returns:
        The random chars(str) written to test table.
    """
    create_records_sql = [
        "CREATE DATABASE IF NOT EXISTS test",
        "DROP TABLE IF EXISTS test.data_replication_table",
        "CREATE TABLE test.data_replication_table (id varchar(40), primary key(id))",
        (
            "INSERT INTO test.data_replication_table"
            f" VALUES ('{(random_chars := generate_random_string(40))}')"
        ),
    ]

    primary_unit_ip = await get_unit_ip(ops_test, primary_unit.name)
    server_config_password = await get_system_user_password(primary_unit, SERVER_CONFIG_USERNAME)

    await execute_queries_on_unit(
        primary_unit_ip,
        SERVER_CONFIG_USERNAME,
        server_config_password,
        create_records_sql,
        commit=True,
    )

    return random_chars


async def retrieve_database_variable_value(
    ops_test: OpsTest, unit: Unit, variable_name: str
) -> str:
    """Retrieve a database variable value as a string.

    Args:
        ops_test: The ops test framework instance
        unit: The unit to retrieve the variable
        variable_name: The name of the variable to retrieve
    Returns:
        The variable value (str)
    """
    unit_ip = await get_unit_ip(ops_test, unit.name)
    server_config_password = await get_system_user_password(unit, SERVER_CONFIG_USERNAME)
    queries = [f"SELECT @@{variable_name};"]

    output = await execute_queries_on_unit(
        unit_ip, SERVER_CONFIG_USERNAME, server_config_password, queries
    )

    return output[0]


async def get_tls_ca(
    ops_test: OpsTest,
    unit_name: str,
) -> str:
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


async def get_cluster_status(unit: Unit, cluster_set: Optional[bool] = False) -> Dict:
    """Get the cluster status by running the get-cluster-status action.

    Args:
        ops_test: The ops test framework
        unit: The unit on which to execute the action on

    Returns:
        A dictionary representing the cluster status
    """
    if cluster_set:
        result = await juju_.run_action(
            unit, "get-cluster-status", **{"--wait": "5m", "cluster-set": True}
        )
    else:
        result = await juju_.run_action(unit, "get-cluster-status")
    return result.get("status", {})


async def delete_file_or_directory_in_unit(ops_test: OpsTest, unit_name: str, path: str) -> bool:
    """Delete a file in the provided unit.

    Args:
        ops_test: The ops test framework
        unit_name: The name unit on which to delete the file from
        path: The path of file or directory to delete

    Returns:
        boolean indicating success
    """
    if path.strip() in ["/", "."]:
        return

    try:
        return_code, _, _ = await ops_test.juju(
            "ssh", unit_name, "sudo", "find", path, "-maxdepth", "1", "-delete"
        )

        return return_code == 0
    except Exception:
        return False


async def write_content_to_file_in_unit(
    ops_test: OpsTest, unit: Unit, path: str, content: str
) -> None:
    """Write content to the file in the provided unit.

    Args:
        ops_test: The ops test framework
        unit: THe unit in which to write to file in
        path: The path at which to write the content to
        content: The content to write to the file.
    """
    with tempfile.NamedTemporaryFile(mode="w") as temp_file:
        temp_file.write(content)
        temp_file.flush()

        await unit.scp_to(temp_file.name, "/tmp/file")

    return_code, _, _ = await ops_test.juju("ssh", unit.name, "sudo", "mv", "/tmp/file", path)
    assert return_code == 0

    return_code, _, _ = await ops_test.juju(
        "ssh", unit.name, "sudo", "chown", "snap_daemon:root", path
    )
    assert return_code == 0


async def read_contents_from_file_in_unit(ops_test: OpsTest, unit: Unit, path: str) -> str:
    """Read contents from file in the provided unit.

    Args:
        ops_test: The ops test framework
        unit: The unit in which to read file from
        path: The path from which to read content from

    Returns:
        the contents of the file
    """
    return_code, _, _ = await ops_test.juju("ssh", unit.name, "sudo", "cp", path, "/tmp/file")
    assert return_code == 0

    return_code, _, _ = await ops_test.juju(
        "ssh", unit.name, "sudo", "chown", "ubuntu:ubuntu", "/tmp/file"
    )
    assert return_code == 0

    with tempfile.NamedTemporaryFile(mode="r+") as temp_file:
        await unit.scp_from("/tmp/file", temp_file.name)

        temp_file.seek(0)

        contents = ""
        for line in temp_file:
            contents += line
            contents += "\n"

    return_code, _, _ = await ops_test.juju("ssh", unit.name, "sudo", "rm", "/tmp/file")
    assert return_code == 0

    return contents


async def ls_la_in_unit(ops_test: OpsTest, unit_name: str, directory: str) -> list[str]:
    """Returns the output of ls -la in unit.

    Args:
        ops_test: The ops test framework
        unit_name: The name of unit in which to run ls -la
        path: The path from which to run ls -la

    Returns:
        a list of files returned by ls -la
    """
    return_code, output, _ = await ops_test.juju("ssh", unit_name, "sudo", "ls", "-la", directory)
    assert return_code == 0

    ls_output = output.split("\n")[1:]

    return [
        line.strip("\r")
        for line in ls_output
        if len(line.strip()) > 0 and line.split()[-1] not in [".", ".."]
    ]


async def stop_running_flush_mysql_cronjobs(ops_test: OpsTest, unit_name: str) -> None:
    """Stop running any logrotate jobs that may have been triggered by cron.

    Args:
        ops_test: The ops test object passed into every test case
        unit_name: The name of the unit to be tested
    """
    # send TERM signal to mysql daemon, which trigger shutdown process
    await ops_test.juju(
        "ssh",
        unit_name,
        "sudo",
        "pkill",
        "-15",
        "-f",
        "logrotate -f /etc/logrotate.d/flush_mysql_logs",
    )

    # hold execution until process is stopped
    try:
        for attempt in Retrying(stop=stop_after_attempt(45), wait=wait_fixed(2)):
            with attempt:
                if await get_process_pid(ops_test, unit_name, "logrotate"):
                    raise Exception
    except RetryError:
        raise Exception("Failed to stop the flush_mysql_logs logrotate process.")


def get_unit_by_index(app_name: str, units: list, index: int):
    """Get unit by index.

    Args:
        app_name: Name of the application
        units: List of units
        index: index of the unit to get
    """
    for unit in units:
        if unit.name == f"{app_name}/{index}":
            return unit
