# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import subprocess
import unittest
from unittest.mock import call, patch

import tenacity

from mysqlsh_helpers import (
    MySQL,
    MySQLAddInstanceToClusterError,
    MySQLConfigureInstanceError,
    MySQLConfigureMySQLUsersError,
    MySQLCreateClusterError,
    MySQLRemoveInstanceDBConnectionError,
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

    @patch("mysqlsh_helpers.MySQL._run_mysqlcli_script")
    def test_configure_mysql_users(self, _run_mysqlcli_script):
        """Test failed to configuring the MySQL users."""
        _run_mysqlcli_script.return_value = b""

        _expected_create_root_user_commands = " ".join(
            (
                "CREATE USER 'root'@'%' IDENTIFIED BY 'password';",
                "GRANT ALL ON *.* TO 'root'@'%' WITH GRANT OPTION;",
            )
        )

        _expected_configure_user_commands = " ".join(
            (
                "CREATE USER 'serverconfig'@'%' IDENTIFIED BY 'serverconfigpassword';",
                "GRANT ALL ON *.* TO 'serverconfig'@'%' WITH GRANT OPTION;",
                "UPDATE mysql.user SET authentication_string=null WHERE User='root' and Host='localhost';",
                "ALTER USER 'root'@'localhost' IDENTIFIED BY 'password';",
                "REVOKE SYSTEM_USER, SYSTEM_VARIABLES_ADMIN, SUPER, REPLICATION_SLAVE_ADMIN, GROUP_REPLICATION_ADMIN, BINLOG_ADMIN, SET_USER_ID, ENCRYPTION_KEY_ADMIN, VERSION_TOKEN_ADMIN, CONNECTION_ADMIN ON *.* FROM root@'%';",
                "REVOKE SYSTEM_USER, SYSTEM_VARIABLES_ADMIN, SUPER, REPLICATION_SLAVE_ADMIN, GROUP_REPLICATION_ADMIN, BINLOG_ADMIN, SET_USER_ID, ENCRYPTION_KEY_ADMIN, VERSION_TOKEN_ADMIN, CONNECTION_ADMIN ON *.* FROM root@localhost;",
                "FLUSH PRIVILEGES;",
            )
        )

        self.mysql.configure_mysql_users()

        self.assertEqual(_run_mysqlcli_script.call_count, 2)

        self.assertEqual(
            sorted(_run_mysqlcli_script.mock_calls),
            sorted(
                [
                    call(_expected_create_root_user_commands),
                    call(_expected_configure_user_commands, password="password"),
                ]
            ),
        )

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
        self.assertEqual(MySQL.get_mysqlsh_bin(), "/usr/bin/mysqlsh")

        _exists.return_value = False
        self.assertEqual(MySQL.get_mysqlsh_bin(), "/snap/bin/mysql-shell")

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
            "cluster = dba.create_cluster('test_cluster')",
            "cluster.set_instance_option('127.0.0.1', 'label', 'mysql-0')",
        )

        self.mysql.create_cluster("mysql-0")

        _run_mysqlsh_script.assert_called_once_with("\n".join(create_cluster_commands))

    @patch("mysqlsh_helpers.MySQL._run_mysqlsh_script")
    def test_create_cluster_exceptions(self, _run_mysqlsh_script):
        """Test exceptions raised while running create_cluster."""
        _run_mysqlsh_script.side_effect = subprocess.CalledProcessError(cmd="mock", returncode=127)

        with self.assertRaises(MySQLCreateClusterError):
            self.mysql.create_cluster("mysql-0")

    @patch("mysqlsh_helpers.MySQL._run_mysqlsh_script")
    def test_add_instance_to_cluster(self, _run_mysqlsh_script):
        """Test a successful execution of create_cluster."""
        add_instance_to_cluster_commands = (
            "shell.connect('clusteradmin:clusteradminpassword@127.0.0.1')",
            "session.run_sql(\"SELECT get_lock('add_instance', -1);\")",
            "cluster = dba.get_cluster('test_cluster')",
            'cluster.add_instance(\'clusteradmin@127.0.0.2\', {"password": "clusteradminpassword", "label": "mysql-1", "recoveryMethod": "auto"})',
            "session.run_sql(\"SELECT release_lock('add_instance');\")",
        )

        self.mysql.add_instance_to_cluster("127.0.0.2", "mysql-1")

        _run_mysqlsh_script.assert_called_once_with("\n".join(add_instance_to_cluster_commands))

    @patch("mysqlsh_helpers.MySQL._run_mysqlsh_script")
    def test_add_instance_to_cluster_exception(self, _run_mysqlsh_script):
        """Test exceptions raised while running add_instance_to_cluster."""
        _run_mysqlsh_script.side_effect = subprocess.CalledProcessError(cmd="mock", returncode=127)

        with self.assertRaises(MySQLAddInstanceToClusterError):
            self.mysql.add_instance_to_cluster("127.0.0.2", "mysql-1")

    @patch("mysqlsh_helpers.MySQL._run_mysqlsh_script", return_value="INSTANCE_CONFIGURED")
    def test_is_instance_configured_for_innodb(self, _run_mysqlsh_script):
        """Test with no exceptions while calling the is_instance_configured_for_innodb method."""
        # test successfully configured instance
        check_instance_configuration_commands = (
            "shell.connect('clusteradmin:clusteradminpassword@127.0.0.2')",
            "instance_configured = dba.check_instance_configuration()['status'] == 'ok'",
            'print("INSTANCE_CONFIGURED" if instance_configured else "INSTANCE_NOT_CONFIGURED")',
        )

        is_instance_configured = self.mysql.is_instance_configured_for_innodb(
            "127.0.0.2", "mysql-1"
        )

        _run_mysqlsh_script.assert_called_once_with(
            "\n".join(check_instance_configuration_commands)
        )
        self.assertTrue(is_instance_configured)

        # reset mocks
        _run_mysqlsh_script.reset_mock()

        # test instance not configured for innodb
        _run_mysqlsh_script.return_value = "INSTANCE_NOT_CONFIGURED"

        is_instance_configured = self.mysql.is_instance_configured_for_innodb(
            "127.0.0.2", "mysql-1"
        )

        _run_mysqlsh_script.assert_called_once_with(
            "\n".join(check_instance_configuration_commands)
        )
        self.assertFalse(is_instance_configured)

    @patch("mysqlsh_helpers.MySQL._run_mysqlsh_script")
    def test_is_instance_configured_for_innodb_exceptions(self, _run_mysqlsh_script):
        """Test an exception while calling the is_instance_configured_for_innodb method."""
        _run_mysqlsh_script.side_effect = subprocess.CalledProcessError(cmd="mock", returncode=127)

        check_instance_configuration_commands = (
            "shell.connect('clusteradmin:clusteradminpassword@127.0.0.2')",
            "instance_configured = dba.check_instance_configuration()['status'] == 'ok'",
            'print("INSTANCE_CONFIGURED" if instance_configured else "INSTANCE_NOT_CONFIGURED")',
        )

        is_instance_configured = self.mysql.is_instance_configured_for_innodb(
            "127.0.0.2", "mysql-1"
        )

        _run_mysqlsh_script.assert_called_once_with(
            "\n".join(check_instance_configuration_commands)
        )
        self.assertFalse(is_instance_configured)

    @patch("mysqlsh_helpers.MySQL._run_mysqlsh_script")
    def test_remove_instance(self, _run_mysqlsh_script):
        """Test with no exceptions while running the remove_instance() method."""
        expected_commands = (
            "cluster_admin_user = 'clusteradmin'",
            "cluster_admin_password = 'clusteradminpassword'",
            "this_instance_address = '127.0.0.1'",
            "remove_instance_address = '127.0.0.2'",
            "cluster_name = 'test_cluster'",
            'remove_instance_options = {"password": "clusteradminpassword", "force": "true"}',
            'dissolve_cluster_options = {"force": "true"}',
            "shell.connect(f'{cluster_admin_user}:{cluster_admin_password}@{this_instance_address}')",
            "cluster = dba.get_cluster(f'{cluster_name}')",
            "primary_address = sorted([cluster_member['address'] for cluster_member in cluster.status()['defaultReplicaSet']['topology'].values() if cluster_member['mode'] == 'R/W'])[0]",
            "shell.connect(f'{cluster_admin_user}:{cluster_admin_password}@{primary_address}')",
            "session.run_sql(\"SELECT get_lock('remove_instance', -1);\")",
            "cluster = dba.get_cluster(f'{cluster.name}')",
            "number_cluster_members = len(cluster.describe()['defaultReplicaSet']['topology'])",
            "cluster.remove_instance(f'{cluster_admin_user}@{remove_instance_address}', remove_instance_options) if number_cluster_members > 1 else cluster.dissolve(dissolve_cluster_options)",
            "session.run_sql(\"SELECT release_lock('remove_instance')\")",
        )

        self.mysql.remove_instance("127.0.0.2")

        _run_mysqlsh_script.assert_called_once_with("\n".join(expected_commands))

    @patch("mysqlsh_helpers.MySQL._run_mysqlsh_script")
    def test_remove_instance_exceptions(self, _run_mysqlsh_script):
        """Test an exception while calling the remove_instance() method."""
        _run_mysqlsh_script.side_effect = subprocess.CalledProcessError(cmd="mock", returncode=127)

        # disable the tenacity retry
        self.mysql.remove_instance.retry.wait = tenacity.wait_none()

        with self.assertRaises(MySQLRemoveInstanceDBConnectionError):
            self.mysql.remove_instance("127.0.0.2")
