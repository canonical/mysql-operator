# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for MySQL class."""

import subprocess
import unittest
from unittest.mock import patch

from charms.mysql.v0.mysql import MySQLClientError

from mysql_vm_helpers import MySQL, MySQLServiceNotRunningError


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
            "exporter",
            "exporterpassword",
        )

    @patch("os.path.exists")
    def test_mysqlsh_bin(self, _exists):
        """Test the mysqlsh_bin property."""
        _exists.return_value = True
        self.assertEqual(MySQL.get_mysqlsh_bin(), "/usr/bin/mysqlsh")

        _exists.return_value = False
        self.assertEqual(MySQL.get_mysqlsh_bin(), "/snap/bin/mysql-shell")

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
                "mysql",
                "-u",
                "root",
                "--protocol=SOCKET",
                "--socket=/var/run/mysqld/mysqld.sock",
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
