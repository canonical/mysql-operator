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
    MySQLInitializeJujuOperationsTableError,
    MySQLRemoveInstanceError,
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

    @patch("mysqlsh_helpers.MySQL._run_mysqlcli_script")
    def test_initialize_juju_units_operations_table(self, _run_mysqlcli_script):
        """Test a successful initialization of the mysql.juju_units_operations table."""
        expected_initialize_table_commands = (
            "CREATE TABLE mysql.juju_units_operations (task varchar(20), executor varchar(20), status varchar(20), primary key(task));",
            "INSERT INTO mysql.juju_units_operations values ('unit-teardown', '', 'not-started');",
        )

        self.mysql.initialize_juju_units_operations_table()

        _run_mysqlcli_script.assert_called_once_with(
            " ".join(expected_initialize_table_commands),
            user="serverconfig",
            password="serverconfigpassword",
        )

    @patch("mysqlsh_helpers.MySQL._run_mysqlcli_script")
    def test_initialize_juju_units_operations_table_exception(self, _run_mysqlcli_script):
        """Test an exception initialization of the mysql.juju_units_operations table."""
        _run_mysqlcli_script.side_effect = subprocess.CalledProcessError(
            cmd="mock", returncode=127
        )

        with self.assertRaises(MySQLInitializeJujuOperationsTableError):
            self.mysql.initialize_juju_units_operations_table()

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
            "cluster = dba.get_cluster('test_cluster')",
            'cluster.add_instance(\'clusteradmin@127.0.0.2\', {"password": "clusteradminpassword", "label": "mysql-1", "recoveryMethod": "auto"})',
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

    @patch("mysqlsh_helpers.MySQL._get_cluster_primary_address")
    @patch("mysqlsh_helpers.MySQL._run_mysqlsh_script")
    @patch("mysqlsh_helpers.MySQL._get_cluster_member_addresses")
    def test_remove_primary_instance(
        self, _get_cluster_member_addresses, _run_mysqlsh_script, _get_cluster_primary_address
    ):
        """Test with no exceptions while running the remove_instance() method."""
        _get_cluster_primary_address.side_effect = ["1.1.1.1", "2.2.2.2"]
        _run_mysqlsh_script.side_effect = ["<ACQUIRED_LOCK>1</ACQUIRED_LOCK>", "", ""]
        _get_cluster_member_addresses.return_value = ("2.2.2.2", True)

        self.mysql.remove_instance("mysql-0")

        self.assertEqual(_get_cluster_primary_address.call_count, 2)
        _get_cluster_member_addresses.assert_called_once_with(exclude_unit_labels=["mysql-0"])

        expected_acquire_lock_commands = "\n".join(
            [
                "shell.connect('clusteradmin:clusteradminpassword@1.1.1.1')",
                "session.run_sql(\"UPDATE mysql.juju_units_operations SET executor='mysql-0', status='in-progress' WHERE task='unit-teardown' AND executor='';\")",
                "acquired_lock = session.run_sql(\"SELECT count(*) FROM mysql.juju_units_operations WHERE task='unit-teardown' AND executor='mysql-0';\").fetch_one()[0]",
                "print(f'<ACQUIRED_LOCK>{acquired_lock}</ACQUIRED_LOCK>')",
            ]
        )

        expected_remove_instance_commands = "\n".join(
            [
                "shell.connect('clusteradmin:clusteradminpassword@127.0.0.1')",
                "cluster = dba.get_cluster('test_cluster')",
                "number_cluster_members = len(cluster.status()['defaultReplicaSet']['topology'])",
                'cluster.remove_instance(\'clusteradmin@127.0.0.1\', {"password": "clusteradminpassword", "force": "true"}) if number_cluster_members > 1 else cluster.dissolve({"force": "true"})',
            ]
        )

        expected_release_lock_commands = "\n".join(
            [
                "shell.connect('clusteradmin:clusteradminpassword@2.2.2.2')",
                "session.run_sql(\"UPDATE mysql.juju_units_operations SET executor='', status='not-started' WHERE task='unit-teardown' AND executor='mysql-0';\")",
            ]
        )

        self.assertEqual(
            sorted(_run_mysqlsh_script.mock_calls),
            sorted(
                [
                    call(expected_acquire_lock_commands),
                    call(expected_remove_instance_commands),
                    call(expected_release_lock_commands),
                ]
            ),
        )

    @patch("mysqlsh_helpers.MySQL._get_cluster_primary_address")
    @patch("mysqlsh_helpers.MySQL._run_mysqlsh_script")
    @patch("mysqlsh_helpers.MySQL._get_cluster_member_addresses")
    def test_remove_instance_failed_to_acquire_lock(
        self, _get_cluster_member_addresses, _run_mysqlsh_script, _get_cluster_primary_address
    ):
        """Test failure to acquire lock while running the remove_instance() method."""
        _get_cluster_primary_address.side_effect = ["1.1.1.1", "2.2.2.2"]
        _run_mysqlsh_script.side_effect = ["<ACQUIRED_LOCK>0</ACQUIRED_LOCK>", "", ""]
        _get_cluster_member_addresses.return_value = ("2.2.2.2", True)

        # disable tenacity retry
        self.mysql.remove_instance.retry.retry = tenacity.retry_if_not_result(lambda x: True)

        with self.assertRaises(MySQLRemoveInstanceError):
            self.mysql.remove_instance("mysql-0")

    @patch("mysqlsh_helpers.MySQL._get_cluster_primary_address")
    @patch("mysqlsh_helpers.MySQL._run_mysqlsh_script")
    @patch("mysqlsh_helpers.MySQL._get_cluster_member_addresses")
    def test_remove_instance_subprocess_execption(
        self, _get_cluster_member_addresses, _run_mysqlsh_script, _get_cluster_primary_address
    ):
        """Test CalledProcessError while acquiring lock running the remove_instance() method."""
        _get_cluster_primary_address.side_effect = ["1.1.1.1", "2.2.2.2"]
        _run_mysqlsh_script.side_effect = subprocess.CalledProcessError(cmd="mock", returncode=127)
        _get_cluster_member_addresses.return_value = ("2.2.2.2", True)

        # disable tenacity retry
        self.mysql.remove_instance.retry.retry = tenacity.retry_if_not_result(lambda x: True)

        with self.assertRaises(MySQLRemoveInstanceError):
            self.mysql.remove_instance("mysql-0")
