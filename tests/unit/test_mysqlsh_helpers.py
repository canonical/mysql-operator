# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for MySQL class."""

import subprocess
import unittest
from unittest.mock import patch

from charms.mysql.v0.mysql import MySQLClientError

from mysql_vm_helpers import (
    MySQL,
    MySQLResetRootPasswordAndStartMySQLDError,
    MySQLServiceNotRunningError,
    SnapServiceOperationError,
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
