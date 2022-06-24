# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit test for MySQL shared library."""

import unittest
from unittest.mock import call, patch

import tenacity
from charms.mysql.v0.mysql import (
    MySQLAddInstanceToClusterError,
    MySQLBase,
    MySQLCheckUserExistenceError,
    MySQLClientError,
    MySQLConfigureInstanceError,
    MySQLConfigureMySQLUsersError,
    MySQLConfigureRouterUserError,
    MySQLCreateApplicationDatabaseAndScopedUserError,
    MySQLCreateClusterError,
    MySQLDeleteUsersForUnitError,
    MySQLInitializeJujuOperationsTableError,
    MySQLRemoveInstanceError,
    MySQLRemoveInstanceRetryError,
)


class TestMySQLBase(unittest.TestCase):
    # Patch abstract methods so it's
    # possible to instantiate abstract class.
    @patch.multiple(MySQLBase, __abstractmethods__=set())
    def setUp(self):
        self.mysql = MySQLBase(
            "127.0.0.1",
            "test_cluster",
            "password",
            "serverconfig",
            "serverconfigpassword",
            "clusteradmin",
            "clusteradminpassword",
        )

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlcli_script")
    def test_configure_mysql_users(self, _run_mysqlcli_script):
        """Test successful configuration of MySQL users."""
        _run_mysqlcli_script.return_value = b""

        _expected_create_root_user_commands = "; ".join(
            (
                "CREATE USER 'root'@'%' IDENTIFIED BY 'password'",
                "GRANT ALL ON *.* TO 'root'@'%' WITH GRANT OPTION",
            )
        )

        _expected_configure_user_commands = "; ".join(
            (
                "CREATE USER 'serverconfig'@'%' IDENTIFIED BY 'serverconfigpassword'",
                "GRANT ALL ON *.* TO 'serverconfig'@'%' WITH GRANT OPTION",
                "UPDATE mysql.user SET authentication_string=null WHERE User='root' and Host='localhost'",
                "ALTER USER 'root'@'localhost' IDENTIFIED BY 'password'",
                "REVOKE SYSTEM_USER, SYSTEM_VARIABLES_ADMIN, SUPER, REPLICATION_SLAVE_ADMIN, GROUP_REPLICATION_ADMIN, BINLOG_ADMIN, SET_USER_ID, ENCRYPTION_KEY_ADMIN, VERSION_TOKEN_ADMIN, CONNECTION_ADMIN ON *.* FROM root@'%'",
                "REVOKE SYSTEM_USER, SYSTEM_VARIABLES_ADMIN, SUPER, REPLICATION_SLAVE_ADMIN, GROUP_REPLICATION_ADMIN, BINLOG_ADMIN, SET_USER_ID, ENCRYPTION_KEY_ADMIN, VERSION_TOKEN_ADMIN, CONNECTION_ADMIN ON *.* FROM root@localhost",
                "FLUSH PRIVILEGES",
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

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlcli_script")
    def test_configure_mysql_users_fail(self, _run_mysqlcli_script):
        """Test failure to configure the MySQL users."""
        _run_mysqlcli_script.side_effect = MySQLClientError("Error on subprocess")

        with self.assertRaises(MySQLConfigureMySQLUsersError):
            self.mysql.configure_mysql_users()

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlcli_script")
    def test_does_mysql_user_exist(self, _run_mysqlcli_script):
        """Test successful execution of does_mysql_user_exist."""
        # Test passing in a custom hostname
        user_existence_command = (
            "select if((select count(*) from mysql.user where user = 'test_username' and host = '1.1.1.1'), 'USER_EXISTS', 'USER_DOES_NOT_EXIST') as ''",
        )

        self.mysql.does_mysql_user_exist("test_username", "1.1.1.1")
        _run_mysqlcli_script.assert_called_once_with("\n".join(user_existence_command))

        # Reset the mock
        _run_mysqlcli_script.reset_mock()

        # Test default hostname
        user_existence_command = (
            "select if((select count(*) from mysql.user where user = 'test_username' and host = '1.1.1.2'), 'USER_EXISTS', 'USER_DOES_NOT_EXIST') as ''",
        )

        self.mysql.does_mysql_user_exist("test_username", "1.1.1.2")
        _run_mysqlcli_script.assert_called_once_with("\n".join(user_existence_command))

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlcli_script")
    def test_does_mysql_user_exist_failure(self, _run_mysqlcli_script):
        """Test failure in execution of does_mysql_user_exist."""
        _run_mysqlcli_script.side_effect = MySQLClientError("Error on subprocess")

        with self.assertRaises(MySQLCheckUserExistenceError):
            self.mysql.does_mysql_user_exist("test_username", "1.1.1.1")

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlcli_script")
    def test_configure_mysqlrouter_user(self, _run_mysqlcli_script):
        """Test the successful execution of configure_mysqlrouter_user."""
        _run_mysqlcli_script.return_value = b""

        _expected_create_mysqlrouter_user_commands = "; ".join(
            (
                "CREATE USER 'test_username'@'1.1.1.1' IDENTIFIED BY 'test_password' ATTRIBUTE '{\"unit_name\": \"app/0\"}'",
            )
        )

        _expected_mysqlrouter_user_grant_commands = "; ".join(
            (
                "GRANT CREATE USER ON *.* TO 'test_username'@'1.1.1.1' WITH GRANT OPTION",
                "GRANT SELECT, INSERT, UPDATE, DELETE, EXECUTE ON mysql_innodb_cluster_metadata.* TO 'test_username'@'1.1.1.1'",
                "GRANT SELECT ON mysql.user TO 'test_username'@'1.1.1.1'",
                "GRANT SELECT ON performance_schema.replication_group_members TO 'test_username'@'1.1.1.1'",
                "GRANT SELECT ON performance_schema.replication_group_member_stats TO 'test_username'@'1.1.1.1'",
                "GRANT SELECT ON performance_schema.global_variables TO 'test_username'@'1.1.1.1'",
            )
        )

        self.mysql.configure_mysqlrouter_user("test_username", "test_password", "1.1.1.1", "app/0")

        self.assertEqual(_run_mysqlcli_script.call_count, 2)

        self.assertEqual(
            sorted(_run_mysqlcli_script.mock_calls),
            sorted(
                [
                    call(_expected_create_mysqlrouter_user_commands),
                    call(_expected_mysqlrouter_user_grant_commands),
                ]
            ),
        )

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlcli_script")
    def test_configure_mysqlrouter_user_failure(self, _run_mysqlcli_script):
        """Test failure to configure the MySQLRouter user."""
        _run_mysqlcli_script.side_effect = MySQLClientError("Error on subprocess")

        with self.assertRaises(MySQLConfigureRouterUserError):
            self.mysql.configure_mysqlrouter_user(
                "test_username", "test_password", "1.1.1.1", "app/0"
            )

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlcli_script")
    def test_create_application_database_and_scoped_user(self, _run_mysqlcli_script):
        """Test the successful execution of create_application_database_and_scoped_user."""
        _run_mysqlcli_script.return_value = b""

        _expected_create_database_commands = "; ".join(
            ("CREATE DATABASE IF NOT EXISTS test_database",)
        )

        _expected_create_scoped_user_commands = "; ".join(
            (
                "CREATE USER 'test_username'@'1.1.1.1' IDENTIFIED BY 'test_password' ATTRIBUTE '{\"unit_name\": \"app/0\"}'",
                "GRANT USAGE ON *.* TO 'test_username'@`1.1.1.1`",
                "GRANT ALL PRIVILEGES ON `test_database`.* TO `test_username`@`1.1.1.1`",
            )
        )

        self.mysql.create_application_database_and_scoped_user(
            "test_database", "test_username", "test_password", "1.1.1.1", "app/0"
        )

        self.assertEqual(_run_mysqlcli_script.call_count, 2)

        self.assertEqual(
            sorted(_run_mysqlcli_script.mock_calls),
            sorted(
                [
                    call(_expected_create_database_commands),
                    call(_expected_create_scoped_user_commands),
                ]
            ),
        )

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlcli_script")
    def test_create_application_database_and_scoped_user_failure(self, _run_mysqlcli_script):
        """Test failure to create application database and scoped user."""
        _run_mysqlcli_script.side_effect = MySQLClientError("Error on subprocess")

        with self.assertRaises(MySQLCreateApplicationDatabaseAndScopedUserError):
            self.mysql.create_application_database_and_scoped_user(
                "test_database", "test_username", "test_password", "1.1.1.1", "app/.0"
            )

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlcli_script")
    def test_delete_users_for_unit(self, _run_mysqlcli_script):
        """Test successful execution of delete_users_for_unit."""
        _run_mysqlcli_script.side_effect = ["test_column\ntest@1.1.1.1\ntest2@1.1.1.2", ""]

        _expected_get_unit_user_commands = "; ".join(
            (
                "SELECT CONCAT(user.user, '@', user.host) FROM mysql.user AS user JOIN information_schema.user_attributes AS attributes ON (user.user = attributes.user AND user.host = attributes.host) WHERE attributes.attribute LIKE '%\"unit_name\": \"app/0\"%'",
            )
        )

        _expected_drop_users_command = "; ".join(
            ("DROP USER IF EXISTS test@1.1.1.1, test2@1.1.1.2",)
        )

        self.mysql.delete_users_for_unit("app/0")

        self.assertEqual(_run_mysqlcli_script.call_count, 2)
        self.assertEqual(
            sorted(_run_mysqlcli_script.mock_calls),
            sorted(
                [
                    call(_expected_get_unit_user_commands),
                    call(_expected_drop_users_command),
                ]
            ),
        )

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlcli_script")
    def test_delete_users_for_unit_failure(self, _run_mysqlcli_script):
        """Test failure to delete users for a unit."""
        _run_mysqlcli_script.side_effect = MySQLClientError("Error on subprocess")

        with self.assertRaises(MySQLDeleteUsersForUnitError):
            self.mysql.delete_users_for_unit("app/0")

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    @patch("charms.mysql.v0.mysql.MySQLBase.wait_until_mysql_connection")
    def test_configure_instance(self, _wait_until_mysql_connection, _run_mysqlsh_script):
        """Test a successful execution of configure_instance."""
        configure_instance_commands = (
            'dba.configure_instance(\'serverconfig:serverconfigpassword@127.0.0.1\', {"clusterAdmin": "clusteradmin", "clusterAdminPassword": "clusteradminpassword", "restart": "true"})',
        )

        self.mysql.configure_instance()

        _run_mysqlsh_script.assert_called_once_with("\n".join(configure_instance_commands))

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    @patch("charms.mysql.v0.mysql.MySQLBase.wait_until_mysql_connection")
    def test_configure_instance_exceptions(
        self, _wait_until_mysql_connection, _run_mysqlsh_script
    ):
        """Test exceptions raise while running configure_instance."""
        # Test an issue with _run_mysqlsh_script
        _run_mysqlsh_script.side_effect = MySQLClientError("Error on subprocess")

        with self.assertRaises(MySQLConfigureInstanceError):
            self.mysql.configure_instance()

        _wait_until_mysql_connection.assert_not_called()

        # Reset mocks
        _run_mysqlsh_script.reset_mock()
        _wait_until_mysql_connection.reset_mock()

        # Test an issue with _wait_until_mysql_connection
        _wait_until_mysql_connection.side_effect = MySQLClientError("Error on subprocess")

        with self.assertRaises(MySQLConfigureInstanceError):
            self.mysql.configure_instance()

        _run_mysqlsh_script.assert_called_once()

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlcli_script")
    def test_initialize_juju_units_operations_table(self, _run_mysqlcli_script):
        """Test a successful initialization of the mysql.juju_units_operations table."""
        expected_initialize_table_commands = (
            "CREATE TABLE mysql.juju_units_operations (task varchar(20), executor varchar(20), status varchar(20), primary key(task))",
            "INSERT INTO mysql.juju_units_operations values ('unit-teardown', '', 'not-started')",
        )

        self.mysql.initialize_juju_units_operations_table()

        _run_mysqlcli_script.assert_called_once_with(
            "; ".join(expected_initialize_table_commands),
            user="serverconfig",
            password="serverconfigpassword",
        )

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlcli_script")
    def test_initialize_juju_units_operations_table_exception(self, _run_mysqlcli_script):
        """Test an exception initialization of the mysql.juju_units_operations table."""
        _run_mysqlcli_script.side_effect = MySQLClientError("Error on subprocess")

        with self.assertRaises(MySQLInitializeJujuOperationsTableError):
            self.mysql.initialize_juju_units_operations_table()

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    def test_create_cluster(self, _run_mysqlsh_script):
        """Test a successful execution of create_cluster."""
        create_cluster_commands = (
            "shell.connect('serverconfig:serverconfigpassword@127.0.0.1')",
            "cluster = dba.create_cluster('test_cluster')",
            "cluster.set_instance_option('127.0.0.1', 'label', 'mysql-0')",
        )

        self.mysql.create_cluster("mysql-0")

        _run_mysqlsh_script.assert_called_once_with("\n".join(create_cluster_commands))

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    def test_create_cluster_exceptions(self, _run_mysqlsh_script):
        """Test exceptions raised while running create_cluster."""
        _run_mysqlsh_script.side_effect = MySQLClientError("Error on subprocess")

        with self.assertRaises(MySQLCreateClusterError):
            self.mysql.create_cluster("mysql-0")

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    def test_add_instance_to_cluster(self, _run_mysqlsh_script):
        """Test a successful execution of create_cluster."""
        add_instance_to_cluster_commands = (
            "shell.connect('clusteradmin:clusteradminpassword@127.0.0.1')",
            "cluster = dba.get_cluster('test_cluster')",
            'cluster.add_instance(\'clusteradmin@127.0.0.2\', {"password": "clusteradminpassword", "label": "mysql-1", "recoveryMethod": "auto"})',
        )

        self.mysql.add_instance_to_cluster("127.0.0.2", "mysql-1")

        _run_mysqlsh_script.assert_called_once_with("\n".join(add_instance_to_cluster_commands))

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    def test_add_instance_to_cluster_exception(self, _run_mysqlsh_script):
        """Test exceptions raised while running add_instance_to_cluster."""
        _run_mysqlsh_script.side_effect = MySQLClientError("Error on subprocess")

        with self.assertRaises(MySQLAddInstanceToClusterError):
            self.mysql.add_instance_to_cluster("127.0.0.2", "mysql-1")

    @patch(
        "charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script", return_value="INSTANCE_CONFIGURED"
    )
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

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    def test_is_instance_configured_for_innodb_exceptions(self, _run_mysqlsh_script):
        """Test an exception while calling the is_instance_configured_for_innodb method."""
        _run_mysqlsh_script.side_effect = MySQLClientError("Error on subprocess")

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

    @patch("charms.mysql.v0.mysql.MySQLBase.get_cluster_primary_address")
    @patch("charms.mysql.v0.mysql.MySQLBase._acquire_lock")
    @patch("charms.mysql.v0.mysql.MySQLBase._get_cluster_member_addresses")
    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    @patch("charms.mysql.v0.mysql.MySQLBase._release_lock")
    def test_remove_primary_instance(
        self,
        _release_lock,
        _run_mysqlsh_script,
        _get_cluster_member_addresses,
        _acquire_lock,
        _get_cluster_primary_address,
    ):
        """Test with no exceptions while running the remove_instance() method."""
        _get_cluster_primary_address.side_effect = ["1.1.1.1", "2.2.2.2"]
        _acquire_lock.return_value = True
        _get_cluster_member_addresses.return_value = ("2.2.2.2", True)

        self.mysql.remove_instance("mysql-0")

        expected_remove_instance_commands = "\n".join(
            [
                "shell.connect('clusteradmin:clusteradminpassword@127.0.0.1')",
                "cluster = dba.get_cluster('test_cluster')",
                "number_cluster_members = len(cluster.status()['defaultReplicaSet']['topology'])",
                'cluster.remove_instance(\'clusteradmin@127.0.0.1\', {"password": "clusteradminpassword", "force": "true"}) if number_cluster_members > 1 else cluster.dissolve({"force": "true"})',
            ]
        )

        self.assertEqual(_get_cluster_primary_address.call_count, 2)
        _acquire_lock.assert_called_once_with("1.1.1.1", "mysql-0", "unit-teardown")
        _get_cluster_member_addresses.assert_called_once_with(exclude_unit_labels=["mysql-0"])
        _run_mysqlsh_script.assert_called_once_with(expected_remove_instance_commands)
        _release_lock.assert_called_once_with("2.2.2.2", "mysql-0", "unit-teardown")

    @patch("charms.mysql.v0.mysql.MySQLBase.get_cluster_primary_address")
    @patch("charms.mysql.v0.mysql.MySQLBase._acquire_lock")
    @patch("charms.mysql.v0.mysql.MySQLBase._get_cluster_member_addresses")
    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    @patch("charms.mysql.v0.mysql.MySQLBase._release_lock")
    def test_remove_primary_instance_error_acquiring_lock(
        self,
        _release_lock,
        _run_mysqlsh_script,
        _get_cluster_member_addresses,
        _acquire_lock,
        _get_cluster_primary_address,
    ):
        """Test an issue acquiring lock while running the remove_instance() method."""
        _get_cluster_primary_address.side_effect = ["1.1.1.1", "2.2.2.2"]
        _acquire_lock.return_value = False

        # disable tenacity retry
        self.mysql.remove_instance.retry.retry = tenacity.retry_if_not_result(lambda x: True)

        with self.assertRaises(MySQLRemoveInstanceRetryError):
            self.mysql.remove_instance("mysql-0")

        self.assertEqual(_get_cluster_primary_address.call_count, 1)
        _acquire_lock.assert_called_once_with("1.1.1.1", "mysql-0", "unit-teardown")
        _get_cluster_member_addresses.assert_not_called()
        _run_mysqlsh_script.assert_not_called()
        _release_lock.assert_not_called()

    @patch("charms.mysql.v0.mysql.MySQLBase.get_cluster_primary_address")
    @patch("charms.mysql.v0.mysql.MySQLBase._acquire_lock")
    @patch("charms.mysql.v0.mysql.MySQLBase._get_cluster_member_addresses")
    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    @patch("charms.mysql.v0.mysql.MySQLBase._release_lock")
    def test_remove_primary_instance_error_releasing_lock(
        self,
        _release_lock,
        _run_mysqlsh_script,
        _get_cluster_member_addresses,
        _acquire_lock,
        _get_cluster_primary_address,
    ):
        """Test an issue releasing locks while running the remove_instance() method."""
        _get_cluster_primary_address.side_effect = ["1.1.1.1", "2.2.2.2"]
        _acquire_lock.return_value = True
        _get_cluster_member_addresses.return_value = ("2.2.2.2", True)
        _release_lock.side_effect = MySQLClientError("Error on subprocess")

        with self.assertRaises(MySQLRemoveInstanceError):
            self.mysql.remove_instance("mysql-0")

        expected_remove_instance_commands = "\n".join(
            [
                "shell.connect('clusteradmin:clusteradminpassword@127.0.0.1')",
                "cluster = dba.get_cluster('test_cluster')",
                "number_cluster_members = len(cluster.status()['defaultReplicaSet']['topology'])",
                'cluster.remove_instance(\'clusteradmin@127.0.0.1\', {"password": "clusteradminpassword", "force": "true"}) if number_cluster_members > 1 else cluster.dissolve({"force": "true"})',
            ]
        )

        self.assertEqual(_get_cluster_primary_address.call_count, 2)
        _acquire_lock.assert_called_once_with("1.1.1.1", "mysql-0", "unit-teardown")
        _get_cluster_member_addresses.assert_called_once_with(exclude_unit_labels=["mysql-0"])
        _run_mysqlsh_script.assert_called_once_with(expected_remove_instance_commands)
        _release_lock.assert_called_once_with("2.2.2.2", "mysql-0", "unit-teardown")

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    def test_acquire_lock(self, _run_mysqlsh_script):
        """Test a successful execution of _acquire_lock()."""
        _run_mysqlsh_script.return_value = "<ACQUIRED_LOCK>1</ACQUIRED_LOCK>"

        acquired_lock = self.mysql._acquire_lock("1.1.1.1", "mysql-0", "unit-teardown")

        self.assertTrue(acquired_lock)

        expected_acquire_lock_commands = "\n".join(
            [
                "shell.connect('clusteradmin:clusteradminpassword@1.1.1.1')",
                "session.run_sql(\"UPDATE mysql.juju_units_operations SET executor='mysql-0', status='in-progress' WHERE task='unit-teardown' AND executor='';\")",
                "acquired_lock = session.run_sql(\"SELECT count(*) FROM mysql.juju_units_operations WHERE task='unit-teardown' AND executor='mysql-0';\").fetch_one()[0]",
                "print(f'<ACQUIRED_LOCK>{acquired_lock}</ACQUIRED_LOCK>')",
            ]
        )
        _run_mysqlsh_script.assert_called_once_with(expected_acquire_lock_commands)

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    def test_unable_to_acquire_lock(self, _run_mysqlsh_script):
        """Test a successful execution of _acquire_lock() but failure to acquire lock."""
        _run_mysqlsh_script.return_value = "<ACQUIRED_LOCK>0</ACQUIRED_LOCK>"

        acquired_lock = self.mysql._acquire_lock("1.1.1.1", "mysql-0", "unit-teardown")

        self.assertFalse(acquired_lock)

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    def test_issue_with_acquire_lock(self, _run_mysqlsh_script):
        """Test an issue while executing _acquire_lock()."""
        _run_mysqlsh_script.return_value = ""

        acquired_lock = self.mysql._acquire_lock("1.1.1.1", "mysql-0", "unit-teardown")

        self.assertFalse(acquired_lock)

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    def test_release_lock(self, _run_mysqlsh_script):
        """Test a successful execution of _acquire_lock()."""
        self.mysql._release_lock("2.2.2.2", "mysql-0", "unit-teardown")

        expected_release_lock_commands = "\n".join(
            [
                "shell.connect('clusteradmin:clusteradminpassword@2.2.2.2')",
                "session.run_sql(\"UPDATE mysql.juju_units_operations SET executor='', status='not-started' WHERE task='unit-teardown' AND executor='mysql-0';\")",
            ]
        )
        _run_mysqlsh_script.assert_called_once_with(expected_release_lock_commands)

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    def test_get_cluster_member_addresses(self, _run_mysqlsh_script):
        """Test a successful execution of _get_cluster_member_addresses()."""
        _run_mysqlsh_script.return_value = "<MEMBER_ADDRESSES>1.1.1.1,2.2.2.2</MEMBER_ADDRESSES>"

        cluster_members, valid = self.mysql._get_cluster_member_addresses(
            exclude_unit_labels=["mysql-0"]
        )

        self.assertEqual(cluster_members, ["1.1.1.1", "2.2.2.2"])
        self.assertTrue(valid)

        expected_commands = "\n".join(
            [
                "shell.connect('clusteradmin:clusteradminpassword@127.0.0.1')",
                "cluster = dba.get_cluster('test_cluster')",
                "member_addresses = ','.join([member['address'] for label, member in cluster.status()['defaultReplicaSet']['topology'].items() if label not in ['mysql-0']])",
                "print(f'<MEMBER_ADDRESSES>{member_addresses}</MEMBER_ADDRESSES>')",
            ]
        )
        _run_mysqlsh_script.assert_called_once_with(expected_commands)

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    def test_empty_get_cluster_member_addresses(self, _run_mysqlsh_script):
        """Test successful execution of _get_cluster_member_addresses() with empty return value."""
        _run_mysqlsh_script.return_value = "<MEMBER_ADDRESSES></MEMBER_ADDRESSES>"

        cluster_members, valid = self.mysql._get_cluster_member_addresses(
            exclude_unit_labels=["mysql-0"]
        )

        self.assertEqual(cluster_members, [])
        self.assertTrue(valid)

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    def test_error_get_cluster_member_addresses(self, _run_mysqlsh_script):
        """Test an issue executing _get_cluster_member_addresses()."""
        _run_mysqlsh_script.return_value = ""

        cluster_members, valid = self.mysql._get_cluster_member_addresses(
            exclude_unit_labels=["mysql-0"]
        )

        self.assertEqual(cluster_members, [])
        self.assertFalse(valid)

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    def test_get_cluster_primary_address(self, _run_mysqlsh_script):
        """Test a successful execution of _get_cluster_primary_address()."""
        _run_mysqlsh_script.return_value = "<PRIMARY_ADDRESS>1.1.1.1</PRIMARY_ADDRESS>"

        primary_address = self.mysql.get_cluster_primary_address()

        self.assertEqual(primary_address, "1.1.1.1")

        expected_commands = "\n".join(
            [
                "shell.connect('clusteradmin:clusteradminpassword@127.0.0.1')",
                "cluster = dba.get_cluster('test_cluster')",
                "primary_address = sorted([cluster_member['address'] for cluster_member in cluster.status()['defaultReplicaSet']['topology'].values() if cluster_member['mode'] == 'R/W'])[0]",
                "print(f'<PRIMARY_ADDRESS>{primary_address}</PRIMARY_ADDRESS>')",
            ]
        )
        _run_mysqlsh_script.assert_called_once_with(expected_commands)

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    def test_no_match_cluster_primary_address_with_connect_instance_address(
        self, _run_mysqlsh_script
    ):
        """Test an issue executing _get_cluster_primary_address()."""
        _run_mysqlsh_script.return_value = ""

        primary_address = self.mysql.get_cluster_primary_address(
            connect_instance_address="127.0.0.2"
        )

        self.assertIsNone(primary_address)

        expected_commands = "\n".join(
            [
                "shell.connect('clusteradmin:clusteradminpassword@127.0.0.2')",
                "cluster = dba.get_cluster('test_cluster')",
                "primary_address = sorted([cluster_member['address'] for cluster_member in cluster.status()['defaultReplicaSet']['topology'].values() if cluster_member['mode'] == 'R/W'])[0]",
                "print(f'<PRIMARY_ADDRESS>{primary_address}</PRIMARY_ADDRESS>')",
            ]
        )
        _run_mysqlsh_script.assert_called_once_with(expected_commands)

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    def test_is_instance_in_cluster(self, _run_mysqlsh_script):
        """Test a successful execution of is_instance_in_cluster() method."""
        _run_mysqlsh_script.return_value = "ONLINE"

        result = self.mysql.is_instance_in_cluster("mysql-0")
        self.assertTrue(result)

        expected_commands = "\n".join(
            [
                "shell.connect('clusteradmin:clusteradminpassword@127.0.0.1')",
                "cluster = dba.get_cluster('test_cluster')",
                "print(cluster.status()['defaultReplicaSet']['topology'].get('mysql-0', {}).get('status', 'NOT_A_MEMBER'))",
            ]
        )
        _run_mysqlsh_script.assert_called_once_with(expected_commands)

        _run_mysqlsh_script.return_value = "NOT_A_MEMBER"

        result = self.mysql.is_instance_in_cluster("mysql-0")
        self.assertFalse(result)

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    def test_is_instance_in_cluster_exception(self, _run_mysqlsh_script):
        """Test an exception executing is_instance_in_cluster() method."""
        _run_mysqlsh_script.side_effect = MySQLClientError("Error on subprocess")

        result = self.mysql.is_instance_in_cluster("mysql-0")
        self.assertFalse(result)
