#!/usr/bin/env python3
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

from constants import CHARMED_MYSQL_COMMON_DIRECTORY

from ..helpers import (
    delete_file_or_directory_in_unit,
    execute_queries_on_unit,
    fetch_credentials,
    generate_random_string,
    get_primary_unit,
    get_primary_unit_wrapper,
    get_server_config_credentials,
    ls_la_in_unit,
    read_contents_from_file_in_unit,
    retrieve_database_variable_value,
    scale_application,
    stop_running_flush_mysql_cronjobs,
    write_content_to_file_in_unit,
)
from .high_availability_helpers import (
    clean_up_database_and_table,
    ensure_all_units_continuous_writes_incrementing,
    ensure_n_online_mysql_members,
    get_application_name,
    insert_data_into_mysql_and_validate_replication,
)

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = METADATA["name"]
ANOTHER_APP_NAME = f"second{APP_NAME}"
TIMEOUT = 17 * 60


@pytest.mark.group(1)
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


@pytest.mark.group(2)
@pytest.mark.abort_on_fail
async def test_custom_variables(ops_test: OpsTest, highly_available_cluster) -> None:
    """Query database for custom variables."""
    mysql_application_name = get_application_name(ops_test, "mysql")
    application = ops_test.model.applications[mysql_application_name]

    for unit in application.units:
        custom_vars = {}
        custom_vars["max_connections"] = 100
        for k, v in custom_vars.items():
            logger.info(f"Checking that {k} is set to {v} on {unit.name}")
            value = await retrieve_database_variable_value(ops_test, unit, k)
            assert value == v, f"Variable {k} is not set to {v}"


@pytest.mark.group(3)
@pytest.mark.abort_on_fail
async def test_consistent_data_replication_across_cluster(
    ops_test: OpsTest, highly_available_cluster
) -> None:
    """Confirm that data is replicated from the primary node to all the replicas."""
    mysql_application_name = get_application_name(ops_test, "mysql")

    # assert that there are 3 units in the mysql cluster
    assert len(ops_test.model.applications[mysql_application_name].units) == 3

    database_name, table_name = "test-check-consistency", "data"
    await insert_data_into_mysql_and_validate_replication(ops_test, database_name, table_name)
    await clean_up_database_and_table(ops_test, database_name, table_name)

    await ensure_all_units_continuous_writes_incrementing(ops_test)


@pytest.mark.group(4)
@pytest.mark.abort_on_fail
async def test_kill_primary_check_reelection(ops_test: OpsTest, highly_available_cluster) -> None:
    """Confirm that a new primary is elected when the current primary is torn down."""
    mysql_application_name = get_application_name(ops_test, "mysql")
    application = ops_test.model.applications[mysql_application_name]

    await ensure_all_units_continuous_writes_incrementing(ops_test)

    primary_unit = await get_primary_unit_wrapper(ops_test, mysql_application_name)
    primary_unit_name = primary_unit.name

    # Destroy the primary unit and block to ensure that the
    # juju status changed from active
    logger.info("Destroying leader unit")
    await ops_test.model.destroy_units(primary_unit.name)

    async with ops_test.fast_forward("60s"):
        await ops_test.model.block_until(lambda: len(application.units) == 2)
        await ops_test.model.wait_for_idle(
            apps=[mysql_application_name],
            status="active",
            raise_on_blocked=True,
            timeout=TIMEOUT,
        )

    # Wait for unit to be destroyed and confirm that the new primary unit is different
    new_primary_unit = await get_primary_unit_wrapper(ops_test, mysql_application_name)

    assert primary_unit_name != new_primary_unit.name, "Primary has not changed"

    # Add the unit back and wait until it is active
    async with ops_test.fast_forward("60s"):
        logger.info("Scaling back to 3 units")
        await scale_application(ops_test, mysql_application_name, 3)

        # wait (and retry) until the killed pod is back online in the mysql cluster
        assert await ensure_n_online_mysql_members(
            ops_test, 3
        ), "Old primary has not come back online after being killed"

    await ensure_all_units_continuous_writes_incrementing(ops_test)

    database_name, table_name = "test-kill-primary-check-reelection", "data"
    await insert_data_into_mysql_and_validate_replication(ops_test, database_name, table_name)
    await clean_up_database_and_table(ops_test, database_name, table_name)


@pytest.mark.group(5)
@pytest.mark.abort_on_fail
async def test_scaling_without_data_loss(ops_test: OpsTest, highly_available_cluster) -> None:
    """Test that data is preserved during scale up and scale down."""
    # Insert values into test table from the primary unit
    app = get_application_name(ops_test, "mysql")
    application = ops_test.model.applications[app]

    random_unit = application.units[0]
    server_config_credentials = await get_server_config_credentials(random_unit)

    primary_unit = await get_primary_unit_wrapper(
        ops_test,
        app,
    )
    primary_unit_address = await primary_unit.get_public_address()

    random_chars = generate_random_string(40)
    create_records_sql = [
        "CREATE DATABASE IF NOT EXISTS test",
        "CREATE TABLE IF NOT EXISTS test.instance_state_replication (id varchar(40), primary key(id))",
        f"INSERT INTO test.instance_state_replication VALUES ('{random_chars}')",
    ]

    await execute_queries_on_unit(
        primary_unit_address,
        server_config_credentials["username"],
        server_config_credentials["password"],
        create_records_sql,
        commit=True,
    )

    old_unit_names = [unit.name for unit in ops_test.model.applications[app].units]

    # Add a unit and wait until it is active
    async with ops_test.fast_forward("60s"):
        await scale_application(ops_test, app, 4)

    added_unit = [unit for unit in application.units if unit.name not in old_unit_names][0]

    # Ensure that all units have the above inserted data
    select_data_sql = [
        f"SELECT * FROM test.instance_state_replication WHERE id = '{random_chars}'",
    ]

    for unit in application.units:
        unit_address = await unit.get_public_address()
        output = await execute_queries_on_unit(
            unit_address,
            server_config_credentials["username"],
            server_config_credentials["password"],
            select_data_sql,
        )
        assert random_chars in output

    # Destroy the recently created unit and wait until the application is active
    await ops_test.model.destroy_units(added_unit.name)
    async with ops_test.fast_forward("60s"):
        await ops_test.model.block_until(lambda: len(ops_test.model.applications[app].units) == 3)
        await ops_test.model.wait_for_idle(
            apps=[app],
            status="active",
            raise_on_blocked=True,
            timeout=TIMEOUT,
        )

    # Ensure that the data still exists in all the units
    for unit in application.units:
        unit_address = await unit.get_public_address()
        output = await execute_queries_on_unit(
            unit_address,
            server_config_credentials["username"],
            server_config_credentials["password"],
            select_data_sql,
        )
        assert random_chars in output


@pytest.mark.group(6)
async def test_cluster_isolation(ops_test: OpsTest, highly_available_cluster) -> None:
    """Test for cluster data isolation.

    This test creates a new cluster, create a new table on both cluster, write a single record with
    the application name for each cluster, retrieve and compare these records, asserting they are
    not the same.
    """
    app = get_application_name(ops_test, "mysql")
    apps = [app, ANOTHER_APP_NAME]

    # Build and deploy secondary charm
    charm = await ops_test.build_charm(".")

    await ops_test.model.deploy(
        charm,
        application_name=ANOTHER_APP_NAME,
        num_units=1,
        base="ubuntu@22.04",
    )
    async with ops_test.fast_forward("60s"):
        await ops_test.model.block_until(
            lambda: len(ops_test.model.applications[ANOTHER_APP_NAME].units) == 1
        )
        await ops_test.model.wait_for_idle(
            apps=[ANOTHER_APP_NAME],
            status="active",
            raise_on_blocked=True,
            timeout=TIMEOUT,
        )

    # retrieve connection data for each cluster
    connection_data = {}
    for application in apps:
        random_unit = ops_test.model.applications[application].units[0]
        server_config_credentials = await get_server_config_credentials(random_unit)
        primary_unit = await get_primary_unit(ops_test, random_unit, application)

        primary_unit_address = await primary_unit.get_public_address()

        connection_data[application] = {
            "host": primary_unit_address,
            "username": server_config_credentials["username"],
            "password": server_config_credentials["password"],
        }

    # write single distinct record to each cluster
    for application in apps:
        create_records_sql = [
            "CREATE DATABASE IF NOT EXISTS test",
            "DROP TABLE IF EXISTS test.cluster_isolation_table",
            "CREATE TABLE test.cluster_isolation_table (id varchar(40), primary key(id))",
            f"INSERT INTO test.cluster_isolation_table VALUES ('{application}')",
        ]

        await execute_queries_on_unit(
            connection_data[application]["host"],
            connection_data[application]["username"],
            connection_data[application]["password"],
            create_records_sql,
            commit=True,
        )

    result = []
    # read single record from each cluster
    for application in apps:
        read_records_sql = ["SELECT id FROM test.cluster_isolation_table"]

        output = await execute_queries_on_unit(
            connection_data[application]["host"],
            connection_data[application]["username"],
            connection_data[application]["password"],
            read_records_sql,
            commit=False,
        )

        assert len(output) == 1, "Just one record must exist on the test table"
        result.append(output[0])

    assert result[0] != result[1], "Writes from one cluster are replicated to another cluster."


@pytest.mark.group(7)
@pytest.mark.abort_on_fail
async def test_log_rotation(ops_test: OpsTest, highly_available_cluster) -> None:
    """Test the log rotation of text files."""
    app = get_application_name(ops_test, "mysql")
    unit = ops_test.model.applications[app].units[0]

    log_types = ["error", "general", "audit"]
    log_files = ["error.log", "general.log", "audit.log"]
    archive_directories = [
        "archive_error",
        "archive_general",
        "archive_audit",
    ]

    logger.info("Removing the cron file")
    await delete_file_or_directory_in_unit(ops_test, unit.name, "/etc/cron.d/flush_mysql_logs")

    logger.info("Stopping any running logrotate jobs")
    await stop_running_flush_mysql_cronjobs(ops_test, unit.name)

    logger.info("Removing existing archive directories")
    for archive_directory in archive_directories:
        await delete_file_or_directory_in_unit(
            ops_test,
            unit.name,
            f"{CHARMED_MYSQL_COMMON_DIRECTORY}/var/log/mysql/{archive_directory}/",
        )

    logger.info("Writing some data to the text log files")
    for log in log_types:
        log_path = f"{CHARMED_MYSQL_COMMON_DIRECTORY}/var/log/mysql/{log}.log"
        await write_content_to_file_in_unit(ops_test, unit, log_path, f"test {log} content\n")

    logger.info("Ensuring only log files exist")
    ls_la_output = await ls_la_in_unit(
        ops_test, unit.name, f"{CHARMED_MYSQL_COMMON_DIRECTORY}/var/log/mysql/"
    )

    assert len(ls_la_output) == len(
        log_files
    ), f"❌ files other than log files exist {ls_la_output}"
    directories = [line.split()[-1] for line in ls_la_output]
    assert sorted(directories) == sorted(
        log_files
    ), f"❌ file other than logs files exist: {ls_la_output}"

    logger.info("Executing logrotate")
    return_code, stdout, _ = await ops_test.juju(
        "ssh", unit.name, "sudo", "logrotate", "-f", "/etc/logrotate.d/flush_mysql_logs"
    )
    assert return_code == 0, f"❌ logrotate exited with code {return_code} and stdout {stdout}"

    logger.info("Ensuring log files and archive directories exist")
    ls_la_output = await ls_la_in_unit(
        ops_test, unit.name, f"{CHARMED_MYSQL_COMMON_DIRECTORY}/var/log/mysql/"
    )

    assert len(ls_la_output) == len(
        log_files + archive_directories
    ), f"❌ unexpected files/directories in log directory: {ls_la_output}"
    directories = [line.split()[-1] for line in ls_la_output]
    assert sorted(directories) == sorted(
        log_files + archive_directories
    ), f"❌ unexpected files/directories in log directory: {ls_la_output}"

    logger.info("Ensuring log files were rotated")
    for log in set(log_types):
        file_contents = await read_contents_from_file_in_unit(
            ops_test, unit, f"{CHARMED_MYSQL_COMMON_DIRECTORY}/var/log/mysql/{log}.log"
        )
        assert f"test {log} content" not in file_contents, f"❌ log file {log}.log not rotated"

        ls_la_output = await ls_la_in_unit(
            ops_test, unit.name, f"{CHARMED_MYSQL_COMMON_DIRECTORY}/var/log/mysql/archive_{log}/"
        )
        assert len(ls_la_output) == 1, f"❌ more than 1 file in archive directory: {ls_la_output}"

        filename = ls_la_output[0].split()[-1]
        file_contents = await read_contents_from_file_in_unit(
            ops_test,
            unit,
            f"{CHARMED_MYSQL_COMMON_DIRECTORY}/var/log/mysql/archive_{log}/{filename}",
        )
        assert f"test {log} content" in file_contents, f"❌ log file {log}.log not rotated"
