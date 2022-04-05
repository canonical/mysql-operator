# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import subprocess
import unittest
from unittest.mock import PropertyMock, patch

from mysqlsh_helpers import MySQL, MySQLInstanceConfigureError


class TestMySQL(unittest.TestCase):
    def setUp(self):
        root_password = "password"
        cluster_admin_user = "clusteradmin"
        cluster_admin_password = "innodb"
        instance_address = "127.0.0.1"

        self.mysql = MySQL(
            root_password, cluster_admin_user, cluster_admin_password, instance_address
        )

    @patch("os.path.exists", return_value=False)
    @patch("mysqlsh_helpers.MySQL.mysqlsh_bin", new_callable=PropertyMock)
    @patch("subprocess.check_call")
    @patch("tempfile.NamedTemporaryFile")
    @patch("subprocess.check_output")
    def test_run_mysqlsh_script(
        self, _check_output, _named_temporary_file, _check_call, _mysqlsh_bin, _exists
    ):
        """Test successful execution of _run_mysqlsh_script."""
        _mysqlsh_bin.return_value = "test_mysqlsh"
        _named_temporary_file.return_value.__enter__.return_value.name = "test_temp_file"

        self.mysql._run_mysqlsh_script("test_script")

        _check_call.assert_called_once_with(["test_mysqlsh", "--help"], stderr=subprocess.PIPE)

        _check_output.assert_called_once_with(
            ["test_mysqlsh", "--no-wizard", "--python", "-f", "test_temp_file"],
            stderr=subprocess.PIPE,
        )

    @patch("os.path.exists", return_value=True)
    @patch("mysqlsh_helpers.MySQL.mysqlsh_bin", new_callable=PropertyMock)
    @patch("subprocess.check_call")
    @patch("tempfile.NamedTemporaryFile")
    @patch("subprocess.check_output")
    def test_run_mysqlsh_script_common_dir_exists(
        self, _check_output, _named_temporary_file, _check_call, _mysqlsh_bin, _exists
    ):
        """Test successful execution of _run_mysqlsh_script with existence of common dir."""
        _mysqlsh_bin.return_value = "test_mysqlsh"
        _named_temporary_file.return_value.__enter__.return_value.name = "test_temp_file"

        self.mysql._run_mysqlsh_script("test_script")

        _check_call.assert_not_called()

        _check_output.assert_called_once_with(
            ["test_mysqlsh", "--no-wizard", "--python", "-f", "test_temp_file"],
            stderr=subprocess.PIPE,
        )

    @patch("mysqlsh_helpers.MySQL._run_mysqlsh_script", return_value="success")
    def test_wait_until_mysql_connection(self, _):
        """Test that no exceptions raised while running _wait_until_mysql_connection."""
        self.mysql._wait_until_mysql_connection()

    @patch("mysqlsh_helpers.MySQL._run_mysqlsh_script")
    @patch("mysqlsh_helpers.MySQL._wait_until_mysql_connection")
    def test_configure_instance(self, _wait_until_mysql_connection, _run_mysqlsh_script):
        """Test a successful execution of configure_instance."""
        self.mysql.configure_instance()

    @patch("mysqlsh_helpers.MySQL._run_mysqlsh_script")
    @patch("mysqlsh_helpers.MySQL._wait_until_mysql_connection")
    def test_configure_instance_exceptions(
        self, _wait_until_mysql_connection, _run_mysqlsh_script
    ):
        """Test exceptions raised by methods called in configure_instance."""
        # Test an issue with _run_mysqlsh_script
        _run_mysqlsh_script.side_effect = subprocess.CalledProcessError(cmd="mock", returncode=127)

        with self.assertRaises(MySQLInstanceConfigureError):
            self.mysql.configure_instance()

        _wait_until_mysql_connection.assert_not_called()

        # Reset mocks
        _run_mysqlsh_script.reset_mock()
        _wait_until_mysql_connection.reset_mock()

        # Test an issue with _wait_until_mysql_connection
        _wait_until_mysql_connection.side_effect = subprocess.CalledProcessError(
            cmd="mock", returncode=127
        )

        with self.assertRaises(MySQLInstanceConfigureError):
            self.mysql.configure_instance()

        _run_mysqlsh_script.assert_called_once()
