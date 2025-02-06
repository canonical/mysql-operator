# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.


import logging
from pathlib import Path

import pytest
import yaml
from pytest_operator.plugin import OpsTest

from constants import CHARMED_MYSQL_COMMON_DIRECTORY

from ..helpers import (
    delete_file_or_directory_in_unit,
    ls_la_in_unit,
    read_contents_from_file_in_unit,
    stop_running_flush_mysql_cronjobs,
    write_content_to_file_in_unit,
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
async def test_log_rotation(ops_test: OpsTest, highly_available_cluster) -> None:
    """Test the log rotation of text files."""
    app = get_application_name(ops_test, "mysql")
    unit = ops_test.model.applications[app].units[0]

    log_types = ["error", "audit"]
    log_files = ["error.log", "audit.log"]
    archive_directories = [
        "archive_error",
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
