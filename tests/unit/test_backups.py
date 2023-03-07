# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import MagicMock, patch

from charms.mysql.v0.mysql import (
    MySQLDeleteTempBackupDirectoryError,
    MySQLExecuteBackupCommandsError,
    MySQLGetMemberStateError,
    MySQLOfflineModeAndHiddenInstanceExistsError,
    MySQLSetInstanceOfflineModeError,
    MySQLSetInstanceOptionError,
)
from ops.model import ActiveStatus, BlockedStatus
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

    @patch("backups.upload_content_to_s3", return_value=True)
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
        "backups.MySQLBackups._retrieve_s3_parameters",
        return_value=({"bucket": "test-bucket"}, []),
    )
    @patch("backups.list_backups_in_s3_path", return_value=["backup1", "backup2"])
    def test_on_list_backups(self, _list_backups_in_s3_path, _retrieve_s3_parameters):
        """Test _on_list_backups()."""
        event = MagicMock()

        self.mysql_backups._on_list_backups(event)

        _retrieve_s3_parameters.assert_called_once()
        _list_backups_in_s3_path.assert_called_once_with({"bucket": "test-bucket"})

        event.set_results.assert_called_once_with({"backup-ids": '["backup1", "backup2"]'})
        event.fail.assert_not_called()

    @patch("backups.MySQLBackups._retrieve_s3_parameters")
    @patch("backups.list_backups_in_s3_path")
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

    @patch("datetime.datetime")
    @patch("backups.MySQLBackups._retrieve_s3_parameters", return_value=({"path": "/path"}, []))
    @patch("backups.MySQLBackups._can_unit_perform_backup", return_value=(True, None))
    @patch("ops.jujuversion.JujuVersion.from_environ", return_value="test-juju-version")
    @patch("backups.upload_content_to_s3")
    @patch("backups.MySQLBackups._pre_backup", return_value=(True, None))
    @patch("backups.MySQLBackups._backup", return_value=(True, None))
    @patch("backups.MySQLBackups._post_backup", return_value=(True, None))
    def test_on_create_backup(
        self,
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

    @patch("datetime.datetime")
    @patch("backups.MySQLBackups._retrieve_s3_parameters", return_value=({"path": "/path"}, []))
    @patch("backups.MySQLBackups._can_unit_perform_backup", return_value=(True, None))
    @patch("ops.jujuversion.JujuVersion.from_environ", return_value="test-juju-version")
    @patch("backups.upload_content_to_s3")
    @patch("backups.MySQLBackups._pre_backup", return_value=(True, None))
    @patch("backups.MySQLBackups._backup", return_value=(True, None))
    @patch("backups.MySQLBackups._post_backup", return_value=(True, None))
    def test_on_create_backup_failure(
        self,
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
        self.assertEqual(error_message, "Cluster or unit is waiting to start or restart")

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
    @patch("backups.MySQLBackups._upload_logs_to_s3")
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
    @patch("backups.MySQLBackups._upload_logs_to_s3")
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
