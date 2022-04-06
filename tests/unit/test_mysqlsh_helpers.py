# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import subprocess
import unittest
from unittest.mock import patch

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

    @patch("mysqlsh_helpers.MySQL._run_mysqlsh_script")
    @patch("mysqlsh_helpers.MySQL._wait_until_mysql_connection")
    def test_configure_instance(self, _wait_until_mysql_connection, _run_mysqlsh_script):
        """Test a successful execution of configure_instance."""
        configure_instance_commands = [
            "dba.configure_instance('clusteradmin:innodb@127.0.0.1')",
            "my_shell = shell.connect('clusteradmin:innodb@127.0.0.1')",
            'my_shell.run_sql("RESTART;");',
        ]

        self.mysql.configure_instance()

        _run_mysqlsh_script.assert_called_once_with("\n".join(configure_instance_commands))
        _wait_until_mysql_connection.assert_called_once()

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
