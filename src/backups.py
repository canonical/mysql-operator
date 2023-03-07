# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Library containing the implementation of backups."""

import datetime
import json
import logging
import pathlib
from typing import Dict, List, Tuple

from charms.data_platform_libs.v0.s3 import S3Requirer
from charms.mysql.v0.mysql import (
    MySQLDeleteTempBackupDirectoryError,
    MySQLExecuteBackupCommandsError,
    MySQLGetMemberStateError,
    MySQLOfflineModeAndHiddenInstanceExistsError,
    MySQLSetInstanceOfflineModeError,
    MySQLSetInstanceOptionError,
)
from ops.charm import ActionEvent, CharmBase
from ops.framework import Object
from ops.jujuversion import JujuVersion
from ops.model import BlockedStatus

from constants import S3_INTEGRATOR_RELATION_NAME
from s3_helpers import list_backups_in_s3_path, upload_content_to_s3

logger = logging.getLogger(__name__)

MYSQL_BACKUPS = "mysql-backups"


class MySQLBackups(Object):
    """Encapsulation of backups for MySQL."""

    def __init__(self, charm: CharmBase, s3_integrator: S3Requirer) -> None:
        super().__init__(charm, MYSQL_BACKUPS)

        self.charm = charm
        self.s3_integrator = s3_integrator

        self.framework.observe(self.charm.on.create_backup_action, self._on_create_backup)
        self.framework.observe(self.charm.on.list_backups_action, self._on_list_backups)

    # ------------------ Helpers ------------------

    def _retrieve_s3_parameters(self) -> Tuple[Dict, List[str]]:
        """Retrieve S3 parameters from the S3 integrator relation.

        Returns: tuple of (s3_parameters, missing_required_parameters)
        """
        s3_parameters = self.s3_integrator.get_s3_connection_info()

        required_parameters = [
            "bucket",
            "access-key",
            "secret-key",
        ]
        missing_required_parameters = [
            param for param in required_parameters if not s3_parameters.get(param)
        ]
        if missing_required_parameters:
            logger.warning(
                f"Missing required S3 parameters in relation with S3 integrator: {missing_required_parameters}"
            )
            return {}, missing_required_parameters

        # Add some sensible defaults (as expected by the code) for missing optional parameters
        s3_parameters.setdefault("endpoint", "https://s3.amazonaws.com")
        s3_parameters.setdefault("region")
        s3_parameters.setdefault("path", "")

        return s3_parameters, []

    def _upload_logs_to_s3(
        self: str,
        stdout: str,
        stderr: str,
        log_filename: str,
        s3_parameters: Dict,
    ) -> bool:
        """Upload logs to S3 at the specified location.

        Args:
            stdout: The stdout logs
            stderr: The stderr logs
            log_filename: The name of the object to upload in S3
            s3_parameters: A dictionary of S3 parameters to use to upload to S3

        Returns: bool indicating success
        """
        logs = f"""Stdout:
{stdout}

Stderr:
{stderr}"""
        logger.debug(f"Logs to upload to S3 at location {log_filename}:\n{logs}")

        logger.info(
            f"Uploading logs to S3 at bucket={s3_parameters['bucket']}, location={log_filename}"
        )
        return upload_content_to_s3(logs, log_filename, s3_parameters)

    # ------------------ List Backups ------------------

    def _on_list_backups(self, event: ActionEvent) -> None:
        """Handle the list backups action.

        List backups available to restore by this application.
        """
        if not self.charm.model.get_relation(S3_INTEGRATOR_RELATION_NAME):
            event.fail("Missing relation with S3 integrator charm")
            return

        try:
            logger.info("Retrieving s3 parameters from the s3-integrator relation")
            s3_parameters, missing_parameters = self._retrieve_s3_parameters()
            if missing_parameters:
                event.fail(f"Missing S3 parameters: {missing_parameters}")
                return

            logger.info("Listing backups in the specified s3 path")
            backup_ids = list_backups_in_s3_path(s3_parameters)
            event.set_results({"backup-ids": json.dumps(backup_ids)})
        except Exception:
            event.fail("Failed to retrieve backup ids from S3")

    # ------------------ Create Backup ------------------

    def _on_create_backup(self, event: ActionEvent) -> None:
        """Handle the create backup action."""
        logger.info("A backup has been requested on unit")

        if not self.charm.model.get_relation(S3_INTEGRATOR_RELATION_NAME):
            event.fail("Missing relation with S3 integrator charm")
            return

        datetime_backup_requested = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")

        # Retrieve and validate missing S3 parameters
        s3_parameters, missing_parameters = self._retrieve_s3_parameters()
        if missing_parameters:
            event.fail(f"Missing S3 parameters: {missing_parameters}")
            return

        backup_path = str(pathlib.Path(s3_parameters["path"]) / datetime_backup_requested)

        # Check if this unit can perform backup
        can_unit_perform_backup, validation_message = self._can_unit_perform_backup()
        if not can_unit_perform_backup:
            logger.warning(validation_message)
            event.fail(validation_message)
            return

        # Test uploading metadata to S3 to test credentials before backup
        juju_version = JujuVersion.from_environ()
        metadata = f"""Date Backup Requested: {datetime_backup_requested}
Model Name: {self.model.name}
Application Name: {self.model.app.name}
Unit Name: {self.charm.unit.name}
Juju Version: {str(juju_version)}
"""

        if not upload_content_to_s3(metadata, f"{backup_path}.metadata", s3_parameters):
            event.fail("Failed to upload metadata to provided S3")
            return

        # Run operations to prepare for the backup
        success, error_message = self._pre_backup()
        if not success:
            logger.warning(error_message)
            event.fail(error_message)
            return

        # Perform the backup
        success, error_message = self._backup(backup_path, s3_parameters)
        if not success:
            logger.warning(error_message)
            event.fail(error_message)

            success, error_message = self._post_backup()
            if not success:
                logger.error(error_message)
                self.charm.unit.status = BlockedStatus(
                    "Failed to create backup; instance in bad state"
                )

            return

        # Run operations to clean up after the backup
        success, error_message = self._post_backup()
        if not success:
            logger.error(error_message)
            self.charm.unit.status = BlockedStatus(
                "Failed to create backup; instance in bad state"
            )
            event.fail(error_message)
            return

        event.set_results(
            {
                "backup-id": datetime_backup_requested,
            }
        )

    def _can_unit_perform_backup(self) -> Tuple[bool, str]:
        """Validates whether this unit can perform a backup.

        Returns: tuple of (success, error_message)
        """
        logger.info("Checking if the unit is waiting to start or restart")
        if self.charm.unit_peer_data.get("member-state") == "waiting":
            return False, "Cluster or unit is waiting to start or restart"

        logger.info("Checking if backup already in progress")
        try:
            if self.charm._mysql.offline_mode_and_hidden_instance_exists():
                return False, "Backup already in progress on another unit"
        except MySQLOfflineModeAndHiddenInstanceExistsError:
            return False, "Failed to check if a backup is already in progress"

        logger.info("Checking state and role of unit")

        try:
            state, role = self.charm._mysql.get_member_state()
        except MySQLGetMemberStateError:
            return False, "Error obtaining member state"

        if role == "primary" and self.charm.app.planned_units() > 1:
            return False, "Unit cannot perform backups as it is the cluster primary"

        if state in ["recovering", "offline", "error"]:
            return False, f"Unit cannot perform backups as its state is {state}"

        return True, None

    def _pre_backup(self) -> Tuple[bool, str]:
        """Runs operations required before performing a backup.

        Returns: tuple of (success, error_message)
        """
        # Do not set instance offline_mode and do not hide instance from mysqlrouter
        # if there is only one instance in the cluster
        if self.charm.app.planned_units() == 1:
            return True, None

        try:
            logger.info("Setting unit option tag:_hidden")
            self.charm._mysql.set_instance_option("tag:_hidden", "true")
        except MySQLSetInstanceOptionError:
            return False, "Error setting instance option tag:_hidden"

        try:
            logger.info("Setting unit as offline before performing backup")
            self.charm._mysql.set_instance_offline_mode(True)
        except MySQLSetInstanceOfflineModeError:
            self.charm._mysql.set_instance_option("tag:_hidden", "false")
            return False, "Error setting instance as offline before performing backup"

        return True, None

    def _backup(self, backup_path: str, s3_parameters: Dict) -> Tuple[bool, str]:
        """Runs the backup operations.

        Args:
            backup_path: The location to upload the backup to
            s3_parameters: Dictionary containing S3 parameters to upload the backup with

        Returns: tuple of (success, error_message)
        """
        try:
            logger.info("Running the xtrabackup commands")
            stdout = self.charm._mysql.execute_backup_commands(
                s3_parameters["bucket"],
                backup_path,
                s3_parameters["access-key"],
                s3_parameters["secret-key"],
                s3_parameters["endpoint"],
            )
        except MySQLExecuteBackupCommandsError as e:
            self._upload_logs_to_s3(
                "",
                e.message,
                f"{backup_path}.backup.log",
                s3_parameters,
            )
            return False, "Error backing up the database"

        if not self._upload_logs_to_s3(
            stdout,
            "",
            f"{backup_path}.backup.log",
            s3_parameters,
        ):
            return False, "Error uploading logs to S3"

        return True, None

    def _post_backup(self) -> Tuple[bool, str]:
        """Runs operations required after performing a backup.

        Returns: tuple of (success, error_message)
        """
        try:
            logger.info("Deleting temp backup directory")
            self.charm._mysql.delete_temp_backup_directory()
        except MySQLDeleteTempBackupDirectoryError:
            return False, "Error deleting temp backup directory"

        try:
            logger.info("Unsetting unit as offline after performing backup")
            self.charm._mysql.set_instance_offline_mode(False)
        except MySQLSetInstanceOfflineModeError:
            return False, "Error unsetting instance as offline before performing backup"

        try:
            logger.info("Setting unit option tag:_hidden as false")
            self.charm._mysql.set_instance_option("tag:_hidden", "false")
        except MySQLSetInstanceOptionError:
            return False, "Error setting instance option tag:_hidden"

        return True, None
