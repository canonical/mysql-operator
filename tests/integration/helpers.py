# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.


import itertools
import json
import re
import secrets
import string
import subprocess
from typing import Dict, List, Optional, Set

import yaml
from connector import MysqlConnector
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


@retry(stop=stop_after_attempt(20), wait=wait_fixed(5), reraise=True)
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

    # strip and remove escape characters `\`
    string_output = matches.group(1).strip().replace("\\", "")

    cluster_status = json.loads(string_output)

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


async def get_system_user_password(unit: Unit, user: str) -> Dict:
    """Helper to run an action to retrieve system user password.

    Args:
        unit: The juju unit on which to run the get-password action

    Returns:
        A dictionary with the credentials
    """
    action = await unit.run_action("get-password", username=user)
    result = await action.wait()

    return result.results.get("password")


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


@retry(stop=stop_after_attempt(8), wait=wait_fixed(15), reraise=True)
def is_connection_possible(credentials: Dict, **extra_opts) -> bool:
    """Test a connection to a MySQL server.

    Args:
        credentials: A dictionary with the credentials to test
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
        _, raw_pid, _ = await ops_test.juju("ssh", unit_name, "pgrep", process)
        pid = int(raw_pid.strip())

        return pid
    except Exception:
        return None


@retry(stop=stop_after_attempt(12), wait=wait_fixed(15), reraise=True)
async def is_unit_in_cluster(ops_test: OpsTest, unit_name: str, action_unit_name: str) -> bool:
    """Check is unit is online in the cluster.

    Args:
        ops_test: The ops test object passed into every test case
        unit_name: The name of the unit to be tested
        action_unit_name: a different unit to run get status action
    Returns:
        A boolean
    """
    _, raw_status, _ = await ops_test.juju(
        "run-action", action_unit_name, "get-cluster-status", "--format=yaml", "--wait"
    )

    status = yaml.safe_load(raw_status.strip())

    cluster_topology = status[list(status.keys())[0]]["results"]["defaultreplicaset"]["topology"]

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


@retry(stop=stop_after_attempt(8), wait=wait_fixed(15))
def wait_network_restore(model_name: str, hostname: str, old_ip: str) -> None:
    """Wait until network is restored.

    Args:
        model_name: The name of the model
        hostname: The name of the instance
        old_ip: old registered IP address
    """
    if instance_ip(model_name, hostname) == old_ip:
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
    await ops_test.juju("ssh", unit_name, "sudo", "systemctl", "restart", "mysql")

    # hold execution until process is started
    try:
        for attempt in Retrying(stop=stop_after_attempt(12), wait=wait_fixed(5)):
            with attempt:
                if not await get_process_pid(ops_test, unit_name, "mysqld"):
                    raise Exception
    except RetryError:
        raise Exception("Failed to start server.")


async def get_primary_unit_wrapper(ops_test: OpsTest, app_name: str) -> Unit:
    """Wrapper for getting primary.

    Args:
        ops_test: The ops test object passed into every test case
        app_name: The name of the application
    Returns:
        The primary Unit object
    """
    unit = ops_test.model.applications[app_name].units[0]
    cluster = cluster_name(unit, ops_test.model.info.name)

    server_config_password = await get_system_user_password(unit, SERVER_CONFIG_USERNAME)

    return await get_primary_unit(
        ops_test, unit, app_name, cluster, SERVER_CONFIG_USERNAME, server_config_password
    )


async def get_unit_ip(ops_test: OpsTest, unit_name: str) -> str:
    """Wrapper for getting unit ip.

    Args:
        ops_test: The ops test object passed into every test case
        unit_name: The name of the unit to be tested
    Returns:
        The (str) ip of the unit
    """
    return instance_ip(ops_test.model.info.name, await unit_hostname(ops_test, unit_name))


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


def get_read_only_endpoint_hostnames(relation_data: list) -> List[str]:
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
            timeout=1000,
        )


async def get_unit_hostname(ops_test: OpsTest, app_name: str) -> List[str]:
    """Retrieves hostnames of given application units.

    Args:
        ops_test: The ops test framework instance
        app_name: The name of the application
    Returns:
        a list that contains the hostnames of a given application
    """
    units = [app_unit.name for app_unit in ops_test.model.applications[app_name].units]

    return [await unit_hostname(ops_test, unit_name) for unit_name in units]


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
    read_only_endpoints = get_read_only_endpoint_hostnames(relation_data)
    # check that the number of read-only-endpoints is correct
    assert len(ops_test.model.applications[app_name].units) - 1 == len(read_only_endpoints)
    app_hostnames = await get_unit_hostname(ops_test=ops_test, app_name=app_name)
    # check that endpoints are the one of the application
    for r_endpoint in read_only_endpoints:
        assert r_endpoint in app_hostnames


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
            f" VALUES ('{(random_chars:=generate_random_string(40))}')"
        ),
    ]

    primary_unit_ip = await get_unit_ip(ops_test, primary_unit.name)
    server_config_password = await get_system_user_password(primary_unit, SERVER_CONFIG_USERNAME)

    await execute_commands_on_unit(
        primary_unit_ip,
        SERVER_CONFIG_USERNAME,
        server_config_password,
        create_records_sql,
        commit=True,
    )

    return random_chars


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
