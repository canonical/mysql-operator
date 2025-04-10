#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
import dataclasses
import json
import logging
import os
import socket
import subprocess
import time
from pathlib import Path

import boto3
import botocore.exceptions
import pytest
from pytest_operator.plugin import OpsTest

from . import juju_
from .helpers import (
    execute_queries_on_unit,
    get_primary_unit_wrapper,
    get_server_config_credentials,
    get_unit_ip,
    rotate_credentials,
    scale_application,
)
from .high_availability.high_availability_helpers import (
    deploy_and_scale_mysql,
    insert_data_into_mysql_and_validate_replication,
)

logger = logging.getLogger(__name__)

S3_INTEGRATOR = "s3-integrator"
S3_INTEGRATOR_CHANNEL = "latest/stable"
TIMEOUT = 10 * 60
CLUSTER_ADMIN_USER = "clusteradmin"
CLUSTER_ADMIN_PASSWORD = "clusteradminpassword"
SERVER_CONFIG_USER = "serverconfig"
SERVER_CONFIG_PASSWORD = "serverconfigpassword"
ROOT_USER = "root"
ROOT_PASSWORD = "rootpassword"
DATABASE_NAME = "backup-database"
TABLE_NAME = "backup-table"
ANOTHER_S3_CLUSTER_REPOSITORY_ERROR_MESSAGE = "S3 repository claimed by another cluster"
MOVE_RESTORED_CLUSTER_TO_ANOTHER_S3_REPOSITORY_ERROR = (
    "Move restored cluster to another S3 repository"
)

backup_id, value_before_backup, value_after_backup = "", None, None
MICROCEPH_BUCKET = "testbucket"


@dataclasses.dataclass(frozen=True)
class MicrocephConnectionInformation:
    access_key_id: str
    secret_access_key: str
    bucket: str


@pytest.fixture(scope="session")
def microceph():
    if not os.environ.get("CI") == "true":
        raise Exception("Not running on CI. Skipping microceph installation")
    logger.info("Setting up microceph")
    subprocess.run(["sudo", "snap", "install", "microceph"], check=True)
    subprocess.run(["sudo", "microceph", "cluster", "bootstrap"], check=True)
    subprocess.run(["sudo", "microceph", "disk", "add", "loop,4G,3"], check=True)
    subprocess.run(["sudo", "microceph", "enable", "rgw"], check=True)
    output = subprocess.run(
        [
            "sudo",
            "microceph.radosgw-admin",
            "user",
            "create",
            "--uid",
            "test",
            "--display-name",
            "test",
        ],
        capture_output=True,
        check=True,
        encoding="utf-8",
    ).stdout
    key = json.loads(output)["keys"][0]
    key_id = key["access_key"]
    secret_key = key["secret_key"]
    logger.info("Creating microceph bucket")
    for attempt in range(3):
        try:
            boto3.client(
                "s3",
                endpoint_url="http://localhost",
                aws_access_key_id=key_id,
                aws_secret_access_key=secret_key,
            ).create_bucket(Bucket=MICROCEPH_BUCKET)
        except botocore.exceptions.EndpointConnectionError:
            if attempt == 2:
                raise
            # microceph is not ready yet
            logger.info("Unable to connect to microceph via S3. Retrying")
            time.sleep(1)
        else:
            break
    logger.info("Set up microceph")
    return MicrocephConnectionInformation(key_id, secret_key, MICROCEPH_BUCKET)


@pytest.fixture(scope="session")
def cloud_credentials(microceph) -> dict[str, str]:
    """Read cloud credentials."""
    return {
        "access-key": microceph.access_key_id,
        "secret-key": microceph.secret_access_key,
    }


@pytest.fixture(scope="session")
def cloud_configs(microceph):
    host_ip = socket.gethostbyname(socket.gethostname())
    return {
        "endpoint": f"http://{host_ip}",
        "bucket": microceph.bucket,
        "path": "mysql",
        "region": "",
    }


@pytest.fixture(scope="session", autouse=True)
def clean_backups_from_buckets(cloud_configs, cloud_credentials):
    """Teardown to clean up created backups from clouds."""
    yield

    logger.info("Cleaning backups from cloud buckets")
    session = boto3.session.Session(  # pyright: ignore
        aws_access_key_id=cloud_credentials["access-key"],
        aws_secret_access_key=cloud_credentials["secret-key"],
        region_name=cloud_configs["region"],
    )
    s3 = session.resource("s3", endpoint_url=cloud_configs["endpoint"])
    bucket = s3.Bucket(cloud_configs["bucket"])

    # GCS doesn't support batch delete operation, so delete the objects one by one
    backup_path = str(Path(cloud_configs["path"]) / backup_id)
    for bucket_object in bucket.objects.filter(Prefix=backup_path):
        bucket_object.delete()


async def test_build_and_deploy(ops_test: OpsTest, charm) -> None:
    """Simple test to ensure that the mysql charm gets deployed."""
    mysql_application_name = await deploy_and_scale_mysql(ops_test, charm)

    primary_mysql = await get_primary_unit_wrapper(ops_test, mysql_application_name)

    logger.info("Rotating all mysql credentials")

    await rotate_credentials(
        primary_mysql, username=CLUSTER_ADMIN_USER, password=CLUSTER_ADMIN_PASSWORD
    )
    await rotate_credentials(
        primary_mysql, username=SERVER_CONFIG_USER, password=SERVER_CONFIG_PASSWORD
    )
    await rotate_credentials(primary_mysql, username=ROOT_USER, password=ROOT_PASSWORD)

    logger.info("Deploying s3 integrator")

    await ops_test.model.deploy(S3_INTEGRATOR, channel=S3_INTEGRATOR_CHANNEL, base="ubuntu@22.04")
    await ops_test.model.relate(mysql_application_name, S3_INTEGRATOR)

    await ops_test.model.wait_for_idle(
        apps=[S3_INTEGRATOR],
        status="blocked",
        raise_on_blocked=False,
        timeout=TIMEOUT,
    )


@pytest.mark.abort_on_fail
async def test_backup(ops_test: OpsTest, charm, cloud_configs, cloud_credentials) -> None:
    """Test to create a backup and list backups."""
    mysql_application_name = await deploy_and_scale_mysql(ops_test, charm)

    global backup_id, value_before_backup, value_after_backup

    zeroth_unit = ops_test.model.units[f"{mysql_application_name}/0"]
    assert zeroth_unit

    primary_unit = await get_primary_unit_wrapper(ops_test, mysql_application_name)
    non_primary_units = [
        unit
        for unit in ops_test.model.applications[mysql_application_name].units
        if unit.name != primary_unit.name
    ]

    # insert data into cluster before
    logger.info("Inserting value before backup")
    value_before_backup = await insert_data_into_mysql_and_validate_replication(
        ops_test,
        DATABASE_NAME,
        TABLE_NAME,
    )

    # set the s3 config and credentials
    logger.info("Syncing credentials")

    await ops_test.model.applications[S3_INTEGRATOR].set_config(cloud_configs)
    await juju_.run_action(
        ops_test.model.units[f"{S3_INTEGRATOR}/0"],  # pyright: ignore
        "sync-s3-credentials",
        **cloud_credentials,
    )

    await ops_test.model.wait_for_idle(
        apps=[mysql_application_name, S3_INTEGRATOR],
        status="active",
        timeout=TIMEOUT,
    )

    # list backups
    logger.info("Listing existing backup ids")

    results = await juju_.run_action(zeroth_unit, "list-backups")
    output = results["backups"]
    backup_ids = [line.split("|")[0].strip() for line in output.split("\n")[2:]]

    # create backup
    logger.info("Creating backup")

    results = await juju_.run_action(non_primary_units[0], "create-backup", **{"--wait": "5m"})
    backup_id = results["backup-id"]

    # list backups again and ensure new backup id exists
    logger.info("Listing backup ids post backup")

    results = await juju_.run_action(zeroth_unit, "list-backups")
    output = results["backups"]
    new_backup_ids = [line.split("|")[0].strip() for line in output.split("\n")[2:]]

    assert sorted(new_backup_ids) == sorted(backup_ids + [backup_id])

    # insert data into cluster after backup
    logger.info("Inserting value after backup")
    value_after_backup = await insert_data_into_mysql_and_validate_replication(
        ops_test,
        DATABASE_NAME,
        TABLE_NAME,
    )


@pytest.mark.abort_on_fail
async def test_restore_on_same_cluster(
    ops_test: OpsTest, charm, cloud_configs, cloud_credentials
) -> None:
    """Test to restore a backup to the same mysql cluster."""
    mysql_application_name = await deploy_and_scale_mysql(ops_test, charm)

    logger.info("Scaling mysql application to 1 unit")
    async with ops_test.fast_forward():
        await scale_application(ops_test, mysql_application_name, 1)

    mysql_unit = ops_test.model.units[f"{mysql_application_name}/0"]
    assert mysql_unit
    mysql_unit_address = await get_unit_ip(ops_test, mysql_unit.name)
    server_config_credentials = await get_server_config_credentials(mysql_unit)

    select_values_sql = [f"SELECT id FROM `{DATABASE_NAME}`.`{TABLE_NAME}`"]

    # set the s3 config and credentials
    logger.info("Syncing credentials")

    await ops_test.model.applications[S3_INTEGRATOR].set_config(cloud_configs)
    await juju_.run_action(
        ops_test.model.units[f"{S3_INTEGRATOR}/0"],  # pyright: ignore
        "sync-s3-credentials",
        **cloud_credentials,
    )

    await ops_test.model.wait_for_idle(
        apps=[mysql_application_name, S3_INTEGRATOR],
        status="active",
        timeout=TIMEOUT,
    )

    # restore the backup
    logger.info(f"Restoring backup {backup_id=}")

    await juju_.run_action(mysql_unit, action_name="restore", **{"backup-id": backup_id})

    # ensure the correct inserted values exist
    logger.info(
        "Ensuring that the pre-backup inserted value exists in database, while post-backup inserted value does not"
    )

    values = await execute_queries_on_unit(
        mysql_unit_address,
        server_config_credentials["username"],
        server_config_credentials["password"],
        select_values_sql,
    )
    assert values == [value_before_backup]

    # insert data into cluster after restore
    logger.info("Inserting value after restore")
    value_after_restore = await insert_data_into_mysql_and_validate_replication(
        ops_test,
        DATABASE_NAME,
        TABLE_NAME,
    )

    logger.info("Ensuring that pre-backup and post-restore values exist in the database")

    values = await execute_queries_on_unit(
        mysql_unit_address,
        server_config_credentials["username"],
        server_config_credentials["password"],
        select_values_sql,
    )
    assert value_before_backup
    assert sorted(values) == sorted([value_before_backup, value_after_restore])

    logger.info("Scaling mysql application to 3 units")
    await ops_test.model.applications[mysql_application_name].add_unit(2)
    await ops_test.model.wait_for_idle(
        apps=[mysql_application_name],
        wait_for_exact_units=3,
        timeout=TIMEOUT,
    )

    logger.info("Ensuring inserted values before backup and after restore exist on all units")
    for unit in ops_test.model.applications[mysql_application_name].units:
        await ops_test.model.block_until(
            lambda: unit.workload_status == "active",
            timeout=TIMEOUT,
        )

        unit_address = await get_unit_ip(ops_test, unit.name)

        values = await execute_queries_on_unit(
            unit_address,
            server_config_credentials["username"],
            server_config_credentials["password"],
            select_values_sql,
        )

        assert sorted(values) == sorted([value_before_backup, value_after_restore])

    assert (
        ops_test.model.applications[mysql_application_name].status_message
        == MOVE_RESTORED_CLUSTER_TO_ANOTHER_S3_REPOSITORY_ERROR
    ), "cluster should migrate to blocked status after restore"

    # scale down the cluster to preserve resources for the following tests
    await scale_application(ops_test, mysql_application_name, 0)


@pytest.mark.abort_on_fail
async def test_restore_on_new_cluster(
    ops_test: OpsTest, charm, cloud_configs, cloud_credentials
) -> None:
    """Test to restore a backup on a new mysql cluster."""
    logger.info("Deploying a new mysql cluster")

    new_mysql_application_name = await deploy_and_scale_mysql(
        ops_test,
        charm,
        check_for_existing_application=False,
        mysql_application_name="another-mysql",
        num_units=1,
    )

    # relate to S3 integrator
    await ops_test.model.relate(new_mysql_application_name, S3_INTEGRATOR)

    await ops_test.model.wait_for_idle(
        apps=[new_mysql_application_name, S3_INTEGRATOR],
        timeout=TIMEOUT,
    )

    # rotate all credentials
    logger.info("Rotating all mysql credentials")

    primary_mysql = ops_test.model.units[f"{new_mysql_application_name}/0"]
    assert primary_mysql
    primary_unit_address = await get_unit_ip(ops_test, primary_mysql.name)

    await rotate_credentials(
        primary_mysql, username=CLUSTER_ADMIN_USER, password=CLUSTER_ADMIN_PASSWORD
    )
    await rotate_credentials(
        primary_mysql, username=SERVER_CONFIG_USER, password=SERVER_CONFIG_PASSWORD
    )
    await rotate_credentials(primary_mysql, username=ROOT_USER, password=ROOT_PASSWORD)

    server_config_credentials = await get_server_config_credentials(primary_mysql)
    select_values_sql = [f"SELECT id FROM `{DATABASE_NAME}`.`{TABLE_NAME}`"]

    # set the s3 config and credentials
    logger.info("Syncing credentials")

    await ops_test.model.applications[S3_INTEGRATOR].set_config(cloud_configs)
    await juju_.run_action(
        ops_test.model.units[f"{S3_INTEGRATOR}/0"],  # pyright: ignore
        "sync-s3-credentials",
        **cloud_credentials,
    )

    await ops_test.model.wait_for_idle(
        apps=[new_mysql_application_name, S3_INTEGRATOR],
        timeout=TIMEOUT,
    )

    logger.info("Waiting for blocked application status with another cluster S3 repository")
    await ops_test.model.block_until(
        lambda: ops_test.model.applications[new_mysql_application_name].status_message
        == ANOTHER_S3_CLUSTER_REPOSITORY_ERROR_MESSAGE,
        timeout=TIMEOUT,
    )

    # restore the backup
    logger.info(f"Restoring {backup_id=}")

    await juju_.run_action(primary_mysql, action_name="restore", **{"backup-id": backup_id})

    # ensure the correct inserted values exist
    logger.info(
        "Ensuring that the pre-backup inserted value exists in database, while post-backup inserted value does not"
    )

    values = await execute_queries_on_unit(
        primary_unit_address,
        server_config_credentials["username"],
        server_config_credentials["password"],
        select_values_sql,
    )
    assert values == [value_before_backup]

    # insert data into cluster after restore
    logger.info("Inserting value after restore")
    value_after_restore = await insert_data_into_mysql_and_validate_replication(
        ops_test,
        DATABASE_NAME,
        TABLE_NAME,
        mysql_application_substring="another-mysql",
    )

    logger.info("Ensuring that pre-backup and post-restore values exist in the database")

    values = await execute_queries_on_unit(
        primary_unit_address,
        server_config_credentials["username"],
        server_config_credentials["password"],
        select_values_sql,
    )
    assert value_before_backup
    assert sorted(values) == sorted([value_before_backup, value_after_restore])

    logger.info("Waiting for blocked application status after restore")
    await ops_test.model.block_until(
        lambda: ops_test.model.applications[new_mysql_application_name].status_message
        == MOVE_RESTORED_CLUSTER_TO_ANOTHER_S3_REPOSITORY_ERROR,
        timeout=TIMEOUT,
    )
