# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import subprocess
import unittest
from unittest.mock import patch

from mysqlsh_helpers import (
    MySQL,
    MySQLAddInstanceToClusterError,
    MySQLConfigureInstanceError,
    MySQLConfigureMySQLUsersError,
    MySQLCreateClusterError,
)


class TestMySQL(unittest.TestCase):
    def setUp(self):
        with patch("mysqlsh_helpers.MySQL._ensure_mysqlsh_common_dir"):
            self.mysql = MySQL(
                "clusteradminpassword",
                "clusteradmin",
                "test_cluster",
                "127.0.0.1",
                "password",
                "serverconfigpassword",
                "serverconfig",
            )

    @patch("mysqlsh_helpers.MySQL._run_mysqlcli_script")
    def test_configure_mysql_users(self, _run_mysqlcli_script):
        """Test failed to configuring the MySQL users."""
        _run_mysqlcli_script.return_value = b""

        _expected_script = " ".join(
            (
                "SET @@SESSION.SQL_LOG_BIN=0;",
                "CREATE USER 'root'@'%' IDENTIFIED BY 'password';",
                "GRANT ALL ON *.* TO 'root'@'%' WITH GRANT OPTION;",
                "CREATE USER 'serverconfig'@'%' IDENTIFIED BY 'serverconfigpassword';",
                "GRANT ALL ON *.* TO 'serverconfig'@'%' WITH GRANT OPTION;",
                "UPDATE mysql.user SET authentication_string=null WHERE User='root' and Host='localhost';",
                "ALTER USER 'root'@'localhost' IDENTIFIED WITH mysql_native_password BY 'password';",
                "REVOKE SYSTEM_USER, SYSTEM_VARIABLES_ADMIN, SUPER, REPLICATION_SLAVE_ADMIN, GROUP_REPLICATION_ADMIN, BINLOG_ADMIN, SET_USER_ID, ENCRYPTION_KEY_ADMIN, VERSION_TOKEN_ADMIN, CONNECTION_ADMIN ON *.* FROM root@'%';",
                "REVOKE SYSTEM_USER, SYSTEM_VARIABLES_ADMIN, SUPER, REPLICATION_SLAVE_ADMIN, GROUP_REPLICATION_ADMIN, BINLOG_ADMIN, SET_USER_ID, ENCRYPTION_KEY_ADMIN, VERSION_TOKEN_ADMIN, CONNECTION_ADMIN ON *.* FROM root@localhost;",
                "FLUSH PRIVILEGES;",
            )
        )

        self.mysql.configure_mysql_users()
        _run_mysqlcli_script.assert_called_once_with(_expected_script)

    @patch("mysqlsh_helpers.MySQL._run_mysqlcli_script")
    def test_configure_mysql_users_fail(self, _run_mysqlcli_script):
        """Test failed to configuring the MySQL users."""
        _run_mysqlcli_script.side_effect = subprocess.CalledProcessError(
            cmd="mysqlsh", returncode=127
        )

        with self.assertRaises(MySQLConfigureMySQLUsersError):
            self.mysql.configure_mysql_users()

    @patch("os.path.exists")
    def test_mysqlsh_bin(self, _exists):
        """Test the mysqlsh_bin property."""
        _exists.return_value = True
        self.assertEqual(self.mysql._mysqlsh_bin, "/usr/bin/mysqlsh")

        _exists.return_value = False
        self.assertEqual(self.mysql._mysqlsh_bin, "/snap/bin/mysql-shell")

    @patch("mysqlsh_helpers.MySQL._run_mysqlsh_script")
    @patch("mysqlsh_helpers.MySQL._wait_until_mysql_connection")
    def test_configure_instance(self, _wait_until_mysql_connection, _run_mysqlsh_script):
        """Test a successful execution of configure_instance."""
        configure_instance_commands = (
            'dba.configure_instance(\'serverconfig:serverconfigpassword@127.0.0.1\', {"clusterAdmin": "clusteradmin", "clusterAdminPassword": "clusteradminpassword", "restart": "true"})',
        )

        self.mysql.configure_instance()

        _run_mysqlsh_script.assert_called_once_with("\n".join(configure_instance_commands))
        _wait_until_mysql_connection.assert_called_once()

    @patch("mysqlsh_helpers.MySQL._run_mysqlsh_script")
    @patch("mysqlsh_helpers.MySQL._wait_until_mysql_connection")
    def test_configure_instance_exceptions(
        self, _wait_until_mysql_connection, _run_mysqlsh_script
    ):
        """Test exceptions raise while running configure_instance."""
        # Test an issue with _run_mysqlsh_script
        _run_mysqlsh_script.side_effect = subprocess.CalledProcessError(cmd="mock", returncode=127)

        with self.assertRaises(MySQLConfigureInstanceError):
            self.mysql.configure_instance()

        _wait_until_mysql_connection.assert_not_called()

        # Reset mocks
        _run_mysqlsh_script.reset_mock()
        _wait_until_mysql_connection.reset_mock()

        # Test an issue with _wait_until_mysql_connection
        _wait_until_mysql_connection.side_effect = subprocess.CalledProcessError(
            cmd="mock", returncode=127
        )

        with self.assertRaises(MySQLConfigureInstanceError):
            self.mysql.configure_instance()

        _run_mysqlsh_script.assert_called_once()

    @patch("mysqlsh_helpers.MySQL._run_mysqlsh_script")
    def test_create_cluster(self, _run_mysqlsh_script):
        """Test a successful execution of create_cluster."""
        create_cluster_commands = (
            "shell.connect('serverconfig:serverconfigpassword@127.0.0.1')",
            "dba.create_cluster('test_cluster')",
        )

        self.mysql.create_cluster()

        _run_mysqlsh_script.assert_called_once_with("\n".join(create_cluster_commands))

    @patch("mysqlsh_helpers.MySQL._run_mysqlsh_script")
    def test_create_cluster_exceptions(self, _run_mysqlsh_script):
        """Test exceptions raised while running create_cluster."""
        _run_mysqlsh_script.side_effect = subprocess.CalledProcessError(cmd="mock", returncode=127)

        with self.assertRaises(MySQLCreateClusterError):
            self.mysql.create_cluster()

    @patch("mysqlsh_helpers.MySQL._run_mysqlsh_script")
    def test_add_instance_to_cluster(self, _run_mysqlsh_script):
        """Test a successful execution of create_cluster."""
        add_instance_to_cluster_commands = (
            "shell.connect('clusteradmin:clusteradminpassword@127.0.0.1')",
            "cluster = dba.get_cluster('test_cluster')",
            'cluster.add_instance(\'clusteradmin@127.0.0.2\', {"password": "clusteradminpassword", "recoveryMethod": "clone"})',
        )

        self.mysql.add_instance_to_cluster("127.0.0.2")

        _run_mysqlsh_script.assert_called_once_with("\n".join(add_instance_to_cluster_commands))

    @patch("mysqlsh_helpers.MySQL._run_mysqlsh_script")
    def test_add_instance_to_cluster_exception(self, _run_mysqlsh_script):
        """Test exceptions raised while running add_instance_to_cluster."""
        _run_mysqlsh_script.side_effect = subprocess.CalledProcessError(cmd="mock", returncode=127)

        with self.assertRaises(MySQLAddInstanceToClusterError):
            self.mysql.add_instance_to_cluster("127.0.0.2")
