# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import MagicMock, PropertyMock, patch

from charms.mysql.v0.mysql import (
    MySQLConfigureInstanceError,
    MySQLCreateClusterError,
    MySQLDeleteTempBackupDirectoryError,
    MySQLDeleteTempRestoreDirectoryError,
    MySQLEmptyDataDirectoryError,
    MySQLExecuteBackupCommandsError,
    MySQLGetMemberStateError,
    MySQLInitializeJujuOperationsTableError,
    MySQLOfflineModeAndHiddenInstanceExistsError,
    MySQLPrepareBackupForRestoreError,
    MySQLRestoreBackupError,
    MySQLRetrieveBackupWithXBCloudError,
    MySQLServiceNotRunningError,
    MySQLSetInstanceOfflineModeError,
    MySQLSetInstanceOptionError,
    MySQLStartMySQLDError,
    MySQLStopMySQLDError,
)
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus
from ops.testing import Harness

from charm import MySQLOperatorCharm
from constants import S3_INTEGRATOR_RELATION_NAME

from .helpers import patch_network_get


class TestMySQLBackups(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(MySQLOperatorCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()
        self.peer_relation_id = self.harness.add_relation("database-peers", "database-peers")
        self.harness.set_leader(True)
        self.harness.charm.on.config_changed.emit()
        self.charm = self.harness.charm
        self.s3_integrator_id = self.harness.add_relation(
            S3_INTEGRATOR_RELATION_NAME, "s3-integrator"
        )
        self.mysql_backups = self.charm.backups

    @patch("charms.data_platform_libs.v0.s3.S3Requirer.get_s3_connection_info")
    def test_retrieve_s3_parameters(self, _get_s3_connection_info):
        """Test _retrieve_s3_parameters()."""
        return_value = {
            "bucket": "test_bucket",
            "access-key": "test-access-key",
            "secret-key": "test-secret-key",
        }
        _get_s3_connection_info.return_value = return_value

        s3_parameters, missing_required_parameters = self.mysql_backups._retrieve_s3_parameters()
        self.assertEqual(
            s3_parameters,
            {"endpoint": "https://s3.amazonaws.com", "region": None, "path": "", **return_value},
        )
        self.assertEqual(missing_required_parameters, [])

        _get_s3_connection_info.return_value = {}
        s3_parameters, missing_required_parameters = self.mysql_backups._retrieve_s3_parameters()
        self.assertEqual(s3_parameters, {})
        self.assertEqual(
            sorted(missing_required_parameters), sorted(["bucket", "access-key", "secret-key"])
        )

    @patch("charms.mysql.v0.backups.upload_content_to_s3", return_value=True)
    def test_upload_logs_to_s3(self, _upload_content_to_s3):
        """Test _upload_logs_to_s3()."""
        expected_logs = """Stdout:
test stdout

Stderr:
test stderr"""
        s3_params = {"bucket": "test-bucket"}

        self.mysql_backups._upload_logs_to_s3("test stdout", "test stderr", "/filename", s3_params)
        _upload_content_to_s3.assert_called_once_with(expected_logs, "/filename", s3_params)

    @patch(
        "charms.mysql.v0.backups.MySQLBackups._retrieve_s3_parameters",
        return_value=({"bucket": "test-bucket"}, []),
    )
    @patch("charms.mysql.v0.backups.list_backups_in_s3_path", return_value=[("backup1", "finished"), ("backup2", "failed")])
    def test_on_list_backups(self, _list_backups_in_s3_path, _retrieve_s3_parameters):
        """Test _on_list_backups()."""
        event = MagicMock()

        self.mysql_backups._on_list_backups(event)

        _retrieve_s3_parameters.assert_called_once()
        _list_backups_in_s3_path.assert_called_once_with({"bucket": "test-bucket"})

        expected_backups_output = [
            "backup-id             | backup-type  | backup-status",
            "----------------------------------------------------",
            "backup1               | physical     | finished",
            "backup2               | physical     | failed",
        ]

        event.set_results.assert_called_once_with({"backups": "\n".join(expected_backups_output)})
        event.fail.assert_not_called()

    @patch("charms.mysql.v0.backups.MySQLBackups._retrieve_s3_parameters")
    @patch("charms.mysql.v0.backups.list_backups_in_s3_path")
    def test_on_list_backups_failure(self, _list_backups_in_s3_path, _retrieve_s3_parameters):
        """Test failures in _on_list_backups()."""
        # test an exception being thrown
        event = MagicMock()
        _list_backups_in_s3_path.side_effect = Exception("failure")

        self.mysql_backups._on_list_backups(event)

        event.set_results.assert_not_called()
        event.fail.assert_called_once_with("Failed to retrieve backup ids from S3")

        # test missing parameters
        event = MagicMock()
        _retrieve_s3_parameters.return_value = {}, ["bucket"]

        self.mysql_backups._on_list_backups(event)

        event.set_results.assert_not_called()
        event.fail.assert_called_once_with("Missing S3 parameters: ['bucket']")

        # test missing s3_integrator relation
        event = MagicMock()
        self.harness.remove_relation(self.s3_integrator_id)

        self.mysql_backups._on_list_backups(event)

        event.set_results.assert_not_called()
        event.fail.assert_called_once_with("Missing relation with S3 integrator charm")

    @patch_network_get(private_address="1.1.1.1")
    @patch("datetime.datetime")
    @patch(
        "charms.mysql.v0.backups.MySQLBackups._retrieve_s3_parameters",
        return_value=({"path": "/path"}, []),
    )
    @patch(
        "charms.mysql.v0.backups.MySQLBackups._can_unit_perform_backup", return_value=(True, None)
    )
    @patch("ops.jujuversion.JujuVersion.from_environ", return_value="test-juju-version")
    @patch("charms.mysql.v0.backups.upload_content_to_s3")
    @patch("charms.mysql.v0.backups.MySQLBackups._pre_backup", return_value=(True, None))
    @patch("charms.mysql.v0.backups.MySQLBackups._backup", return_value=(True, None))
    @patch("charms.mysql.v0.backups.MySQLBackups._post_backup", return_value=(True, None))
    @patch("mysql_vm_helpers.MySQL.is_mysqld_running", return_value=True)
    def test_on_create_backup(
        self,
        _is_mysqld_running,
        _post_backup,
        _backup,
        _pre_backup,
        _upload_content_to_s3,
        _from_environ,
        _can_unit_perform_backup,
        _retrieve_s3_parameters,
        _datetime,
    ):
        """Test _on_create_backup()."""
        _datetime.now.return_value.strftime.return_value = "2023-03-07%13:43:15Z"

        expected_metadata = f"""Date Backup Requested: 2023-03-07%13:43:15Z
Model Name: {self.charm.model.name}
Application Name: {self.charm.model.app.name}
Unit Name: {self.charm.unit.name}
Juju Version: test-juju-version
"""
        expected_backup_path = "/path/2023-03-07%13:43:15Z"
        expected_s3_params = {"path": "/path"}

        event = MagicMock()

        self.mysql_backups._on_create_backup(event)

        _retrieve_s3_parameters.assert_called_once()
        _can_unit_perform_backup.assert_called_once()
        _from_environ.assert_called_once()
        _upload_content_to_s3.assert_called_once_with(
            expected_metadata, f"{expected_backup_path}.metadata", expected_s3_params
        )
        _pre_backup.assert_called_once()
        _backup.assert_called_once_with(expected_backup_path, expected_s3_params)
        _post_backup.assert_called_once()

        event.set_results.assert_called_once_with({"backup-id": "2023-03-07%13:43:15Z"})
        event.fail.assert_not_called()

    @patch_network_get(private_address="1.1.1.1")
    @patch("datetime.datetime")
    @patch(
        "charms.mysql.v0.backups.MySQLBackups._retrieve_s3_parameters",
        return_value=({"path": "/path"}, []),
    )
    @patch(
        "charms.mysql.v0.backups.MySQLBackups._can_unit_perform_backup", return_value=(True, None)
    )
    @patch("ops.jujuversion.JujuVersion.from_environ", return_value="test-juju-version")
    @patch("charms.mysql.v0.backups.upload_content_to_s3")
    @patch("charms.mysql.v0.backups.MySQLBackups._pre_backup", return_value=(True, None))
    @patch("charms.mysql.v0.backups.MySQLBackups._backup", return_value=(True, None))
    @patch("charms.mysql.v0.backups.MySQLBackups._post_backup", return_value=(True, None))
    @patch("mysql_vm_helpers.MySQL.is_mysqld_running", return_value=True)
    def test_on_create_backup_failure(
        self,
        _is_mysqld_running,
        _post_backup,
        _backup,
        _pre_backup,
        _upload_content_to_s3,
        _from_environ,
        _can_unit_perform_backup,
        _retrieve_s3_parameters,
        _datetime,
    ):
        """Test failure of _on_create_backup()."""
        _datetime.now.return_value.strftime.return_value = "2023-03-07%13:43:15Z"

        # test failure with _post_backup
        _post_backup.return_value = False, "post backup failure"
        event = MagicMock()
        self.charm.unit.status = ActiveStatus()

        self.mysql_backups._on_create_backup(event)
        event.set_results.assert_not_called()
        event.fail.assert_called_once_with("post backup failure")
        self.assertTrue(isinstance(self.harness.model.unit.status, BlockedStatus))

        # test failure with _backup
        _backup.return_value = False, "backup failure"
        event = MagicMock()
        self.charm.unit.status = ActiveStatus()

        self.mysql_backups._on_create_backup(event)
        event.set_results.assert_not_called()
        event.fail.assert_called_once_with("backup failure")
        self.assertTrue(isinstance(self.harness.model.unit.status, BlockedStatus))

        # test failure with _prebackup
        _pre_backup.return_value = False, "pre backup failure"
        event = MagicMock()
        self.charm.unit.status = ActiveStatus()

        self.mysql_backups._on_create_backup(event)
        event.set_results.assert_not_called()
        event.fail.assert_called_once_with("pre backup failure")
        self.assertTrue(isinstance(self.harness.model.unit.status, ActiveStatus))

        # test failure with upload_content_to_s3
        _upload_content_to_s3.return_value = False
        event = MagicMock()
        self.charm.unit.status = ActiveStatus()

        self.mysql_backups._on_create_backup(event)
        event.set_results.assert_not_called()
        event.fail.assert_called_once_with("Failed to upload metadata to provided S3")
        self.assertTrue(isinstance(self.harness.model.unit.status, ActiveStatus))

        # test failure with _can_unit_perform_backup
        _can_unit_perform_backup.return_value = False, "can unit perform backup failure"
        event = MagicMock()
        self.charm.unit.status = ActiveStatus()

        self.mysql_backups._on_create_backup(event)
        event.set_results.assert_not_called()
        event.fail.assert_called_once_with("can unit perform backup failure")
        self.assertTrue(isinstance(self.harness.model.unit.status, ActiveStatus))

        # test failure with _retrieve_s3_parameters
        _retrieve_s3_parameters.return_value = False, ["bucket"]
        event = MagicMock()
        self.charm.unit.status = ActiveStatus()

        self.mysql_backups._on_create_backup(event)
        event.set_results.assert_not_called()
        event.fail.assert_called_once_with("Missing S3 parameters: ['bucket']")
        self.assertTrue(isinstance(self.harness.model.unit.status, ActiveStatus))

        # test mysqld not running
        _is_mysqld_running.return_value = False
        event = MagicMock()
        self.charm.unit.status = ActiveStatus()

        self.mysql_backups._on_create_backup(event)
        event.set_results.assert_not_called()
        event.fail.assert_called_once_with("Process mysqld not running")
        self.assertTrue(isinstance(self.harness.model.unit.status, ActiveStatus))

        # test missing s3 integrator relation
        self.harness.remove_relation(self.s3_integrator_id)
        event = MagicMock()
        self.charm.unit.status = ActiveStatus()

        self.mysql_backups._on_create_backup(event)
        event.set_results.assert_not_called()
        event.fail.assert_called_once_with("Missing relation with S3 integrator charm")
        self.assertTrue(isinstance(self.harness.model.unit.status, ActiveStatus))

    @patch_network_get(private_address="1.1.1.1")
    @patch("mysql_vm_helpers.MySQL.offline_mode_and_hidden_instance_exists", return_value=False)
    @patch("mysql_vm_helpers.MySQL.get_member_state", return_value=("online", "replica"))
    def test_can_unit_perform_backup(
        self,
        _get_member_state,
        _offline_mode_and_hidden_instance_exists,
    ):
        """Test _can_unit_perform_backup()."""
        self.harness.set_leader(True)
        self.charm.on.config_changed.emit()

        success, error_message = self.mysql_backups._can_unit_perform_backup()
        self.assertTrue(success)
        self.assertIsNone(error_message)

    @patch_network_get(private_address="1.1.1.1")
    @patch("mysql_vm_helpers.MySQL.offline_mode_and_hidden_instance_exists", return_value=False)
    @patch("mysql_vm_helpers.MySQL.get_member_state")
    def test_can_unit_perform_backup_failure(
        self,
        _get_member_state,
        _offline_mode_and_hidden_instance_exists,
    ):
        """Test failure of _can_unit_perform_backup()."""
        # test non-online state
        _get_member_state.return_value = ("recovering", "replica")

        success, error_message = self.mysql_backups._can_unit_perform_backup()
        self.assertFalse(success)
        self.assertEqual(error_message, "Unit cannot perform backups as its state is recovering")

        # test more than one unit and backup on primary
        _get_member_state.return_value = ("online", "primary")

        self.harness.add_relation_unit(self.peer_relation_id, "mysql/1")

        success, error_message = self.mysql_backups._can_unit_perform_backup()
        self.assertFalse(success)
        self.assertEqual(error_message, "Unit cannot perform backups as it is the cluster primary")

        self.harness.remove_relation_unit(self.peer_relation_id, "mysql/1")

        # test error getting member state
        _get_member_state.side_effect = MySQLGetMemberStateError

        success, error_message = self.mysql_backups._can_unit_perform_backup()
        self.assertFalse(success)
        self.assertEqual(error_message, "Error obtaining member state")

        # test error checking if offline mode and hidden instance exists
        _offline_mode_and_hidden_instance_exists.side_effect = (
            MySQLOfflineModeAndHiddenInstanceExistsError
        )

        success, error_message = self.mysql_backups._can_unit_perform_backup()
        self.assertFalse(success)
        self.assertEqual(error_message, "Failed to check if a backup is already in progress")

        # test member-state = waiting
        self.charm.unit_peer_data["member-state"] = "waiting"

        success, error_message = self.mysql_backups._can_unit_perform_backup()
        self.assertFalse(success)
        self.assertEqual(error_message, "Unit is waiting to start or restart")

    @patch_network_get(private_address="1.1.1.1")
    @patch("mysql_vm_helpers.MySQL.set_instance_option")
    @patch("mysql_vm_helpers.MySQL.set_instance_offline_mode")
    def test_pre_backup(
        self,
        _set_instance_offline_mode,
        _set_instance_option,
    ):
        """Test _pre_backup()."""
        # test with 2 planned units
        self.harness.add_relation_unit(self.peer_relation_id, "mysql/1")

        success, error_message = self.mysql_backups._pre_backup()
        self.assertTrue(success)
        self.assertIsNone(error_message)

        self.harness.remove_relation_unit(self.peer_relation_id, "mysql/1")

        # test with 1 planned units
        success, error_message = self.mysql_backups._pre_backup()
        self.assertTrue(success)
        self.assertIsNone(error_message)

    @patch_network_get(private_address="1.1.1.1")
    @patch("mysql_vm_helpers.MySQL.set_instance_option")
    @patch("mysql_vm_helpers.MySQL.set_instance_offline_mode")
    def test_pre_backup_failure(
        self,
        _set_instance_offline_mode,
        _set_instance_option,
    ):
        """Test failure of _pre_backup()."""
        self.harness.add_relation_unit(self.peer_relation_id, "mysql/1")

        # test error with set_instance_offline_mode
        _set_instance_offline_mode.side_effect = MySQLSetInstanceOfflineModeError

        success, error_message = self.mysql_backups._pre_backup()
        self.assertFalse(success)
        self.assertEqual(
            error_message, "Error setting instance as offline before performing backup"
        )
        self.assertEqual(_set_instance_option.call_count, 2)

        # test error with set_instance_option
        _set_instance_option.side_effect = MySQLSetInstanceOptionError

        success, error_message = self.mysql_backups._pre_backup()
        self.assertFalse(success)
        self.assertEqual(error_message, "Error setting instance option tag:_hidden")

    @patch_network_get(private_address="1.1.1.1")
    @patch("mysql_vm_helpers.MySQL.execute_backup_commands", return_value="stdout")
    @patch("charms.mysql.v0.backups.MySQLBackups._upload_logs_to_s3")
    def test_backup(
        self,
        _upload_logs_to_s3,
        _execute_backup_commands,
    ):
        """Test _backup()."""
        s3_params = {
            "bucket": "test-bucket",
            "access-key": "test-access-key",
            "secret-key": "test-secret-key",
            "endpoint": "https://s3.amazonaws.com",
        }

        success, error_message = self.mysql_backups._backup("/path", s3_params)
        self.assertTrue(success)
        self.assertIsNone(error_message)
        _upload_logs_to_s3.assert_called_once_with("stdout", "", "/path.backup.log", s3_params)

    @patch_network_get(private_address="1.1.1.1")
    @patch("mysql_vm_helpers.MySQL.execute_backup_commands", return_value="stdout")
    @patch("charms.mysql.v0.backups.MySQLBackups._upload_logs_to_s3")
    def test_backup_failure(
        self,
        _upload_logs_to_s3,
        _execute_backup_commands,
    ):
        """Test failure of _backup()."""
        s3_params = {
            "bucket": "test-bucket",
            "access-key": "test-access-key",
            "secret-key": "test-secret-key",
            "endpoint": "https://s3.amazonaws.com",
        }

        # test failure uploading logs to s3
        _upload_logs_to_s3.return_value = False

        success, error_message = self.mysql_backups._backup("/path", s3_params)
        self.assertFalse(success)
        self.assertEqual(error_message, "Error uploading logs to S3")

        # test failure in execute_backup_commands
        _upload_logs_to_s3.reset_mock()
        _execute_backup_commands.side_effect = MySQLExecuteBackupCommandsError("failure backup")

        success, error_message = self.mysql_backups._backup("/path", s3_params)
        self.assertFalse(success)
        self.assertEqual(error_message, "Error backing up the database")
        _upload_logs_to_s3.assert_called_once_with(
            "", "failure backup", "/path.backup.log", s3_params
        )

    @patch_network_get(private_address="1.1.1.1")
    @patch("mysql_vm_helpers.MySQL.delete_temp_backup_directory")
    @patch("mysql_vm_helpers.MySQL.set_instance_offline_mode")
    @patch("mysql_vm_helpers.MySQL.set_instance_option")
    def test_post_backup(
        self,
        _set_instance_option,
        _set_instance_offline_mode,
        _delete_temp_backup_directory,
    ):
        """Test _post_backup."""
        success, error_message = self.mysql_backups._post_backup()
        self.assertTrue(success)
        self.assertIsNone(error_message)

    @patch_network_get(private_address="1.1.1.1")
    @patch("mysql_vm_helpers.MySQL.delete_temp_backup_directory")
    @patch("mysql_vm_helpers.MySQL.set_instance_offline_mode")
    @patch("mysql_vm_helpers.MySQL.set_instance_option")
    def test_post_backup_failure(
        self,
        _set_instance_option,
        _set_instance_offline_mode,
        _delete_temp_backup_directory,
    ):
        """Test failure of _post_backup."""
        # test failure in set_instance_option
        _set_instance_option.side_effect = MySQLSetInstanceOptionError

        success, error_message = self.mysql_backups._post_backup()
        self.assertFalse(success)
        self.assertEqual(error_message, "Error setting instance option tag:_hidden")

        # test failure in set_instance_offline_mode
        _set_instance_offline_mode.side_effect = MySQLSetInstanceOfflineModeError

        success, error_message = self.mysql_backups._post_backup()
        self.assertFalse(success)
        self.assertEqual(
            error_message, "Error unsetting instance as offline before performing backup"
        )

        # test failure in delete_temp_backup_directory
        _delete_temp_backup_directory.side_effect = MySQLDeleteTempBackupDirectoryError

        success, error_message = self.mysql_backups._post_backup()
        self.assertFalse(success)
        self.assertEqual(error_message, "Error deleting temp backup directory")

    @patch_network_get(private_address="1.1.1.1")
    @patch("mysql_vm_helpers.MySQL.is_server_connectable", return_value=True)
    @patch("charm.MySQLOperatorCharm.is_unit_busy", return_value=False)
    def test_pre_restore_checks(
        self,
        _is_unit_busy,
        _is_server_connectable,
    ):
        """Test _pre_restore_checks()."""
        event = MagicMock()

        self.assertTrue(self.mysql_backups._pre_restore_checks(event))

    @patch_network_get(private_address="1.1.1.1")
    @patch("mysql_vm_helpers.MySQL.is_server_connectable", return_value=True)
    @patch("charm.MySQLOperatorCharm.is_unit_busy", return_value=False)
    def test_pre_restore_checks_failure(
        self,
        _is_unit_busy,
        _is_server_connectable,
    ):
        """Test failure of _pre_restore_checks()."""
        # test more than one planned units
        self.harness.add_relation_unit(self.peer_relation_id, "mysql/1")
        event = MagicMock()

        self.assertFalse(self.mysql_backups._pre_restore_checks(event))

        self.harness.remove_relation_unit(self.peer_relation_id, "mysql/1")

        # test unit in blocked state
        _is_unit_busy.return_value = True
        event = MagicMock()

        self.assertFalse(self.mysql_backups._pre_restore_checks(event))

        # test mysqld not running
        _is_server_connectable.return_value = False
        event = MagicMock()

        self.assertFalse(self.mysql_backups._pre_restore_checks(event))

        # test missing backup-id
        event = MagicMock()
        params_mock = {}
        with patch.dict(params_mock, {}):
            type(event).params = PropertyMock(return_value=params_mock)

            self.assertFalse(self.mysql_backups._pre_restore_checks(event))

        # test missing s3-integrator relation
        self.harness.remove_relation(self.s3_integrator_id)
        event = MagicMock()

        self.assertFalse(self.mysql_backups._pre_restore_checks(event))

    @patch_network_get(private_address="1.1.1.1")
    @patch("charms.mysql.v0.backups.MySQLBackups._pre_restore_checks", return_value=True)
    @patch(
        "charms.mysql.v0.backups.MySQLBackups._retrieve_s3_parameters",
        return_value=({"path": "/path"}, []),
    )
    @patch("charms.mysql.v0.backups.fetch_and_check_existence_of_s3_path", return_value=True)
    @patch("charms.mysql.v0.backups.MySQLBackups._pre_restore", return_value=(True, None))
    @patch("charms.mysql.v0.backups.MySQLBackups._restore", return_value=(True, True, None))
    @patch("charms.mysql.v0.backups.MySQLBackups._post_restore", return_value=(True, None))
    def test_on_restore(
        self,
        _post_restore,
        _restore,
        _pre_restore,
        _fetch_and_check_existence_of_s3_path,
        _retrieve_s3_parameters,
        _pre_restore_checks,
    ):
        """Test _on_restore()."""
        event = MagicMock()
        params_mock = {}

        with patch.dict(params_mock, {"backup-id": "test-backup-id"}):
            type(event).params = PropertyMock(return_value=params_mock)

            self.mysql_backups._on_restore(event)

        expected_s3_parameters = {"path": "/path"}

        _pre_restore_checks.assert_called_once()
        _retrieve_s3_parameters.assert_called_once()
        _fetch_and_check_existence_of_s3_path.assert_called_once_with(
            expected_s3_parameters, "/path/test-backup-id.md5"
        )
        _pre_restore.assert_called_once()
        _restore.assert_called_once_with("test-backup-id", expected_s3_parameters)
        _post_restore.assert_called_once()

        self.assertEqual(event.set_results.call_count, 1)
        self.assertEqual(event.fail.call_count, 0)

    @patch_network_get(private_address="1.1.1.1")
    @patch("charms.mysql.v0.backups.MySQLBackups._pre_restore_checks", return_value=True)
    @patch(
        "charms.mysql.v0.backups.MySQLBackups._retrieve_s3_parameters",
        return_value=({"path": "/path"}, []),
    )
    @patch("charms.mysql.v0.backups.fetch_and_check_existence_of_s3_path", return_value=True)
    @patch("charms.mysql.v0.backups.MySQLBackups._pre_restore", return_value=(True, None))
    @patch("charms.mysql.v0.backups.MySQLBackups._restore", return_value=(True, True, None))
    @patch("charms.mysql.v0.backups.MySQLBackups._clean_data_dir_and_start_mysqld")
    @patch("charms.mysql.v0.backups.MySQLBackups._post_restore", return_value=(True, None))
    def test_on_restore_failure(
        self,
        _post_restore,
        _clean_data_dir_and_start_mysqld,
        _restore,
        _pre_restore,
        _fetch_and_check_existence_of_s3_path,
        _retrieve_s3_parameters,
        _pre_restore_checks,
    ):
        """Test failure of _on_restore()."""
        # test failure of _post_restore()
        _post_restore.return_value = (False, "post restore error")

        event = MagicMock()
        params_mock = {}
        with patch.dict(params_mock, {"backup-id": "test-backup-id"}):
            type(event).params = PropertyMock(return_value=params_mock)

            self.mysql_backups._on_restore(event)

        event.set_results.assert_not_called()
        event.fail.assert_called_once_with("post restore error")

        # test failure of recoverable _restore()
        _restore.return_value = (False, True, "restore error")
        self.charm.unit.status = ActiveStatus()

        event = MagicMock()
        params_mock = {}
        with patch.dict(params_mock, {"backup-id": "test-backup-id"}):
            type(event).params = PropertyMock(return_value=params_mock)

            self.mysql_backups._on_restore(event)

        event.set_results.assert_not_called()
        event.fail.assert_called_once_with("restore error")
        _clean_data_dir_and_start_mysqld.assert_called_once()
        self.assertTrue(isinstance(self.charm.unit.status, ActiveStatus))

        _clean_data_dir_and_start_mysqld.reset_mock()

        # test failure of unrecoverable _restore()
        _restore.return_value = (False, False, "restore error")
        self.charm.unit.status = ActiveStatus()

        event = MagicMock()
        params_mock = {}
        with patch.dict(params_mock, {"backup-id": "test-backup-id"}):
            type(event).params = PropertyMock(return_value=params_mock)

            self.mysql_backups._on_restore(event)

        event.set_results.assert_not_called()
        event.fail.assert_called_once_with("restore error")
        _clean_data_dir_and_start_mysqld.assert_not_called()
        self.assertTrue(isinstance(self.charm.unit.status, BlockedStatus))

        # test failure of _pre_restore()
        _pre_restore.return_value = (False, "pre restore error")
        event = MagicMock()
        params_mock = {}
        with patch.dict(params_mock, {"backup-id": "test-backup-id"}):
            type(event).params = PropertyMock(return_value=params_mock)

            self.mysql_backups._on_restore(event)

        event.set_results.assert_not_called()
        event.fail.assert_called_once_with("pre restore error")

        # test failure of fetch_and_check_existence_of_s3_path()
        _fetch_and_check_existence_of_s3_path.return_value = False

        event = MagicMock()
        params_mock = {}
        with patch.dict(params_mock, {"backup-id": "test-backup-id"}):
            type(event).params = PropertyMock(return_value=params_mock)

            self.mysql_backups._on_restore(event)

        event.set_results.assert_not_called()
        event.fail.assert_called_once_with("Invalid backup-id: test-backup-id")

        # test failure of _retrieve_s3_parameters()
        _retrieve_s3_parameters.return_value = ({}, ["bucket"])

        event = MagicMock()
        params_mock = {}
        with patch.dict(params_mock, {"backup-id": "test-backup-id"}):
            type(event).params = PropertyMock(return_value=params_mock)

            self.mysql_backups._on_restore(event)

        event.set_results.assert_not_called()
        event.fail.assert_called_once_with("Missing S3 parameters: ['bucket']")

        # test failure of _pre_restore_checks
        _pre_restore_checks.return_value = False
        event = MagicMock()

        self.mysql_backups._on_restore(event)

        event.set_results.assert_not_called()
        event.fail.assert_not_called()

    @patch_network_get(private_address="1.1.1.1")
    @patch("mysql_vm_helpers.MySQL.stop_mysqld")
    def test_pre_restore(self, _stop_mysqld):
        """Test _pre_restore()."""
        success, error = self.mysql_backups._pre_restore()

        self.assertTrue(success)
        self.assertIsNone(error)

    @patch_network_get(private_address="1.1.1.1")
    @patch("mysql_vm_helpers.MySQL.stop_mysqld")
    def test_pre_restore_failure(self, _stop_mysqld):
        """Test failure of _pre_restore()."""
        _stop_mysqld.side_effect = MySQLStopMySQLDError()

        success, error = self.mysql_backups._pre_restore()

        self.assertFalse(success)
        self.assertEqual(error, "Failed to stop mysqld")

    @patch_network_get(private_address="1.1.1.1")
    @patch(
        "mysql_vm_helpers.MySQL.retrieve_backup_with_xbcloud",
        return_value=("", "", "test/backup/location"),
    )
    @patch("mysql_vm_helpers.MySQL.prepare_backup_for_restore", return_value=("", ""))
    @patch("mysql_vm_helpers.MySQL.empty_data_files")
    @patch("mysql_vm_helpers.MySQL.restore_backup", return_value=("", ""))
    def test_restore(
        self,
        _restore_backup,
        _empty_data_files,
        _prepare_backup_for_restore,
        _retrieve_backup_with_xbcloud,
    ):
        """Test _restore()."""
        s3_parameters = {
            "bucket": "test-bucket",
            "path": "test/path",
            "access-key": "test-access-key",
            "secret-key": "test-secret-key",
            "endpoint": "test-endpoint",
        }
        success, recoverable, error = self.mysql_backups._restore("test-backup-id", s3_parameters)

        self.assertTrue(success)
        self.assertTrue(recoverable)
        self.assertIsNone(error)

    @patch_network_get(private_address="1.1.1.1")
    @patch(
        "mysql_vm_helpers.MySQL.retrieve_backup_with_xbcloud",
        return_value=("", "", "test/backup/location"),
    )
    @patch("mysql_vm_helpers.MySQL.prepare_backup_for_restore", return_value=("", ""))
    @patch("mysql_vm_helpers.MySQL.empty_data_files")
    @patch("mysql_vm_helpers.MySQL.restore_backup", return_value=("", ""))
    def test_restore_failure(
        self,
        _restore_backup,
        _empty_data_files,
        _prepare_backup_for_restore,
        _retrieve_backup_with_xbcloud,
    ):
        """Test failure of _restore()."""
        s3_parameters = {
            "bucket": "test-bucket",
            "path": "test/path",
            "access-key": "test-access-key",
            "secret-key": "test-secret-key",
            "endpoint": "test-endpoint",
        }

        # test failure of restore_backup()
        _restore_backup.side_effect = MySQLRestoreBackupError()
        success, recoverable, error = self.mysql_backups._restore("test-backup-id", s3_parameters)

        self.assertFalse(success)
        self.assertFalse(recoverable)
        self.assertEqual(error, "Failed to restore backup test-backup-id")

        # test failure of empty_data_files()
        _empty_data_files.side_effect = MySQLEmptyDataDirectoryError()
        success, recoverable, error = self.mysql_backups._restore("test-backup-id", s3_parameters)

        self.assertFalse(success)
        self.assertFalse(recoverable)
        self.assertEqual(error, "Failed to empty the data directory")

        # test failure of prepare_backup_for_restore()
        _prepare_backup_for_restore.side_effect = MySQLPrepareBackupForRestoreError()
        success, recoverable, error = self.mysql_backups._restore("test-backup-id", s3_parameters)

        self.assertFalse(success)
        self.assertTrue(recoverable)
        self.assertEqual(error, "Failed to prepare backup test-backup-id")

        # test failure of retrieve_backup_with_xbcloud()
        _retrieve_backup_with_xbcloud.side_effect = MySQLRetrieveBackupWithXBCloudError()
        success, recoverable, error = self.mysql_backups._restore("test-backup-id", s3_parameters)

        self.assertFalse(success)
        self.assertTrue(recoverable)
        self.assertEqual(error, "Failed to retrieve backup test-backup-id")

    @patch_network_get(private_address="1.1.1.1")
    @patch("mysql_vm_helpers.MySQL.start_mysqld")
    @patch("mysql_vm_helpers.MySQL.delete_temp_restore_directory")
    @patch("mysql_vm_helpers.MySQL.delete_temp_backup_directory")
    def test_clean_data_dir_and_start_mysqld(self, ___, __, _):
        """Test _clean_data_dir_and_start_mysqld()."""
        success, error = self.mysql_backups._clean_data_dir_and_start_mysqld()

        self.assertTrue(success)
        self.assertIsNone(error)

    @patch_network_get(private_address="1.1.1.1")
    @patch("mysql_vm_helpers.MySQL.start_mysqld")
    @patch("mysql_vm_helpers.MySQL.delete_temp_restore_directory")
    @patch("mysql_vm_helpers.MySQL.delete_temp_backup_directory")
    def test_clean_data_dir_and_start_mysqld_failure(
        self, _delete_temp_backup_directory, _delete_temp_restore_directory, _start_mysqld
    ):
        """Test failure of _clean_data_dir_and_start_mysqld()."""
        # test failure of start_mysqld()
        _start_mysqld.side_effect = MySQLStartMySQLDError()
        success, error = self.mysql_backups._clean_data_dir_and_start_mysqld()

        self.assertFalse(success)
        self.assertEquals(error, "Failed to start mysqld")

        # test failure of delete_temp_backup_directory()
        _delete_temp_backup_directory.side_effect = MySQLDeleteTempBackupDirectoryError()
        success, error = self.mysql_backups._clean_data_dir_and_start_mysqld()

        self.assertFalse(success)
        self.assertEquals(error, "Failed to delete the temp backup directory")

        # test failure of delete_temp_restore_directory()
        _delete_temp_restore_directory.side_effect = MySQLDeleteTempRestoreDirectoryError()
        success, error = self.mysql_backups._clean_data_dir_and_start_mysqld()

        self.assertFalse(success)
        self.assertEquals(error, "Failed to delete the temp restore directory")

    @patch_network_get(private_address="1.1.1.1")
    @patch(
        "charms.mysql.v0.backups.MySQLBackups._clean_data_dir_and_start_mysqld",
        return_value=(True, None),
    )
    @patch("mysql_vm_helpers.MySQL.configure_instance")
    @patch("mysql_vm_helpers.MySQL.wait_until_mysql_connection")
    @patch("mysql_vm_helpers.MySQL.create_cluster")
    @patch("mysql_vm_helpers.MySQL.initialize_juju_units_operations_table")
    @patch("mysql_vm_helpers.MySQL.get_member_state", return_value=("online", "primary"))
    def test_post_restore(
        self,
        _get_member_state,
        _initialize_juju_units_operations_table,
        _create_cluster,
        _wait_until_mysql_connection,
        _configure_instance,
        _clean_data_dir_and_start_mysqld,
    ):
        """Test _post_restore()."""
        self.charm.unit.status = MaintenanceStatus()

        success, error_message = self.mysql_backups._post_restore()

        self.assertTrue(success)
        self.assertIsNone(error_message)

        _clean_data_dir_and_start_mysqld.assert_called_once()
        _configure_instance.assert_called_once_with(create_cluster_admin=False)
        _wait_until_mysql_connection.assert_called_once()
        _create_cluster.assert_called_once()
        _initialize_juju_units_operations_table.assert_called_once()
        _get_member_state.assert_called_once()

        self.assertTrue(isinstance(self.charm.unit.status, ActiveStatus))

    @patch_network_get(private_address="1.1.1.1")
    @patch(
        "charms.mysql.v0.backups.MySQLBackups._clean_data_dir_and_start_mysqld",
        return_value=(True, None),
    )
    @patch("mysql_vm_helpers.MySQL.configure_instance")
    @patch("mysql_vm_helpers.MySQL.wait_until_mysql_connection")
    @patch("mysql_vm_helpers.MySQL.create_cluster")
    @patch("mysql_vm_helpers.MySQL.initialize_juju_units_operations_table")
    @patch("mysql_vm_helpers.MySQL.get_member_state", return_value=("online", "primary"))
    def test_post_restore_failure(
        self,
        _get_member_state,
        _initialize_juju_units_operations_table,
        _create_cluster,
        _wait_until_mysql_connection,
        _configure_instance,
        _clean_data_dir_and_start_mysqld,
    ):
        """Test failure of _post_restore()."""
        self.charm.unit.status = MaintenanceStatus()

        # test failure of get_member_state()
        _get_member_state.side_effect = MySQLGetMemberStateError()

        success, error_message = self.mysql_backups._post_restore()
        self.assertFalse(success)
        self.assertEquals(error_message, "Failed to retrieve member state in restored instance")
        self.assertTrue(isinstance(self.charm.unit.status, MaintenanceStatus))

        # test failure of initialize_juju_units_operations_table()
        _initialize_juju_units_operations_table.side_effect = (
            MySQLInitializeJujuOperationsTableError()
        )

        success, error_message = self.mysql_backups._post_restore()
        self.assertFalse(success)
        self.assertEquals(error_message, "Failed to initialize the juju operations table")
        self.assertTrue(isinstance(self.charm.unit.status, MaintenanceStatus))

        # test failure of create_cluster()
        _create_cluster.side_effect = MySQLCreateClusterError()

        success, error_message = self.mysql_backups._post_restore()
        self.assertFalse(success)
        self.assertEquals(error_message, "Failed to create InnoDB cluster on restored instance")
        self.assertTrue(isinstance(self.charm.unit.status, MaintenanceStatus))

        # test failure of wait_until_mysql_connection()
        _wait_until_mysql_connection.side_effect = MySQLServiceNotRunningError()

        success, error_message = self.mysql_backups._post_restore()
        self.assertFalse(success)
        self.assertEquals(
            error_message, "Failed to configure restored instance for InnoDB cluster"
        )
        self.assertTrue(isinstance(self.charm.unit.status, MaintenanceStatus))

        # test failure of wait_until_mysql_connection()
        _configure_instance.side_effect = MySQLConfigureInstanceError()

        success, error_message = self.mysql_backups._post_restore()
        self.assertFalse(success)
        self.assertEquals(
            error_message, "Failed to configure restored instance for InnoDB cluster"
        )
        self.assertTrue(isinstance(self.charm.unit.status, MaintenanceStatus))

        # test failure of _clean_data_dir_and_start_mysqld()
        _clean_data_dir_and_start_mysqld.return_value = False, "failed to clean data dir"
        success, error_message = self.mysql_backups._post_restore()
        self.assertFalse(success)
        self.assertEquals(error_message, "failed to clean data dir")
        self.assertTrue(isinstance(self.charm.unit.status, MaintenanceStatus))
