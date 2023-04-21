# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit test for MySQL shared library."""

import unittest
from unittest.mock import call, patch

import tenacity
from charms.mysql.v0.mysql import (
    Error,
    MySQLAddInstanceToClusterError,
    MySQLBase,
    MySQLCheckUserExistenceError,
    MySQLClientError,
    MySQLConfigureInstanceError,
    MySQLConfigureMySQLUsersError,
    MySQLConfigureRouterUserError,
    MySQLCreateApplicationDatabaseAndScopedUserError,
    MySQLCreateClusterError,
    MySQLDeleteTempBackupDirectoryError,
    MySQLDeleteTempRestoreDirectoryError,
    MySQLDeleteUserForRelationError,
    MySQLDeleteUsersForUnitError,
    MySQLEmptyDataDirectoryError,
    MySQLExecError,
    MySQLExecuteBackupCommandsError,
    MySQLGetInnoDBBufferPoolParametersError,
    MySQLInitializeJujuOperationsTableError,
    MySQLOfflineModeAndHiddenInstanceExistsError,
    MySQLPrepareBackupForRestoreError,
    MySQLRemoveInstanceError,
    MySQLRemoveInstanceRetryError,
    MySQLRestoreBackupError,
    MySQLRetrieveBackupWithXBCloudError,
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
            "monitoring",
            "monitoringpassword",
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
                "CREATE USER 'monitoring'@'%' IDENTIFIED BY 'monitoringpassword' WITH MAX_USER_CONNECTIONS 3",
                "GRANT SYSTEM_USER, SELECT, PROCESS, SUPER, REPLICATION CLIENT, RELOAD ON *.* TO 'monitoring'@'%'",
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
                    call(_expected_create_root_user_commands, password="password"),
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
        _run_mysqlcli_script.assert_called_once_with(
            "\n".join(user_existence_command), user="serverconfig", password="serverconfigpassword"
        )

        # Reset the mock
        _run_mysqlcli_script.reset_mock()

        # Test default hostname
        user_existence_command = (
            "select if((select count(*) from mysql.user where user = 'test_username' and host = '1.1.1.2'), 'USER_EXISTS', 'USER_DOES_NOT_EXIST') as ''",
        )

        self.mysql.does_mysql_user_exist("test_username", "1.1.1.2")
        _run_mysqlcli_script.assert_called_once_with(
            "\n".join(user_existence_command), user="serverconfig", password="serverconfigpassword"
        )

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlcli_script")
    def test_does_mysql_user_exist_failure(self, _run_mysqlcli_script):
        """Test failure in execution of does_mysql_user_exist."""
        _run_mysqlcli_script.side_effect = MySQLClientError("Error on subprocess")

        with self.assertRaises(MySQLCheckUserExistenceError):
            self.mysql.does_mysql_user_exist("test_username", "1.1.1.1")

    @patch("charms.mysql.v0.mysql.MySQLBase.get_cluster_primary_address")
    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    def test_configure_mysqlrouter_user(self, _run_mysqlsh_script, _get_cluster_primary_address):
        """Test the successful execution of configure_mysqlrouter_user."""
        _get_cluster_primary_address.return_value = "2.2.2.2"
        _run_mysqlsh_script.return_value = ""

        _expected_create_mysqlrouter_user_commands = "\n".join(
            (
                "shell.connect('serverconfig:serverconfigpassword@2.2.2.2')",
                "session.run_sql(\"CREATE USER 'test_username'@'1.1.1.1' IDENTIFIED BY 'test_password' ATTRIBUTE '{\\\"unit_name\\\": \\\"app/0\\\"}';\")",
            )
        )

        _expected_mysqlrouter_user_grant_commands = "\n".join(
            (
                "shell.connect('serverconfig:serverconfigpassword@2.2.2.2')",
                "session.run_sql(\"GRANT CREATE USER ON *.* TO 'test_username'@'1.1.1.1' WITH GRANT OPTION;\")",
                "session.run_sql(\"GRANT SELECT, INSERT, UPDATE, DELETE, EXECUTE ON mysql_innodb_cluster_metadata.* TO 'test_username'@'1.1.1.1';\")",
                "session.run_sql(\"GRANT SELECT ON mysql.user TO 'test_username'@'1.1.1.1';\")",
                "session.run_sql(\"GRANT SELECT ON performance_schema.replication_group_members TO 'test_username'@'1.1.1.1';\")",
                "session.run_sql(\"GRANT SELECT ON performance_schema.replication_group_member_stats TO 'test_username'@'1.1.1.1';\")",
                "session.run_sql(\"GRANT SELECT ON performance_schema.global_variables TO 'test_username'@'1.1.1.1';\")",
            )
        )

        self.mysql.configure_mysqlrouter_user("test_username", "test_password", "1.1.1.1", "app/0")

        self.assertEqual(_run_mysqlsh_script.call_count, 2)

        self.assertEqual(
            sorted(_run_mysqlsh_script.mock_calls),
            sorted(
                [
                    call(_expected_create_mysqlrouter_user_commands),
                    call(_expected_mysqlrouter_user_grant_commands),
                ]
            ),
        )

    @patch("charms.mysql.v0.mysql.MySQLBase.get_cluster_primary_address")
    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    def test_configure_mysqlrouter_user_failure(
        self, _run_mysqlsh_script, _get_cluster_primary_address
    ):
        """Test failure to configure the MySQLRouter user."""
        _get_cluster_primary_address.return_value = "2.2.2.2"
        _run_mysqlsh_script.side_effect = MySQLClientError("Error on subprocess")

        with self.assertRaises(MySQLConfigureRouterUserError):
            self.mysql.configure_mysqlrouter_user(
                "test_username", "test_password", "1.1.1.1", "app/0"
            )

    @patch("charms.mysql.v0.mysql.MySQLBase.get_cluster_primary_address")
    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    def test_create_application_database_and_scoped_user(
        self, _run_mysqlsh_script, _get_cluster_primary_address
    ):
        """Test the successful execution of create_application_database_and_scoped_user."""
        _get_cluster_primary_address.return_value = "2.2.2.2"
        _run_mysqlsh_script.return_value = ""

        _expected_create_database_commands = "\n".join(
            (
                "shell.connect('serverconfig:serverconfigpassword@2.2.2.2')",
                'session.run_sql("CREATE DATABASE IF NOT EXISTS `test-database`;")',
            )
        )

        _expected_create_scoped_user_commands = "\n".join(
            (
                "shell.connect('serverconfig:serverconfigpassword@2.2.2.2')",
                'session.run_sql("CREATE USER `test-username`@`1.1.1.1` IDENTIFIED BY \'test-password\' ATTRIBUTE \'{\\"unit_name\\": \\"app/0\\"}\';")',
                'session.run_sql("GRANT USAGE ON *.* TO `test-username`@`1.1.1.1`;")',
                'session.run_sql("GRANT ALL PRIVILEGES ON `test-database`.* TO `test-username`@`1.1.1.1`;")',
            )
        )

        self.mysql.create_application_database_and_scoped_user(
            "test-database", "test-username", "test-password", "1.1.1.1", "app/0"
        )

        self.assertEqual(_run_mysqlsh_script.call_count, 2)

        self.assertEqual(
            sorted(_run_mysqlsh_script.mock_calls),
            sorted(
                [
                    call(_expected_create_database_commands),
                    call(_expected_create_scoped_user_commands),
                ]
            ),
        )

    @patch("charms.mysql.v0.mysql.MySQLBase.get_cluster_primary_address")
    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    def test_create_application_database_and_scoped_user_failure(
        self, _run_mysqlsh_script, _get_cluster_primary_address
    ):
        """Test failure to create application database and scoped user."""
        _get_cluster_primary_address.return_value = "2.2.2.2"
        _run_mysqlsh_script.side_effect = MySQLClientError("Error on subprocess")

        with self.assertRaises(MySQLCreateApplicationDatabaseAndScopedUserError):
            self.mysql.create_application_database_and_scoped_user(
                "test_database", "test_username", "test_password", "1.1.1.1", "app/.0"
            )

    @patch(
        "charms.mysql.v0.mysql.MySQLBase._run_mysqlcli_script",
        return_value="test_column\ntest@1.1.1.1\ntest2@1.1.1.2",
    )
    @patch("charms.mysql.v0.mysql.MySQLBase.get_cluster_primary_address", return_value="2.2.2.2")
    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    def test_delete_users_for_unit(
        self, _run_mysqlsh_script, _get_cluster_primary_address, _run_mysqlcli_script
    ):
        """Test successful execution of delete_users_for_unit."""
        _expected_get_unit_user_commands = "; ".join(
            (
                "SELECT CONCAT(user.user, '@', user.host) FROM mysql.user AS user JOIN information_schema.user_attributes AS attributes ON (user.user = attributes.user AND user.host = attributes.host) WHERE attributes.attribute LIKE '%\"unit_name\": \"app/0\"%'",
            )
        )

        _expected_drop_users_command = "\n".join(
            (
                "shell.connect('serverconfig:serverconfigpassword@2.2.2.2')",
                "session.run_sql(\"DROP USER IF EXISTS 'test'@'1.1.1.1', 'test2'@'1.1.1.2';\")",
            )
        )

        self.mysql.delete_users_for_unit("app/0")

        _run_mysqlcli_script.assert_called_once_with(
            _expected_get_unit_user_commands,
            user="serverconfig",
            password="serverconfigpassword",
        )
        _get_cluster_primary_address.assert_called_once()
        _run_mysqlsh_script.assert_called_once_with(_expected_drop_users_command)

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
            'dba.configure_instance(\'serverconfig:serverconfigpassword@127.0.0.1\', {"restart": "true", "clusterAdmin": "clusteradmin", "clusterAdminPassword": "clusteradminpassword"})',
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
            "CREATE TABLE IF NOT EXISTS mysql.juju_units_operations (task varchar(20), executor varchar(20), "
            "status varchar(20), primary key(task))",
            "INSERT INTO mysql.juju_units_operations values ('unit-teardown', '', 'not-started') ON DUPLICATE KEY UPDATE executor = '', status = 'not-started'",
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
            'cluster = dba.create_cluster(\'test_cluster\', {"communicationStack": "MySQL"})',
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
            "cluster.add_instance('clusteradmin@127.0.0.2', {\"password\": "
            '"clusteradminpassword", "label": "mysql-1", "recoveryMethod": "auto"})',
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
        self.mysql.remove_instance.retry.retry = tenacity.retry_if_not_result(lambda _: True)

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

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    def test_get_cluster_status(self, _run_mysqlsh_script):
        """Test a successful execution of get_cluster_status() method."""
        _run_mysqlsh_script.return_value = '{"status":"online"}'

        self.mysql.get_cluster_status()
        expected_commands = "\n".join(
            (
                "shell.connect('clusteradmin:clusteradminpassword@127.0.0.1')",
                "cluster = dba.get_cluster('test_cluster')",
                "print(cluster.status())",
            )
        )
        _run_mysqlsh_script.assert_called_once_with(expected_commands)

    @patch("json.loads")
    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    def test_get_cluster_status_failure(self, _run_mysqlsh_script, _json_loads):
        """Test an exception executing get_cluster_status() method."""
        _run_mysqlsh_script.side_effect = MySQLClientError("Error on subprocess")

        self.mysql.get_cluster_status()
        _json_loads.assert_not_called()

    def test_error(self):
        """Test Error class."""
        error = Error("Error message")

        self.assertEqual(error.__repr__(), "<charms.mysql.v0.mysql.Error ('Error message',)>")
        self.assertEqual(error.name, "<charms.mysql.v0.mysql.Error>")
        self.assertEqual(error.message, "Error message")

    @patch("charms.mysql.v0.mysql.MySQLBase.get_cluster_primary_address", return_value="2.2.2.2")
    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    def test_delete_user_for_relation(self, _run_mysqlsh_script, _get_cluster_primary_address):
        """Test delete_user_for_relation() method."""
        self.mysql.delete_user_for_relation(40)

        expected_commands = "\n".join(
            (
                "shell.connect('serverconfig:serverconfigpassword@2.2.2.2')",
                "session.run_sql(\"DROP USER IF EXISTS 'relation-40'@'%';\")",
            )
        )
        _get_cluster_primary_address.assert_called_once()
        _run_mysqlsh_script.assert_called_once_with(expected_commands)

    @patch("charms.mysql.v0.mysql.MySQLBase.get_cluster_primary_address", return_value="2.2.2.2")
    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    def test_delete_user_for_relation_failure(
        self, _run_mysqlsh_script, _get_cluster_primary_address
    ):
        """Test failure to delete users for relation."""
        _run_mysqlsh_script.side_effect = MySQLClientError("Error on subprocess")

        with self.assertRaises(MySQLDeleteUserForRelationError):
            self.mysql.delete_user_for_relation(40)

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    def test_get_cluster_members_addresses(self, _run_mysqlsh_script):
        """Test get_cluster_members_addresses() method."""
        _run_mysqlsh_script.return_value = "<MEMBERS>member1,member2,member4</MEMBERS>"

        output = self.mysql.get_cluster_members_addresses()

        expected_commands = "\n".join(
            (
                "shell.connect('clusteradmin:clusteradminpassword@127.0.0.1')",
                "cluster = dba.get_cluster('test_cluster')",
                "members = ','.join((member['address'] for member in cluster.describe()['defaultReplicaSet']['topology']))",
                "print(f'<MEMBERS>{members}</MEMBERS>')",
            )
        )

        _run_mysqlsh_script.assert_called_once_with(expected_commands)

        self.assertEqual(output, {"member1", "member2", "member4"})

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    def test_get_mysql_version(self, _run_mysqlsh_script):
        """Test get_mysql_version() method."""
        _run_mysqlsh_script.return_value = "<VERSION>8.0.29-0ubuntu0.20.04.3</VERSION>"

        version = self.mysql.get_mysql_version()
        expected_commands = "\n".join(
            (
                "shell.connect('clusteradmin:clusteradminpassword@127.0.0.1')",
                'result = session.run_sql("SELECT version()")',
                'print(f"<VERSION>{result.fetch_one()[0]}</VERSION>")',
            )
        )

        _run_mysqlsh_script.assert_called_once_with(expected_commands)

        self.assertEqual(version, "8.0.29-0ubuntu0.20.04.3")

    @patch(
        "charms.mysql.v0.mysql.MySQLBase.get_cluster_primary_address", return_value="1.1.1.1:3306"
    )
    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    def test_grant_privileges_to_user(self, _run_mysqlsh_script, _get_cluster_primary_address):
        """Test the successful execution of grant_privileges_to_user."""
        expected_commands = "\n".join(
            (
                "shell.connect('serverconfig:serverconfigpassword@1.1.1.1:3306')",
                "session.run_sql(\"GRANT CREATE USER ON *.* TO 'test_user'@'%' WITH GRANT OPTION\")",
            )
        )

        self.mysql.grant_privileges_to_user(
            "test_user", "%", ["CREATE USER"], with_grant_option=True
        )

        _run_mysqlsh_script.assert_called_with(expected_commands)

        _run_mysqlsh_script.reset_mock()

        expected_commands = "\n".join(
            (
                "shell.connect('serverconfig:serverconfigpassword@1.1.1.1:3306')",
                "session.run_sql(\"GRANT SELECT, UPDATE ON *.* TO 'test_user'@'%'\")",
            )
        )

        self.mysql.grant_privileges_to_user("test_user", "%", ["SELECT", "UPDATE"])

        _get_cluster_primary_address.assert_called()
        _run_mysqlsh_script.assert_called_with(expected_commands)

    @patch(
        "charms.mysql.v0.mysql.MySQLBase.get_cluster_status",
        return_value={
            "defaultreplicaset": {
                "topology": {
                    "mysql-k8s-0": {
                        "address": "mysql-k8s-0.mysql-k8s-endpoints:3306",
                        "memberrole": "secondary",
                        "status": "online",
                    },
                    "mysql-k8s-1": {
                        "address": "mysql-k8s-1.mysql-k8s-endpoints:3306",
                        "memberrole": "primary",
                        "status": "online",
                    },
                    "mysql-k8s-2": {
                        "address": "mysql-k8s-2.mysql-k8s-endpoints:3306",
                        "memberrole": "",
                        "status": "offline",
                    },
                }
            }
        },
    )
    def test_get_cluster_endpoints(self, _):
        """Test get_cluster_endpoints() method."""
        endpoints = self.mysql.get_cluster_endpoints(get_ips=False)

        self.assertEqual(
            endpoints,
            (
                "mysql-k8s-1.mysql-k8s-endpoints:3306",
                "mysql-k8s-0.mysql-k8s-endpoints:3306",
                "mysql-k8s-2.mysql-k8s-endpoints:3306",
            ),
        )

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    def test_offline_mode_and_hidden_instance_exists(self, _run_mysqlsh_script):
        """Test the offline_mode_and_hidden_instance_exists() method."""
        commands = (
            "shell.connect('clusteradmin:clusteradminpassword@127.0.0.1')",
            "cluster_topology = dba.get_cluster('test_cluster').status()['defaultReplicaSet']['topology']",
            "selected_instances = [label for label, member in cluster_topology.items() if 'Instance has offline_mode enabled' in member.get('instanceErrors', '') and member.get('hiddenFromRouter')]",
            "print(f'<OFFLINE_MODE_INSTANCES>{len(selected_instances)}</OFFLINE_MODE_INSTANCES>')",
        )

        _run_mysqlsh_script.return_value = "<OFFLINE_MODE_INSTANCES>1</OFFLINE_MODE_INSTANCES>"

        exists = self.mysql.offline_mode_and_hidden_instance_exists()
        self.assertTrue(exists)
        _run_mysqlsh_script.assert_called_once_with("\n".join(commands))

        _run_mysqlsh_script.reset_mock()
        _run_mysqlsh_script.return_value = "<OFFLINE_MODE_INSTANCES>0</OFFLINE_MODE_INSTANCES>"

        exists = self.mysql.offline_mode_and_hidden_instance_exists()
        self.assertFalse(exists)
        _run_mysqlsh_script.assert_called_once_with("\n".join(commands))

        _run_mysqlsh_script.reset_mock()
        _run_mysqlsh_script.side_effect = MySQLClientError()

        with self.assertRaises(MySQLOfflineModeAndHiddenInstanceExistsError):
            self.mysql.offline_mode_and_hidden_instance_exists()

        _run_mysqlsh_script.reset_mock()
        _run_mysqlsh_script.return_value = "garbage"

        with self.assertRaises(MySQLOfflineModeAndHiddenInstanceExistsError):
            self.mysql.offline_mode_and_hidden_instance_exists()

    @patch("charms.mysql.v0.mysql.MySQLBase._get_total_memory")
    def test_get_innodb_buffer_pool_parameters(self, _get_total_memory):
        """Test the successful execution of get_innodb_buffer_pool_parameters()."""
        _get_total_memory.return_value = 16484458496

        pool_size, chunk_size = self.mysql.get_innodb_buffer_pool_parameters()
        self.assertEqual(12482248704, pool_size)
        self.assertEqual(1560281088, chunk_size)

        _get_total_memory.return_value = 3221000000
        pool_size, chunk_size = self.mysql.get_innodb_buffer_pool_parameters()
        self.assertEqual(1610612736, pool_size)
        self.assertEqual(201326592, chunk_size)

        _get_total_memory.return_value = 1073741825
        pool_size, chunk_size = self.mysql.get_innodb_buffer_pool_parameters()
        self.assertEqual(536870912, pool_size)
        self.assertIsNone(chunk_size)

    @patch("charms.mysql.v0.mysql.MySQLBase._get_total_memory")
    def test_get_innodb_buffer_pool_parameters_exception(self, _get_total_memory):
        """Test a failure in execution of get_innodb_buffer_pool_parameters()."""
        _get_total_memory.side_effect = MySQLExecError

        with self.assertRaises(MySQLGetInnoDBBufferPoolParametersError):
            self.mysql.get_innodb_buffer_pool_parameters()

    @patch("charms.mysql.v0.mysql.MySQLBase._execute_commands")
    def test_get_total_memory(self, _execute_commands):
        """Test successful execution of _get_total_memory()."""
        _execute_commands.return_value = "16484458496\n", None

        total_memory = self.mysql._get_total_memory()

        self.assertEqual(16484458496, total_memory)

        _execute_commands.assert_called_once_with(
            "free --bytes | awk '/^Mem:/{print $2; exit}'".split(),
            bash=True,
        )

    @patch("charms.mysql.v0.mysql.MySQLBase._execute_commands")
    def test_get_total_memory_exception(self, _execute_commands):
        """Test a failure in execution of _get_total_memory()."""
        _execute_commands.side_effect = MySQLExecError

        with self.assertRaises(MySQLExecError):
            self.mysql._get_total_memory()

    @patch("charms.mysql.v0.mysql.MySQLBase._execute_commands")
    def test_execute_backup_commands(self, _execute_commands):
        """Test successful execution of execute_backup_commands()."""
        _execute_commands.side_effect = [
            ("16", None),
            ("/tmp/base/directory/xtra_backup_ABCD", None),
            ("stdout", "stderr"),
        ]

        stdout, stderr = self.mysql.execute_backup_commands(
            "s3_bucket",
            "s3_directory",
            "s3_access_key",
            "s3_secret_key",
            "s3_endpoint",
            "/xtrabackup/location",
            "/xbcloud/location",
            "/xtrabackup/plugin/dir",
            "/mysqld/socket/file.sock",
            "/tmp/base/directory",
            "/defaults/file.cnf",
            user="test_user",
            group="test_group",
        )

        self.assertEqual(stdout, "stdout")
        self.assertEqual(stderr, "stderr")

        self.assertEqual(_execute_commands.call_count, 3)

        _expected_nproc_commands = ["nproc"]
        _expected_tmp_dir_commands = (
            "mktemp --directory /tmp/base/directory/xtra_backup_XXXX".split()
        )
        _expected_xtrabackup_commands = """
/xtrabackup/location --defaults-file=/defaults/file.cnf
            --defaults-group=mysqld
            --no-version-check
            --parallel=16
            --user=serverconfig
            --password=serverconfigpassword
            --socket=/mysqld/socket/file.sock
            --lock-ddl
            --backup
            --stream=xbstream
            --xtrabackup-plugin-dir=/xtrabackup/plugin/dir
            --target-dir=/tmp/base/directory/xtra_backup_ABCD
            --no-server-version-check
    | /xbcloud/location put
            --curl-retriable-errors=7
            --insecure
            --storage=s3
            --parallel=10
            --md5
            --s3-bucket=s3_bucket
            --s3-endpoint=s3_endpoint
            s3_directory
""".split()

        self.assertEqual(
            sorted(_execute_commands.mock_calls),
            sorted(
                [
                    call(_expected_nproc_commands),
                    call(_expected_tmp_dir_commands, user="test_user", group="test_group"),
                    call(
                        _expected_xtrabackup_commands,
                        bash=True,
                        user="test_user",
                        group="test_group",
                        env={
                            "ACCESS_KEY_ID": "s3_access_key",
                            "SECRET_ACCESS_KEY": "s3_secret_key",
                        },
                    ),
                ]
            ),
        )

    @patch("charms.mysql.v0.mysql.MySQLBase._execute_commands")
    def test_execute_backup_commands_exceptions(self, _execute_commands):
        """Test a failure in the execution of execute_backup_commands()."""
        _execute_commands.side_effect = MySQLExecError("failure")

        args = [
            "s3_bucket",
            "s3_directory",
            "s3_access_key",
            "s3_secret_key",
            "s3_endpoint",
            "/xtrabackup/location",
            "/xbcloud/location",
            "/xtrabackup/plugin/dir",
            "/mysqld/socket/file.sock",
            "/tmp/base/directory",
            "/defaults/file.cnf",
        ]
        kwargs = {
            "user": "test_user",
            "group": "test_group",
        }

        with self.assertRaises(MySQLExecuteBackupCommandsError):
            self.mysql.execute_backup_commands(*args, **kwargs)

        _execute_commands.side_effect = Exception("failure")

        with self.assertRaises(MySQLExecuteBackupCommandsError):
            self.mysql.execute_backup_commands(*args, **kwargs)

        _execute_commands.side_effect = [
            ("16", None),
            ("/tmp/base/directory/xtra_backup_ABCD", None),
            MySQLExecError("failure"),
        ]

        with self.assertRaises(MySQLExecuteBackupCommandsError):
            self.mysql.execute_backup_commands(*args, **kwargs)

        _execute_commands.side_effect = [
            ("16", None),
            ("/tmp/base/directory/xtra_backup_ABCD", None),
            Exception("failure"),
        ]

        with self.assertRaises(MySQLExecuteBackupCommandsError):
            self.mysql.execute_backup_commands(*args, **kwargs)

    @patch("charms.mysql.v0.mysql.MySQLBase._execute_commands")
    def test_delete_temp_backup_directory(self, _execute_commands):
        """Test successful execution of delete_temp_backup_directory()."""
        self.mysql.delete_temp_backup_directory(
            "/temp/base/directory", user="test_user", group="test_group"
        )

        _execute_commands.assert_called_once_with(
            "find /temp/base/directory -wholename /temp/base/directory/xtra_backup_* -delete".split(),
            user="test_user",
            group="test_group",
        )

    @patch("charms.mysql.v0.mysql.MySQLBase._execute_commands")
    def test_delete_temp_backup_directory_exception(self, _execute_commands):
        """Test a failure in execution of delete_temp_backup_directory()."""
        _execute_commands.side_effect = MySQLExecError("failure")

        with self.assertRaises(MySQLDeleteTempBackupDirectoryError):
            self.mysql.delete_temp_backup_directory("/temp/backup/directory")

        _execute_commands.side_effect = Exception("failure")

        with self.assertRaises(MySQLDeleteTempBackupDirectoryError):
            self.mysql.delete_temp_backup_directory("/temp/backup/directory")

    @patch("charms.mysql.v0.mysql.MySQLBase._execute_commands")
    def test_retrieve_backup_with_xbcloud(
        self,
        _execute_commands,
    ):
        """Test a successful execution of retrieve_backup_with_xbcloud()."""
        _execute_commands.side_effect = [
            ("16", None),
            ("mysql/data/directory/#mysql_sst_ABCD", None),
            ("", None),
        ]

        self.mysql.retrieve_backup_with_xbcloud(
            "s3-bucket",
            "s3-path",
            "s3-access-key",
            "s3-secret-key",
            "s3-endpoint",
            "backup-id",
            "mysql/data/directory",
            "xbcloud/location",
            "xbstream/location",
            user="test-user",
            group="test-group",
        )

        _expected_nproc_commands = ["nproc"]
        _expected_temp_dir_commands = (
            "mktemp --directory mysql/data/directory/#mysql_sst_XXXX".split()
        )
        _expected_retrieve_backup_commands = """
xbcloud/location get
        --curl-retriable-errors=7
        --parallel=10
        --s3-endpoint=s3-endpoint
        s3://s3-bucket/s3-path/backup-id
    | xbstream/location
        --decompress
        -x
        -C mysql/data/directory/#mysql_sst_ABCD
        --parallel=16
""".split()

        self.assertEqual(
            sorted(_execute_commands.mock_calls),
            sorted(
                [
                    call(_expected_nproc_commands),
                    call(_expected_temp_dir_commands, user="test-user", group="test-group"),
                    call(
                        _expected_retrieve_backup_commands,
                        bash=True,
                        env={
                            "ACCESS_KEY_ID": "s3-access-key",
                            "SECRET_ACCESS_KEY": "s3-secret-key",
                        },
                        user="test-user",
                        group="test-group",
                    ),
                ]
            ),
        )

    @patch("charms.mysql.v0.mysql.MySQLBase._execute_commands")
    def test_retrieve_backup_with_xbcloud_failure(
        self,
        _execute_commands,
    ):
        """Test a failure of retrieve_backup_with_xbcloud()."""
        _execute_commands.side_effect = [
            ("16", None),
            ("mysql/data/directory/mysql_sst_ABCD", None),
            MySQLExecError("failure"),
        ]

        with self.assertRaises(MySQLRetrieveBackupWithXBCloudError):
            self.mysql.retrieve_backup_with_xbcloud(
                "s3-bucket",
                "s3-path",
                "s3-access-key",
                "s3-secret-key",
                "s3-endpoint",
                "backup-id",
                "mysql/data/directory",
                "xbcloud/location",
                "xbstream/location",
                user="test-user",
                group="test-group",
            )

        _execute_commands.side_effect = [
            ("16", None),
            MySQLExecError("failure"),
        ]

        with self.assertRaises(MySQLRetrieveBackupWithXBCloudError):
            self.mysql.retrieve_backup_with_xbcloud(
                "s3-bucket",
                "s3-path",
                "s3-access-key",
                "s3-secret-key",
                "s3-endpoint",
                "backup-id",
                "mysql/data/directory",
                "xbcloud/location",
                "xbstream/location",
                user="test-user",
                group="test-group",
            )

        _execute_commands.side_effect = [
            MySQLExecError("failure"),
        ]

        with self.assertRaises(MySQLRetrieveBackupWithXBCloudError):
            self.mysql.retrieve_backup_with_xbcloud(
                "s3-bucket",
                "s3-path",
                "s3-access-key",
                "s3-secret-key",
                "s3-endpoint",
                "backup-id",
                "mysql/data/directory",
                "xbcloud/location",
                "xbstream/location",
                user="test-user",
                group="test-group",
            )

    @patch(
        "charms.mysql.v0.mysql.MySQLBase.get_innodb_buffer_pool_parameters",
        return_value=(1234, 5678),
    )
    @patch("charms.mysql.v0.mysql.MySQLBase._execute_commands")
    def test_prepare_backup_for_restore(
        self,
        _execute_commands,
        _get_innodb_buffer_pool_parameters,
    ):
        """Test successful execution of prepare_backup_for_restore()."""
        self.mysql.prepare_backup_for_restore(
            "backup/location",
            "xtrabackup/location",
            "xtrabackup/plugin/dir",
            user="test-user",
            group="test-group",
        )

        _expected_prepare_backup_command = """
xtrabackup/location --prepare
        --use-memory=1234
        --no-version-check
        --rollback-prepared-trx
        --xtrabackup-plugin-dir=xtrabackup/plugin/dir
        --target-dir=backup/location
""".split()

        _get_innodb_buffer_pool_parameters.assert_called_once()
        _execute_commands.assert_called_once_with(
            _expected_prepare_backup_command,
            user="test-user",
            group="test-group",
        )

    @patch(
        "charms.mysql.v0.mysql.MySQLBase.get_innodb_buffer_pool_parameters",
        return_value=(1234, 5678),
    )
    @patch("charms.mysql.v0.mysql.MySQLBase._execute_commands")
    def test_prepare_backup_for_restore_failure(
        self,
        _execute_commands,
        _get_innodb_buffer_pool_parameters,
    ):
        """Test failure of prepare_backup_for_restore()."""
        _execute_commands.side_effect = MySQLExecError("failure")

        with self.assertRaises(MySQLPrepareBackupForRestoreError):
            self.mysql.prepare_backup_for_restore(
                "backup/location",
                "xtrabackup/location",
                "xtrabackup/plugin/dir",
                user="test-user",
                group="test-group",
            )

        _get_innodb_buffer_pool_parameters.side_effect = MySQLGetInnoDBBufferPoolParametersError()
        with self.assertRaises(MySQLPrepareBackupForRestoreError):
            self.mysql.prepare_backup_for_restore(
                "backup/location",
                "xtrabackup/location",
                "xtrabackup/plugin/dir",
                user="test-user",
                group="test-group",
            )

    @patch("charms.mysql.v0.mysql.MySQLBase._execute_commands")
    def test_empty_data_files(
        self,
        _execute_commands,
    ):
        """Test successful execution of empty_data_files()."""
        self.mysql.empty_data_files(
            "mysql/data/directory",
            user="test-user",
            group="test-group",
        )

        _expected_commands = "find mysql/data/directory -not -path mysql/data/directory/#mysql_sst_* -not -path mysql/data/directory -delete".split()

        _execute_commands.assert_called_once_with(
            _expected_commands,
            user="test-user",
            group="test-group",
        )

    @patch("charms.mysql.v0.mysql.MySQLBase._execute_commands")
    def test_empty_data_files_failure(
        self,
        _execute_commands,
    ):
        """Test failure of empty_data_files()."""
        _execute_commands.side_effect = MySQLExecError("failure")

        with self.assertRaises(MySQLEmptyDataDirectoryError):
            self.mysql.empty_data_files(
                "mysql/data/directory",
                user="test-user",
                group="test-group",
            )

    @patch("charms.mysql.v0.mysql.MySQLBase._execute_commands")
    def test_restore_backup(
        self,
        _execute_commands,
    ):
        """Test successful execution of restore_backup()."""
        self.mysql.restore_backup(
            "backup/location",
            "xtrabackup/location",
            "defaults/config/file",
            "mysql/data/directory",
            "xtrabackup/plugin/directory",
            user="test-user",
            group="test-group",
        )

        _expected_commands = """
xtrabackup/location --defaults-file=defaults/config/file
        --defaults-group=mysqld
        --datadir=mysql/data/directory
        --no-version-check
        --move-back
        --force-non-empty-directories
        --xtrabackup-plugin-dir=xtrabackup/plugin/directory
        --target-dir=backup/location
""".split()

        _execute_commands.assert_called_once_with(
            _expected_commands,
            user="test-user",
            group="test-group",
        )

    @patch("charms.mysql.v0.mysql.MySQLBase._execute_commands")
    def test_restore_backup_failure(
        self,
        _execute_commands,
    ):
        """Test failure of restore_backup()."""
        _execute_commands.side_effect = MySQLExecError("failure")

        with self.assertRaises(MySQLRestoreBackupError):
            self.mysql.restore_backup(
                "backup/location",
                "xtrabackup/location",
                "defaults/config/file",
                "mysql/data/directory",
                "xtrabackup/plugin/directory",
                user="test-user",
                group="test-group",
            )

    @patch("charms.mysql.v0.mysql.MySQLBase._execute_commands")
    def test_delete_temp_restore_directory(
        self,
        _execute_commands,
    ):
        """Test successful execution of delete_temp_restore_directory()."""
        self.mysql.delete_temp_restore_directory(
            "mysql/data/directory",
            user="test-user",
            group="test-group",
        )

        _expected_commands = "find mysql/data/directory -wholename mysql/data/directory/#mysql_sst_* -delete".split()

        _execute_commands.assert_called_once_with(
            _expected_commands,
            user="test-user",
            group="test-group",
        )

    @patch("charms.mysql.v0.mysql.MySQLBase._execute_commands")
    def test_delete_temp_restore_directory_failure(
        self,
        _execute_commands,
    ):
        """Test failure of delete_temp_restore_directory()."""
        _execute_commands.side_effect = MySQLExecError("failure")

        with self.assertRaises(MySQLDeleteTempRestoreDirectoryError):
            self.mysql.delete_temp_restore_directory(
                "mysql/data/directory",
                user="test-user",
                group="test-group",
            )

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlcli_script")
    def test_tls_set_custom(self, _run_mysqlcli_script):
        """Test the successful execution of tls_set_custom."""
        commands = (
            "SET PERSIST ssl_ca='ca_path';"
            "SET PERSIST ssl_key='key_path';"
            "SET PERSIST ssl_cert='cert_path';"
            "SET PERSIST require_secure_transport=on;"
            "ALTER INSTANCE RELOAD TLS;"
        )

        self.mysql.tls_setup("ca_path", "key_path", "cert_path", True)

        _run_mysqlcli_script.assert_called_with(
            commands,
            user=self.mysql.server_config_user,
            password=self.mysql.server_config_password,
        )

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlcli_script")
    def test_tls_restore_deafult(self, _run_mysqlcli_script):
        """Test the successful execution of tls_set_custom."""
        commands = (
            "SET PERSIST ssl_ca='ca.pem';"
            "SET PERSIST ssl_key='server-key.pem';"
            "SET PERSIST ssl_cert='server-cert.pem';"
            "SET PERSIST require_secure_transport=off;"
            "ALTER INSTANCE RELOAD TLS;"
        )

        self.mysql.tls_setup()

        _run_mysqlcli_script.assert_called_with(
            commands,
            user=self.mysql.server_config_user,
            password=self.mysql.server_config_password,
        )

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    def test_kill_unencrypted_sessions(self, _run_mysqlsh_script):
        """Test kill non TLS connections."""
        commands = (
            f"shell.connect('{self.mysql.server_config_user}:{self.mysql.server_config_password}@127.0.0.1')",
            (
                'processes = session.run_sql("'
                "SELECT processlist_id FROM performance_schema.threads WHERE "
                "connection_type = 'TCP/IP' AND type = 'FOREGROUND';"
                '")'
            ),
            "process_id_list = [id[0] for id in processes.fetch_all()]",
            'for process_id in process_id_list:\n  session.run_sql(f"KILL CONNECTION {process_id}")',
        )

        self.mysql.kill_unencrypted_sessions()

        _run_mysqlsh_script.assert_called_with("\n".join(commands))

    def test_abstract_methods(self):
        """Test abstract methods."""
        with self.assertRaises(NotImplementedError):
            self.mysql.wait_until_mysql_connection()

        with self.assertRaises(NotImplementedError):
            self.mysql._run_mysqlsh_script("")

        with self.assertRaises(NotImplementedError):
            self.mysql._run_mysqlcli_script("")

        with self.assertRaises(NotImplementedError):
            self.mysql._execute_commands([])

        with self.assertRaises(NotImplementedError):
            self.mysql.is_mysqld_running()

        with self.assertRaises(NotImplementedError):
            self.mysql.stop_mysqld()

        with self.assertRaises(NotImplementedError):
            self.mysql.start_mysqld()
