# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from pathlib import Path

import pytest
import yaml
from pytest_operator.plugin import OpsTest

from constants import CHARMED_MYSQL_COMMON_DIRECTORY

from .helpers import (
    app_name,
    delete_file_or_directory_in_unit,
    ls_la_in_unit,
    read_contents_from_file_in_unit,
    write_content_to_file_in_unit,
)

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = METADATA["name"]
TIMEOUT = 15 * 60


@pytest.mark.group(1)
@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest, mysql_charm_series: str) -> None:
    """Build and test a unit of the charm."""
    charm = await ops_test.build_charm(".")

    await ops_test.model.deploy(
        charm,
        application_name=APP_NAME,
        num_units=1,
        series=mysql_charm_series,
    )

    # Reduce the update_status frequency until the cluster is deployed
    async with ops_test.fast_forward("60s"):
        await ops_test.model.block_until(
            lambda: ops_test.model.applications[APP_NAME].status == "active",
            timeout=TIMEOUT,
        )


@pytest.mark.group(1)
@pytest.mark.abort_on_fail
async def test_log_rotation(ops_test: OpsTest) -> None:
    """Test the log rotation of text files."""
    app = await app_name(ops_test)
    unit = ops_test.model.applications[app].units[0]

    log_types = ["error", "general", "slowquery"]
    log_files = ["error.log", "general.log", "slowquery.log"]
    archive_directories = ["archive_error", "archive_general", "archive_slowquery"]

    logger.info("Removing the cron file and archive directories")
    await delete_file_or_directory_in_unit(ops_test, unit.name, "/etc/cron.d/flush_mysql_logs")

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

    assert len(ls_la_output) == 3, f"❌ files other than log files exist {ls_la_output}"
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

    assert (
        len(ls_la_output) == 6
    ), f"❌ unexpected files/directories in log directory: {ls_la_output}"
    directories = [line.split()[-1] for line in ls_la_output]
    assert sorted(directories) == sorted(
        log_files + archive_directories
    ), f"❌ unexpected files/directories in log directory: {ls_la_output}"

    logger.info("Ensuring log files were rotated")
    for log in log_types:
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
