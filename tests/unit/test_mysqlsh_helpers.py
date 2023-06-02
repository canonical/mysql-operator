# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for MySQL class."""

import subprocess
import unittest
from unittest.mock import MagicMock, call, patch

from charms.mysql.v0.mysql import (
    MySQLClientError,
    MySQLExecError,
    MySQLGetAutoTunningParametersError,
    MySQLStartMySQLDError,
    MySQLStopMySQLDError,
)

from constants import (
    CHARMED_MYSQL_SNAP_NAME,
    CHARMED_MYSQLD_SERVICE,
    MYSQLD_CONFIG_DIRECTORY,
)
from mysql_vm_helpers import (
    MySQL,
    MySQLCreateCustomMySQLDConfigError,
    MySQLResetRootPasswordAndStartMySQLDError,
    MySQLServiceNotRunningError,
    SnapServiceOperationError,
    snap_service_operation,
)


class TestMySQL(unittest.TestCase):
    def setUp(self):
        self.mysql = MySQL(
            "127.0.0.1",
            "test_cluster",
            "password",
            "serverconfig",
            "serverconfigpassword",
            "clusteradmin",
            "clusteradminpassword",
            "monitoring",
            "monitoringpassword",
            "backups",
            "backupspassword",
        )

    @patch("tempfile.NamedTemporaryFile")
    @patch("subprocess.check_output")
    def test_run_mysqlsh_script(self, _check_output, _):
        """Test a successful execution of run_mysqlsh_script."""
        _check_output.return_value = b"stdout"

        self.mysql._run_mysqlsh_script("script")

        _check_output.assert_called_once()

    @patch("tempfile.NamedTemporaryFile")
    @patch("subprocess.check_output")
    def test_run_mysqlsh_script_exception(self, _check_output, _):
        """Test a failed execution of run_mysqlsh_script."""
        _check_output.side_effect = subprocess.CalledProcessError(cmd="", returncode=-1)

        with self.assertRaises(MySQLClientError):
            self.mysql._run_mysqlsh_script("script")

    @patch("subprocess.check_output")
    def test_run_mysqlcli_script(self, _check_output):
        """Test a successful execution of run_mysqlsh_script."""
        self.mysql._run_mysqlcli_script("script", timeout=10)

        _check_output.assert_called_once_with(
            [
                "charmed-mysql.mysql",
                "-u",
                "root",
                "--protocol=SOCKET",
                "--socket=/var/snap/charmed-mysql/common/var/run/mysqld/mysqld.sock",
                "-e",
                "script",
            ],
            stderr=subprocess.PIPE,
            timeout=10,
        )

    @patch("subprocess.check_output")
    def test_run_mysqlcli_script_exception(self, _check_output):
        """Test a failed execution of run_mysqlsh_script."""
        _check_output.side_effect = subprocess.CalledProcessError(cmd="", returncode=-1)

        with self.assertRaises(MySQLClientError):
            self.mysql._run_mysqlcli_script("script")

    @patch("mysql_vm_helpers.MySQL.wait_until_mysql_connection.retry.stop", return_value=1)
    @patch("os.path.exists", return_value=False)
    def test_wait_until_mysql_connection(self, _exists, _stop):
        """Test a failed execution of wait_until_mysql_connection."""
        with self.assertRaises(MySQLServiceNotRunningError):
            self.mysql.wait_until_mysql_connection()

    @patch("tempfile.NamedTemporaryFile")
    @patch("subprocess.check_output")
    @patch("mysql_vm_helpers.snap_service_operation")
    @patch("mysql_vm_helpers.MySQL.wait_until_mysql_connection")
    def test_reset_root_password_and_start_mysqld(
        self,
        _wait_until_mysql_connection,
        _snap_service_operation,
        _check_output,
        _named_temporary_file,
    ):
        """Test a successful execution of reset_root_password_and_start_mysqld."""
        self.mysql.reset_root_password_and_start_mysqld()

        self.assertEqual(2, _named_temporary_file.call_count)
        self.assertEqual(2, _check_output.call_count)
        self.assertEqual(1, _snap_service_operation.call_count)
        self.assertEqual(1, _wait_until_mysql_connection.call_count)

    @patch("tempfile.NamedTemporaryFile")
    @patch("subprocess.check_output")
    @patch("mysql_vm_helpers.snap_service_operation")
    @patch("mysql_vm_helpers.MySQL.wait_until_mysql_connection")
    def test_reset_root_password_and_start_mysqld_exception(
        self,
        _wait_until_mysql_connection,
        _snap_service_operation,
        _check_output,
        _named_temporary_file,
    ):
        """Test a failed execution of reset_root_password_and_start_mysqld."""
        _check_output.side_effect = subprocess.CalledProcessError(cmd="", returncode=-1)

        with self.assertRaises(MySQLResetRootPasswordAndStartMySQLDError):
            self.mysql.reset_root_password_and_start_mysqld()

        self.assertEqual(2, _named_temporary_file.call_count)
        self.assertEqual(1, _check_output.call_count)
        self.assertEqual(0, _snap_service_operation.call_count)
        self.assertEqual(0, _wait_until_mysql_connection.call_count)

        _named_temporary_file.reset_mock()
        _check_output.reset_mock()
        _snap_service_operation.reset_mock()
        _wait_until_mysql_connection.reset_mock()

        _check_output.side_effect = None
        _snap_service_operation.side_effect = SnapServiceOperationError()

        with self.assertRaises(MySQLResetRootPasswordAndStartMySQLDError):
            self.mysql.reset_root_password_and_start_mysqld()

        self.assertEqual(2, _named_temporary_file.call_count)
        self.assertEqual(2, _check_output.call_count)
        self.assertEqual(1, _snap_service_operation.call_count)
        self.assertEqual(0, _wait_until_mysql_connection.call_count)

        _named_temporary_file.reset_mock()
        _check_output.reset_mock()
        _snap_service_operation.reset_mock()
        _wait_until_mysql_connection.reset_mock()

        _check_output.side_effect = None
        _snap_service_operation.side_effect = None
        _wait_until_mysql_connection.side_effect = MySQLServiceNotRunningError()

        with self.assertRaises(MySQLResetRootPasswordAndStartMySQLDError):
            self.mysql.reset_root_password_and_start_mysqld()

        self.assertEqual(2, _named_temporary_file.call_count)
        self.assertEqual(2, _check_output.call_count)
        self.assertEqual(1, _snap_service_operation.call_count)
        self.assertEqual(1, _wait_until_mysql_connection.call_count)

    @patch("mysql_vm_helpers.snap.SnapCache")
    def test_reconfigure_mysqld(self, _snap_cache):
        """Test a successful execution of method reconfigure_mysqld."""
        _charmed_mysql_mock = MagicMock()
        _cache = {CHARMED_MYSQL_SNAP_NAME: _charmed_mysql_mock}
        _snap_cache.return_value.__getitem__.side_effect = _cache.__getitem__

        self.mysql.reconfigure_mysqld()

        _snap_cache.assert_called_once()

        _charmed_mysql_mock._remove.assert_called_once()
        _charmed_mysql_mock.ensure.assert_called_once()

    @patch("mysql_vm_helpers.snap.SnapCache")
    def test_snap_service_operation(self, _snap_cache):
        """Test a successful execution of function snap_service_operation."""
        _charmed_mysql_mock = MagicMock()
        _cache = {CHARMED_MYSQL_SNAP_NAME: _charmed_mysql_mock}
        _snap_cache.return_value.__getitem__.side_effect = _cache.__getitem__

        # Test start operation
        snap_service_operation(CHARMED_MYSQL_SNAP_NAME, CHARMED_MYSQLD_SERVICE, "start")

        _snap_cache.assert_called_once()
        _charmed_mysql_mock.start.assert_called_once()
        _charmed_mysql_mock.restart.assert_not_called()
        _charmed_mysql_mock.stop.assert_not_called()

        # Test restart operation
        _snap_cache.reset_mock()
        _charmed_mysql_mock.reset_mock()

        snap_service_operation(CHARMED_MYSQL_SNAP_NAME, CHARMED_MYSQLD_SERVICE, "restart")

        _snap_cache.assert_called_once()
        _charmed_mysql_mock.start.assert_not_called()
        _charmed_mysql_mock.restart.assert_called_once()
        _charmed_mysql_mock.stop.assert_not_called()

        # Test stop operation
        _snap_cache.reset_mock()
        _charmed_mysql_mock.reset_mock()

        snap_service_operation(CHARMED_MYSQL_SNAP_NAME, CHARMED_MYSQLD_SERVICE, "stop")

        _snap_cache.assert_called_once()
        _charmed_mysql_mock.start.assert_not_called()
        _charmed_mysql_mock.restart.assert_not_called()
        _charmed_mysql_mock.stop.assert_called_once()

    @patch("mysql_vm_helpers.snap.SnapCache")
    def test_snap_service_operation_exception(self, _snap_cache):
        """Test failure in execution of function snap_service_operation."""
        _charmed_mysql_mock = MagicMock()
        _cache = {CHARMED_MYSQL_SNAP_NAME: _charmed_mysql_mock}
        _snap_cache.return_value.__getitem__.side_effect = _cache.__getitem__

        with self.assertRaises(SnapServiceOperationError):
            snap_service_operation(CHARMED_MYSQL_SNAP_NAME, CHARMED_MYSQLD_SERVICE, "nonsense")

        _snap_cache.assert_not_called()

    @patch("mysql_vm_helpers.MySQL.get_innodb_buffer_pool_parameters", return_value=(1234, 5678))
    @patch("pathlib.Path")
    @patch("builtins.open")
    def test_create_custom_mysqld_config(self, _open, _path, _get_innodb_buffer_pool_parameters):
        """Test successful execution of create_custom_mysqld_config."""
        _path_mock = MagicMock()
        _path.return_value = _path_mock

        _open_mock = unittest.mock.mock_open()
        _open.side_effect = _open_mock

        self.mysql.create_custom_mysqld_config()

        config = """[mysqld]
bind-address = 0.0.0.0
mysqlx-bind-address = 0.0.0.0
innodb_buffer_pool_size = 1234
innodb_buffer_pool_chunk_size = 5678
report_host = 127.0.0.1
"""

        _get_innodb_buffer_pool_parameters.assert_called_once()
        _path_mock.mkdir.assert_called_once_with(mode=0o755, parents=True, exist_ok=True)
        _open.assert_called_once_with(f"{MYSQLD_CONFIG_DIRECTORY}/z-custom-mysqld.cnf", "w")

        self.assertEqual(
            sorted(_open_mock.mock_calls),
            sorted(
                [
                    call(f"{MYSQLD_CONFIG_DIRECTORY}/z-custom-mysqld.cnf", "w"),
                    call().__enter__(),
                    call().write(config),
                    call().__exit__(None, None, None),
                ]
            ),
        )

    @patch("mysql_vm_helpers.MySQL.get_innodb_buffer_pool_parameters", return_value=(1234, 5678))
    @patch("pathlib.Path")
    @patch("builtins.open")
    def test_create_custom_mysqld_config_exception(
        self, _open, _path, _get_innodb_buffer_pool_parameters
    ):
        """Test failure in execution of create_custom_mysqld_config."""
        _get_innodb_buffer_pool_parameters.side_effect = MySQLGetAutoTunningParametersError

        _path_mock = MagicMock()
        _path.return_value = _path_mock

        _open_mock = unittest.mock.mock_open()
        _open.side_effect = _open_mock

        with self.assertRaises(MySQLCreateCustomMySQLDConfigError):
            self.mysql.create_custom_mysqld_config()

    @patch("subprocess.run")
    def test_execute_commands(self, _run):
        """Test a successful execution of _execute_commands."""
        self.mysql._execute_commands(
            ["ls", "-la", "|", "wc", "-l"],
            bash=True,
            user="test_user",
            group="test_group",
            env={"envA": "valueA"},
        )

        _run.assert_called_once_with(
            ["bash", "-c", "set -o pipefail; ls -la | wc -l"],
            user="test_user",
            group="test_group",
            env={
                "envA": "valueA",
            },
            capture_output=True,
            check=True,
            encoding="utf-8",
        )

    @patch("subprocess.run")
    def test_execute_commands_exception(self, _run):
        """Test a failure in execution of _execute_commands."""
        _run.side_effect = subprocess.CalledProcessError(cmd="", returncode=-1)

        with self.assertRaises(MySQLExecError):
            self.mysql._execute_commands(
                ["ls", "-la"],
                bash=True,
                user="test_user",
                group="test_group",
                env={"envA": "valueA"},
            )

    @patch("os.path.exists", return_value=True)
    def test_is_mysqld_running(self, _path_exists):
        """Test execution of is_mysqld_running()."""
        self.assertTrue(self.mysql.is_mysqld_running())

        _path_exists.return_value = False
        self.assertFalse(self.mysql.is_mysqld_running())

    @patch("mysql_vm_helpers.snap_service_operation")
    def test_stop_mysqld(self, _snap_service_operation):
        """Test execution of stop_mysqld()."""
        self.mysql.stop_mysqld()

        _snap_service_operation.assert_called_once_with(
            CHARMED_MYSQL_SNAP_NAME, CHARMED_MYSQLD_SERVICE, "stop"
        )

    @patch("mysql_vm_helpers.snap_service_operation")
    def test_stop_mysqld_failure(self, _snap_service_operation):
        """Test failure of stop_mysqld()."""
        _snap_service_operation.side_effect = SnapServiceOperationError("failure")

        with self.assertRaises(MySQLStopMySQLDError):
            self.mysql.stop_mysqld()

    @patch("mysql_vm_helpers.snap_service_operation")
    @patch("mysql_vm_helpers.MySQL.wait_until_mysql_connection")
    def test_start_mysqld(
        self,
        _wait_until_mysql_connection,
        _snap_service_operation,
    ):
        """Test execution of start_mysqld()."""
        self.mysql.start_mysqld()

        _snap_service_operation.assert_called_once_with(
            CHARMED_MYSQL_SNAP_NAME, CHARMED_MYSQLD_SERVICE, "start"
        )
        _wait_until_mysql_connection.assert_called_once()

    @patch("mysql_vm_helpers.snap_service_operation")
    @patch("mysql_vm_helpers.MySQL.wait_until_mysql_connection")
    def test_start_mysqld_failure(
        self,
        _wait_until_mysql_connection,
        _snap_service_operation,
    ):
        """Test failure of start_mysqld()."""
        _snap_service_operation.side_effect = SnapServiceOperationError("failure")

        with self.assertRaises(MySQLStartMySQLDError):
            self.mysql.start_mysqld()

        _snap_service_operation.reset_mock()
        _wait_until_mysql_connection.side_effect = MySQLServiceNotRunningError

        with self.assertRaises(MySQLStartMySQLDError):
            self.mysql.start_mysqld()
