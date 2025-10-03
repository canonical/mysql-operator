# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import tempfile

import jubilant
import jubilant_backports
import pytest
from jubilant_backports import Juju
from tenacity import (
    Retrying,
    stop_after_attempt,
    wait_fixed,
)

from constants import CHARMED_MYSQL_COMMON_DIRECTORY

from .high_availability_helpers_new import (
    get_app_leader,
    get_unit_process_id,
    wait_for_apps_status,
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
def test_log_rotation(juju: Juju) -> None:
    """Test the log rotation of text files."""
    log_types = ["error", "audit"]
    log_files = ["error.log", "audit.log"]
    archive_dirs = ["archive_error", "archive_audit"]

    mysql_app_leader = get_app_leader(juju, MYSQL_APP_NAME)
    mysql_logs_path = f"{CHARMED_MYSQL_COMMON_DIRECTORY}/var/log/mysql"

    logging.info("Removing the cron file")
    delete_unit_file(juju, mysql_app_leader, "/etc/cron.d/flush_mysql_logs")

    logging.info("Stopping any running logrotate jobs")
    stop_unit_flush_logs_job(juju, mysql_app_leader)

    for log_type in log_types:
        logging.info("Removing existing archive directories")
        delete_unit_file(juju, mysql_app_leader, f"{mysql_logs_path}/archive_{log_type}")
        logging.info("Writing some data to the text log files")
        write_unit_file(juju, mysql_app_leader, f"{mysql_logs_path}/{log_type}.log", "content\n")

    logging.info("Ensuring only log files exist")
    log_files_listed = list_unit_files(juju, mysql_app_leader, mysql_logs_path)
    log_dirs_listed = [line.split()[-1] for line in log_files_listed]

    assert len(log_files_listed) == len(log_files)
    assert sorted(log_dirs_listed) == sorted(log_files)

    logging.info("Executing logrotate")
    start_unit_flush_logs_job(juju, mysql_app_leader)

    logging.info("Ensuring log files and archive directories exist")
    log_files_listed = list_unit_files(juju, mysql_app_leader, mysql_logs_path)
    log_dirs_listed = [line.split()[-1] for line in log_files_listed]

    assert len(log_files_listed) == len(log_files + archive_dirs)
    assert sorted(log_dirs_listed) == sorted(log_files + archive_dirs)

    logging.info("Ensuring log files were rotated")
    for log_type in log_types:
        active_log_file_data = read_unit_file(
            juju, mysql_app_leader, f"{mysql_logs_path}/{log_type}.log"
        )
        assert "content" not in active_log_file_data

        archive_log_files_listed = list_unit_files(
            juju, mysql_app_leader, f"{mysql_logs_path}/archive_{log_type}"
        )
        assert len(archive_log_files_listed) == 1

        archive_log_file_name = archive_log_files_listed[0].split()[-1]
        archive_log_file_data = read_unit_file(
            juju, mysql_app_leader, f"{mysql_logs_path}/archive_{log_type}/{archive_log_file_name}"
        )
        assert "content" in archive_log_file_data


def delete_unit_file(juju: Juju, unit: str, path: str) -> bool:
    """Delete a path in the provided unit.

    Args:
        juju: The Juju instance
        unit: The unit on which to delete the file
        path: The path or file to delete
    """
    if path.strip() in ["/", "."]:
        return False

    try:
        juju.exec(f"sudo find {path} -maxdepth 1 -delete", unit=unit)
        return True
    except (jubilant.TaskError, jubilant_backports.TaskError):
        return False


def list_unit_files(juju: Juju, unit: str, path: str) -> list[str]:
    """Returns the list of files in the given path.

    Args:
        juju: The Juju instance
        unit: The unit in which to list the files
        path: The path at which to list the files
    """
    task = juju.exec(f"sudo ls -la {path}", unit=unit)
    task.raise_on_failure()

    output = task.stdout.split("\n")[1:]

    return [
        line.strip("\r")
        for line in output
        if len(line.strip()) > 0 and line.split()[-1] not in [".", ".."]
    ]


def read_unit_file(juju: Juju, unit: str, path: str) -> str:
    """Read contents from file in the provided unit.

    Args:
        juju: The Juju instance
        unit: The unit in which to read the file from
        path: The path from which to read the data from
    """
    temp_path = "/tmp/file"

    juju.exec(f"sudo cp {path} {temp_path}", unit=unit)
    juju.exec(f"sudo chown ubuntu:ubuntu {temp_path}", unit=unit)

    with tempfile.NamedTemporaryFile(mode="r+") as temp_file:
        juju.scp(
            f"{unit}:{temp_path}",
            f"{unit}:{temp_file.name}",
        )
        contents = temp_file.read()

    juju.exec(f"sudo rm {temp_path}", unit=unit)
    return contents


def write_unit_file(juju: Juju, unit: str, path: str, data: str) -> None:
    """Write content to the file in the provided unit.

    Args:
        juju: The Juju instance
        unit: The unit in which to write to file in
        path: The path at which to write the data into
        data: The data to write to the file.
    """
    temp_path = "/tmp/file"

    with tempfile.NamedTemporaryFile(mode="w") as temp_file:
        temp_file.write(data)
        temp_file.flush()

        juju.scp(
            f"{unit}:{temp_file.name}",
            f"{unit}:{temp_path}",
        )

    juju.exec(f"sudo mv {temp_path} {path}", unit=unit)
    juju.exec(f"sudo chown snap_daemon:root {path}", unit=unit)


def start_unit_flush_logs_job(juju: Juju, unit: str) -> None:
    """Start running the logrotate job."""
    juju.exec(
        command="sudo logrotate -f /etc/logrotate.d/flush_mysql_logs",
        unit=unit,
    )


def stop_unit_flush_logs_job(juju: Juju, unit: str) -> None:
    """Stop running any logrotate jobs that may have been triggered by cron."""
    juju.exec(
        command="sudo pkill --signal SIGTERM -f logrotate -f /etc/logrotate.d/flush_mysql_logs",
        unit=unit,
    )

    # Hold execution until process is stopped
    for attempt in Retrying(stop=stop_after_attempt(45), wait=wait_fixed(2)):
        with attempt:
            if get_unit_process_id(juju, unit, "logrotate") is not None:
                raise Exception("Failed to stop the flush_mysql_logs logrotate process")
