# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for MySQL class."""

import subprocess
import unittest
from unittest.mock import MagicMock, patch

from charms.mysql.v0.mysql import MySQLClientError

from constants import CHARMED_MYSQL_SNAP_NAME, CHARMED_MYSQLD_SERVICE
from mysql_vm_helpers import (
    MySQL,
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
        self.mysql._run_mysqlcli_script("script")

        _check_output.assert_called_once_with(
            [
                "charmed-mysql.mysql",
                "-u",
                "root",
                "--protocol=SOCKET",
                "--socket=/var/snap/charmed-mysql/common/mysql/mysqld.sock",
                "-e",
                "script",
            ],
            stderr=subprocess.PIPE,
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
        self.assertEqual(4, _check_output.call_count)
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
        self.assertEqual(4, _check_output.call_count)
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
        self.assertEqual(4, _check_output.call_count)
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
