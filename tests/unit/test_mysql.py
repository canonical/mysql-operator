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
    MySQLClusterMetadataExistsError,
    MySQLConfigureInstanceError,
    MySQLConfigureMySQLUsersError,
    MySQLConfigureRouterUserError,
    MySQLCreateApplicationDatabaseAndScopedUserError,
    MySQLCreateClusterError,
    MySQLCreateClusterSetError,
    MySQLCreateReplicaClusterError,
    MySQLDeleteTempBackupDirectoryError,
    MySQLDeleteTempRestoreDirectoryError,
    MySQLDeleteUserError,
    MySQLDeleteUsersForRelationError,
    MySQLDeleteUsersForUnitError,
    MySQLEmptyDataDirectoryError,
    MySQLExecError,
    MySQLExecuteBackupCommandsError,
    MySQLGetAutoTuningParametersError,
    MySQLGetClusterPrimaryAddressError,
    MySQLGetMySQLVersionError,
    MySQLGetRouterUsersError,
    MySQLGetVariableError,
    MySQLInitializeJujuOperationsTableError,
    MySQLMemberState,
    MySQLNoMemberStateError,
    MySQLOfflineModeAndHiddenInstanceExistsError,
    MySQLPluginInstallError,
    MySQLPrepareBackupForRestoreError,
    MySQLPromoteClusterToPrimaryError,
    MySQLRemoveInstanceError,
    MySQLRemoveInstanceRetryError,
    MySQLRemoveReplicaClusterError,
    MySQLRemoveRouterFromMetadataError,
    MySQLRescanClusterError,
    MySQLRestoreBackupError,
    MySQLRetrieveBackupWithXBCloudError,
    MySQLServerNotUpgradableError,
    MySQLSetClusterPrimaryError,
    MySQLSetInstanceOfflineModeError,
    MySQLSetInstanceOptionError,
    MySQLSetVariableError,
)

from constants import MYSQLD_SOCK_FILE

SHORT_CLUSTER_STATUS = {
    "defaultreplicaset": {
        "topology": {
            "mysql-k8s-0": {
                "address": "mysql-k8s-0.mysql-k8s-endpoints:3306",
                "memberrole": "secondary",
                "mode": "r/o",
                "status": "online",
            },
            "mysql-k8s-1": {
                "address": "mysql-k8s-1.mysql-k8s-endpoints:3306",
                "memberrole": "primary",
                "mode": "r/w",
                "status": "online",
            },
            "mysql-k8s-2": {
                "address": "mysql-k8s-2.mysql-k8s-endpoints:3306",
                "memberrole": "",
                "mode": "r/o",
                "status": "offline",
            },
        }
    }
}

CLUSTER_SET_STATUS = {
    "clusters": {
        "test_cluster": {
            "clusterrole": "replica",
            "clustersetreplicationstatus": "ok",
            "globalstatus": "ok",
        },
        "lisbon": {
            "clusterrole": "primary",
            "globalstatus": "ok",
            "primary": "juju-3f9f94-1.lxd:3306",
        },
    },
    "domainname": "test_cluster_set",
    "globalprimaryinstance": "juju-3f9f94-1.lxd:3306",
    "primarycluster": "lisbon",
    "status": "healthy",
    "statustext": "all clusters available.",
}


class TestMySQLBase(unittest.TestCase):
    # Patch abstract methods so it's
    # possible to instantiate abstract class.
    @patch.multiple(MySQLBase, __abstractmethods__=set())
    def setUp(self):
        self.mysql = MySQLBase(
            "127.0.0.1",
            MYSQLD_SOCK_FILE,
            "test_cluster",
            "test_cluster_set",
            "password",
            "serverconfig",
            "serverconfigpassword",
            "clusteradmin",
            "clusteradminpassword",
            "monitoring",
            "monitoringpassword",
            "backups",
            "backupspassword",
        )  # pyright: ignore

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlcli_script")
    def test_configure_mysql_users(self, _run_mysqlcli_script):
        """Test successful configuration of MySQL users."""
        _run_mysqlcli_script.return_value = b""

        _expected_configure_user_commands = (
            "CREATE USER 'serverconfig'@'%' IDENTIFIED BY 'serverconfigpassword'",
            "GRANT ALL ON *.* TO 'serverconfig'@'%' WITH GRANT OPTION",
            "CREATE USER 'monitoring'@'%' IDENTIFIED BY 'monitoringpassword' WITH MAX_USER_CONNECTIONS 3",
            "GRANT SYSTEM_USER, SELECT, PROCESS, SUPER, REPLICATION CLIENT, RELOAD ON *.* TO 'monitoring'@'%'",
            "CREATE USER 'backups'@'%' IDENTIFIED BY 'backupspassword'",
            "GRANT CONNECTION_ADMIN, BACKUP_ADMIN, PROCESS, RELOAD, LOCK TABLES, REPLICATION CLIENT ON *.* TO 'backups'@'%'",
            "GRANT SELECT ON performance_schema.log_status TO 'backups'@'%'",
            "GRANT SELECT ON performance_schema.keyring_component_status TO 'backups'@'%'",
            "GRANT SELECT ON performance_schema.replication_group_members TO 'backups'@'%'",
            "UPDATE mysql.user SET authentication_string=null WHERE User='root' and Host='localhost'",
            "ALTER USER 'root'@'localhost' IDENTIFIED BY 'password'",
            "REVOKE SYSTEM_USER, SYSTEM_VARIABLES_ADMIN, SUPER, REPLICATION_SLAVE_ADMIN, GROUP_REPLICATION_ADMIN, BINLOG_ADMIN, SET_USER_ID, ENCRYPTION_KEY_ADMIN, VERSION_TOKEN_ADMIN, CONNECTION_ADMIN ON *.* FROM 'root'@'localhost'",
            "FLUSH PRIVILEGES",
        )

        self.mysql.configure_mysql_users()

        _run_mysqlcli_script.assert_called_once_with(
            _expected_configure_user_commands, password="password"
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
            "select user from mysql.user where user = 'test_username' and host = '1.1.1.1'",
        )

        self.mysql.does_mysql_user_exist("test_username", "1.1.1.1")
        _run_mysqlcli_script.assert_called_once_with(
            user_existence_command, user="serverconfig", password="serverconfigpassword"
        )

        # Reset the mock
        _run_mysqlcli_script.reset_mock()

        # Test default hostname
        user_existence_command = (
            "select user from mysql.user where user = 'test_username' and host = '1.1.1.2'",
        )

        self.mysql.does_mysql_user_exist("test_username", "1.1.1.2")
        _run_mysqlcli_script.assert_called_once_with(
            user_existence_command, user="serverconfig", password="serverconfigpassword"
        )

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlcli_script")
    def test_does_mysql_user_exist_failure(self, _run_mysqlcli_script):
        """Test failure in execution of does_mysql_user_exist."""
        _run_mysqlcli_script.side_effect = MySQLClientError("Error on subprocess")

        with self.assertRaises(MySQLCheckUserExistenceError):
            self.mysql.does_mysql_user_exist("test_username", "1.1.1.1")

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    def test_configure_mysqlrouter_user(self, _run_mysqlsh_script):
        """Test the successful execution of configure_mysqlrouter_user."""
        _run_mysqlsh_script.return_value = ""

        _expected_create_mysqlrouter_user_commands = "\n".join((
            "shell.connect_to_primary()",
            "session.run_sql(\"CREATE USER 'test_username'@'1.1.1.1' IDENTIFIED BY 'test_password' ATTRIBUTE '{\\\"unit_name\\\": \\\"app/0\\\"}';\")",
        ))

        _expected_mysqlrouter_user_grant_commands = "\n".join((
            "shell.connect_to_primary()",
            "session.run_sql(\"GRANT CREATE USER ON *.* TO 'test_username'@'1.1.1.1' WITH GRANT OPTION;\")",
            "session.run_sql(\"GRANT SELECT, INSERT, UPDATE, DELETE, EXECUTE ON mysql_innodb_cluster_metadata.* TO 'test_username'@'1.1.1.1';\")",
            "session.run_sql(\"GRANT SELECT ON mysql.user TO 'test_username'@'1.1.1.1';\")",
            "session.run_sql(\"GRANT SELECT ON performance_schema.replication_group_members TO 'test_username'@'1.1.1.1';\")",
            "session.run_sql(\"GRANT SELECT ON performance_schema.replication_group_member_stats TO 'test_username'@'1.1.1.1';\")",
            "session.run_sql(\"GRANT SELECT ON performance_schema.global_variables TO 'test_username'@'1.1.1.1';\")",
        ))

        self.mysql.configure_mysqlrouter_user("test_username", "test_password", "1.1.1.1", "app/0")

        self.assertEqual(_run_mysqlsh_script.call_count, 2)

        self.assertEqual(
            sorted(_run_mysqlsh_script.mock_calls),
            sorted([
                call(
                    _expected_create_mysqlrouter_user_commands,
                    user="serverconfig",
                    password="serverconfigpassword",
                    host="127.0.0.1:33062",
                ),
                call(
                    _expected_mysqlrouter_user_grant_commands,
                    user="serverconfig",
                    password="serverconfigpassword",
                    host="127.0.0.1:33062",
                ),
            ]),
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

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    def test_create_application_database_and_scoped_user(self, _run_mysqlsh_script):
        """Test the successful execution of create_application_database_and_scoped_user."""
        _run_mysqlsh_script.return_value = ""

        _expected_create_scoped_user_commands = "\n".join((
            "shell.connect_to_primary()",
            'session.run_sql("CREATE DATABASE IF NOT EXISTS `test-database`;")',
            'session.run_sql("CREATE USER `test-username`@`1.1.1.1` IDENTIFIED BY \'test-password\' ATTRIBUTE \'{\\"unit_name\\": \\"app/0\\"}\';")',
            'session.run_sql("GRANT USAGE ON *.* TO `test-username`@`1.1.1.1`;")',
            'session.run_sql("GRANT ALL PRIVILEGES ON `test-database`.* TO `test-username`@`1.1.1.1`;")',
        ))

        self.mysql.create_application_database_and_scoped_user(
            "test-database", "test-username", "test-password", "1.1.1.1", unit_name="app/0"
        )

        self.assertEqual(_run_mysqlsh_script.call_count, 1)

        self.assertEqual(
            _run_mysqlsh_script.mock_calls,
            [
                call(
                    _expected_create_scoped_user_commands,
                    user="serverconfig",
                    password="serverconfigpassword",
                    host="127.0.0.1:33062",
                )
            ],
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
                "test_database", "test_username", "test_password", "1.1.1.1", unit_name="app/.0"
            )

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    @patch("charms.mysql.v0.mysql.MySQLBase.wait_until_mysql_connection")
    def test_configure_instance(self, _wait_until_mysql_connection, _run_mysqlsh_script):
        """Test a successful execution of configure_instance."""
        # Test with create_cluster_admin=False
        configure_instance_commands = [
            "dba.configure_instance(options=",
            "{'restart': 'true'})",
        ]

        self.mysql.configure_instance(create_cluster_admin=False)

        _run_mysqlsh_script.assert_called_once_with(
            "".join(configure_instance_commands),
            user="serverconfig",
            password="serverconfigpassword",
            host="127.0.0.1:33062",
        )

        _run_mysqlsh_script.reset_mock()

        # Test with create_cluster_admin=True
        configure_instance_commands[1] = (
            "{'restart': 'true', "
            "'clusterAdmin': 'clusteradmin', 'clusterAdminPassword': 'clusteradminpassword'})"
        )
        self.mysql.configure_instance(create_cluster_admin=True)

        _run_mysqlsh_script.assert_called_once_with(
            "".join(configure_instance_commands),
            user="serverconfig",
            password="serverconfigpassword",
            host="127.0.0.1:33062",
        )

        # Test an issue with _run_mysqlsh_script
        _wait_until_mysql_connection.reset_mock()
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
            "DROP TABLE IF EXISTS mysql.juju_units_operations",
            "CREATE TABLE mysql.juju_units_operations (task varchar(20), executor varchar(20), "
            "status varchar(20), primary key(task))",
            "INSERT INTO mysql.juju_units_operations values ('unit-teardown', '', 'not-started') "
            "ON DUPLICATE KEY UPDATE executor = '', status = 'not-started'",
            "INSERT INTO mysql.juju_units_operations values ('unit-add', '', 'not-started') "
            "ON DUPLICATE KEY UPDATE executor = '', status = 'not-started'",
        )

        self.mysql.initialize_juju_units_operations_table()

        _run_mysqlcli_script.assert_called_once_with(
            expected_initialize_table_commands,
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
            "cluster = dba.create_cluster('test_cluster', {'communicationStack': 'MySQL'})",
            "cluster.set_instance_option('127.0.0.1', 'label', 'mysql-0')",
        )

        self.mysql.create_cluster("mysql-0")

        _run_mysqlsh_script.assert_called_once_with(
            "\n".join(create_cluster_commands),
            user="serverconfig",
            password="serverconfigpassword",
            host="127.0.0.1:33062",
        )

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    def test_create_cluster_exceptions(self, _run_mysqlsh_script):
        """Test exceptions raised while running create_cluster."""
        _run_mysqlsh_script.side_effect = MySQLClientError("Error on subprocess")

        with self.assertRaises(MySQLCreateClusterError):
            self.mysql.create_cluster("mysql-0")

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    def test_create_cluster_set(self, _run_mysqlsh_script):
        """Test a successful execution of create_cluster."""
        create_cluster_commands = (
            "shell.connect_to_primary()",
            "cluster = dba.get_cluster('test_cluster')",
            "cluster.create_cluster_set('test_cluster_set')",
        )

        self.mysql.create_cluster_set()

        _run_mysqlsh_script.assert_called_once_with(
            "\n".join(create_cluster_commands),
            user="serverconfig",
            password="serverconfigpassword",
            host="127.0.0.1:33062",
        )

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    def test_create_cluster_set_exceptions(self, _run_mysqlsh_script):
        """Test exceptions raised while running create_cluster."""
        _run_mysqlsh_script.side_effect = MySQLClientError("Error on subprocess")

        with self.assertRaises(MySQLCreateClusterSetError):
            self.mysql.create_cluster_set()

    @patch("charms.mysql.v0.mysql.MySQLBase._release_lock")
    @patch("charms.mysql.v0.mysql.MySQLBase._acquire_lock", return_value=True)
    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    def test_add_instance_to_cluster(self, _run_mysqlsh_script, _acquire_lock, _release_lock):
        """Test a successful execution of create_cluster."""
        add_instance_to_cluster_commands = (
            "cluster = dba.get_cluster('test_cluster')\n"
            "shell.options['dba.restartWaitTimeout'] = 3600\n"
            "cluster.add_instance('clusteradmin@127.0.0.2', {'password': 'clusteradminpassword',"
            " 'label': 'mysql-1', 'recoveryMethod': 'auto'})"
        )

        self.mysql.add_instance_to_cluster(
            instance_address="127.0.0.2", instance_unit_label="mysql-1"
        )

        _run_mysqlsh_script.assert_called_once_with(
            add_instance_to_cluster_commands,
            user="serverconfig",
            password="serverconfigpassword",
            host="127.0.0.1:33062",
            exception_as_warning=True,
        )
        _acquire_lock.assert_called_once()
        _release_lock.assert_called_once()

    @patch("charms.mysql.v0.mysql.MySQLBase._release_lock")
    @patch("charms.mysql.v0.mysql.MySQLBase._acquire_lock", return_value=True)
    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    def test_add_instance_to_cluster_exception(
        self, _run_mysqlsh_script, _acquire_lock, _release_lock
    ):
        """Test exceptions raised while running add_instance_to_cluster."""
        _run_mysqlsh_script.side_effect = MySQLClientError("Error on subprocess")

        with self.assertRaises(MySQLAddInstanceToClusterError):
            self.mysql.add_instance_to_cluster(
                instance_address="127.0.0.2", instance_unit_label="mysql-1"
            )
            _acquire_lock.assert_called_once()
            _release_lock.assert_called_once()
            _run_mysqlsh_script.assert_called()

    @patch(
        "charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script", return_value="INSTANCE_CONFIGURED"
    )
    def test_is_instance_configured_for_innodb(self, _run_mysqlsh_script):
        """Test with no exceptions while calling the is_instance_configured_for_innodb method."""
        # test successfully configured instance
        check_instance_configuration_commands = (
            "instance_configured = dba.check_instance_configuration()['status'] == 'ok'",
            'print("INSTANCE_CONFIGURED" if instance_configured else "INSTANCE_NOT_CONFIGURED")',
        )

        is_instance_configured = self.mysql.is_instance_configured_for_innodb(
            "127.0.0.2", "mysql-1"
        )

        _run_mysqlsh_script.assert_called_once_with(
            "\n".join(check_instance_configuration_commands),
            user="serverconfig",
            password="serverconfigpassword",
            host="127.0.0.2:33062",
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
            "\n".join(check_instance_configuration_commands),
            user="serverconfig",
            password="serverconfigpassword",
            host="127.0.0.2:33062",
        )
        self.assertFalse(is_instance_configured)

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    def test_drop_group_replication_metadata_schema(self, _run_mysqlsh_script):
        """Test with no exceptions while calling the drop_group_replication_metadata_schema method."""
        self.mysql.drop_group_replication_metadata_schema()

        _run_mysqlsh_script.assert_called_once_with(
            "dba.drop_metadata_schema()",
            user="serverconfig",
            password="serverconfigpassword",
            host="127.0.0.1:33062",
        )

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    def test_is_instance_configured_for_innodb_exceptions(self, _run_mysqlsh_script):
        """Test an exception while calling the is_instance_configured_for_innodb method."""
        _run_mysqlsh_script.side_effect = MySQLClientError("Error on subprocess")

        check_instance_configuration_commands = (
            "instance_configured = dba.check_instance_configuration()['status'] == 'ok'",
            'print("INSTANCE_CONFIGURED" if instance_configured else "INSTANCE_NOT_CONFIGURED")',
        )

        is_instance_configured = self.mysql.is_instance_configured_for_innodb(
            "127.0.0.2", "mysql-1"
        )

        _run_mysqlsh_script.assert_called_once_with(
            "\n".join(check_instance_configuration_commands),
            user="serverconfig",
            password="serverconfigpassword",
            host="127.0.0.2:33062",
        )
        self.assertFalse(is_instance_configured)

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    def test_execute_remove_instance(self, _run_mysqlsh_script):
        expected_remove_instance_commands = (
            "cluster = dba.get_cluster('test_cluster')\n"
            "cluster.remove_instance('clusteradmin@127.0.0.1', "
            "{'password': 'clusteradminpassword', 'force': 'false'})"
        )

        self.mysql.execute_remove_instance(connect_instance="1.2.3.4", force=False)

        _run_mysqlsh_script.assert_called_once_with(
            expected_remove_instance_commands,
            user="serverconfig",
            password="serverconfigpassword",
            host="1.2.3.4:33062",
        )

    @patch("charms.mysql.v0.mysql.MySQLBase.get_cluster_node_count")
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
        _get_cluster_node_count,
    ):
        """Test with no exceptions while running the remove_instance() method."""
        _get_cluster_primary_address.side_effect = ["1.1.1.1", "2.2.2.2"]
        _acquire_lock.return_value = True
        _get_cluster_member_addresses.return_value = ("2.2.2.2", True)
        _get_cluster_node_count.return_value = 2

        self.mysql.remove_instance("mysql-0")

        expected_remove_instance_commands = (
            "cluster = dba.get_cluster('test_cluster')\n"
            "cluster.remove_instance('clusteradmin@127.0.0.1', "
            "{'password': 'clusteradminpassword', 'force': 'true'})"
        )

        self.assertEqual(_get_cluster_primary_address.call_count, 2)
        _acquire_lock.assert_called_once_with("1.1.1.1", "mysql-0", "unit-teardown")
        _get_cluster_member_addresses.assert_called_once_with(exclude_unit_labels=["mysql-0"])
        _run_mysqlsh_script.assert_called_once_with(
            expected_remove_instance_commands,
            user="serverconfig",
            password="serverconfigpassword",
            host="127.0.0.1:33062",
        )
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

    @patch("charms.mysql.v0.mysql.MySQLBase.get_cluster_node_count")
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
        _get_cluster_node_count,
    ):
        """Test an issue releasing locks while running the remove_instance() method."""
        _get_cluster_primary_address.side_effect = ["1.1.1.1", "2.2.2.2"]
        _acquire_lock.return_value = True
        _get_cluster_member_addresses.return_value = ("2.2.2.2", True)
        _release_lock.side_effect = MySQLClientError("Error on subprocess")
        _get_cluster_node_count.return_value = 2

        with self.assertRaises(MySQLRemoveInstanceError):
            self.mysql.remove_instance("mysql-0")

        expected_remove_instance_commands = (
            "cluster = dba.get_cluster('test_cluster')\n"
            "cluster.remove_instance('clusteradmin@127.0.0.1', "
            "{'password': 'clusteradminpassword', 'force': 'true'})"
        )

        self.assertEqual(_get_cluster_primary_address.call_count, 2)
        _acquire_lock.assert_called_once_with("1.1.1.1", "mysql-0", "unit-teardown")
        _get_cluster_member_addresses.assert_called_once_with(exclude_unit_labels=["mysql-0"])
        _run_mysqlsh_script.assert_called_once_with(
            expected_remove_instance_commands,
            user="serverconfig",
            password="serverconfigpassword",
            host="127.0.0.1:33062",
        )
        _release_lock.assert_called_once_with("2.2.2.2", "mysql-0", "unit-teardown")

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    def test_acquire_lock(self, _run_mysqlsh_script):
        """Test a successful execution of _acquire_lock()."""
        _run_mysqlsh_script.return_value = "<ACQUIRED_LOCK>1</ACQUIRED_LOCK>"

        acquired_lock = self.mysql._acquire_lock("1.1.1.1", "mysql-0", "unit-teardown")

        self.assertTrue(acquired_lock)

        expected_acquire_lock_commands = "\n".join([
            "session.run_sql(\"UPDATE mysql.juju_units_operations SET executor='mysql-0', status='in-progress' WHERE task='unit-teardown' AND executor='';\")",
            "acquired_lock = session.run_sql(\"SELECT count(*) FROM mysql.juju_units_operations WHERE task='unit-teardown' AND executor='mysql-0';\").fetch_one()[0]",
            "print(f'<ACQUIRED_LOCK>{acquired_lock}</ACQUIRED_LOCK>')",
        ])
        _run_mysqlsh_script.assert_called_once_with(
            expected_acquire_lock_commands,
            user="serverconfig",
            password="serverconfigpassword",
            host="1.1.1.1:33062",
        )

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

        expected_release_lock_commands = "\n".join([
            "r = session.run_sql(\"UPDATE mysql.juju_units_operations SET executor='', status='not-started' WHERE task='unit-teardown' AND executor='mysql-0';\")",
            "print(r.get_affected_items_count())",
        ])
        _run_mysqlsh_script.assert_called_once_with(
            expected_release_lock_commands,
            user="serverconfig",
            password="serverconfigpassword",
            host="2.2.2.2:33062",
        )

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    def test_get_cluster_member_addresses(self, _run_mysqlsh_script):
        """Test a successful execution of _get_cluster_member_addresses()."""
        _run_mysqlsh_script.return_value = "<MEMBER_ADDRESSES>1.1.1.1,2.2.2.2</MEMBER_ADDRESSES>"

        cluster_members, valid = self.mysql._get_cluster_member_addresses(
            exclude_unit_labels=["mysql-0"]
        )

        self.assertEqual(cluster_members, ["1.1.1.1", "2.2.2.2"])
        self.assertTrue(valid)

        expected_commands = "\n".join([
            "cluster = dba.get_cluster('test_cluster')",
            "member_addresses = ','.join([member['address'] for label, member in cluster.status()['defaultReplicaSet']['topology'].items() if label not in ['mysql-0']])",
            "print(f'<MEMBER_ADDRESSES>{member_addresses}</MEMBER_ADDRESSES>')",
        ])
        _run_mysqlsh_script.assert_called_once_with(
            expected_commands,
            user="serverconfig",
            password="serverconfigpassword",
            host="127.0.0.1:33062",
        )

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

        expected_commands = "\n".join([
            "shell.connect_to_primary()",
            "primary_address = shell.parse_uri(session.uri)['host']",
            "print(f'<PRIMARY_ADDRESS>{primary_address}</PRIMARY_ADDRESS>')",
        ])
        _run_mysqlsh_script.assert_called_once_with(
            expected_commands,
            user="serverconfig",
            password="serverconfigpassword",
            host="127.0.0.1:33062",
        )

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

        expected_commands = "\n".join([
            "shell.connect_to_primary()",
            "primary_address = shell.parse_uri(session.uri)['host']",
            "print(f'<PRIMARY_ADDRESS>{primary_address}</PRIMARY_ADDRESS>')",
        ])
        _run_mysqlsh_script.assert_called_once_with(
            expected_commands,
            user="serverconfig",
            password="serverconfigpassword",
            host="127.0.0.2:33062",
        )

    @patch("charms.mysql.v0.mysql.MySQLBase.cluster_metadata_exists", return_value=True)
    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    def test_is_instance_in_cluster(self, _run_mysqlsh_script, _cluster_metadata_exists):
        """Test a successful execution of is_instance_in_cluster() method."""
        _run_mysqlsh_script.return_value = "ONLINE"

        result = self.mysql.is_instance_in_cluster("mysql-0")
        self.assertTrue(result)

        expected_commands = "\n".join([
            "cluster = dba.get_cluster('test_cluster')",
            "print(cluster.status()['defaultReplicaSet']['topology'].get('mysql-0', {}).get('status', 'NOT_A_MEMBER'))",
        ])
        _run_mysqlsh_script.assert_called_once_with(
            expected_commands,
            user="serverconfig",
            password="serverconfigpassword",
            host="127.0.0.1:33062",
            exception_as_warning=True,
        )

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
        expected_commands = "\n".join((
            "cluster = dba.get_cluster('test_cluster')",
            "print(cluster.status({'extended': False}))",
        ))
        _run_mysqlsh_script.assert_called_once_with(
            expected_commands,
            user="serverconfig",
            password="serverconfigpassword",
            host="127.0.0.1:33062",
            timeout=30,
        )

    @patch("json.loads")
    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    def test_get_cluster_status_failure(self, _run_mysqlsh_script, _json_loads):
        """Test an exception executing get_cluster_status() method."""
        _run_mysqlsh_script.side_effect = MySQLClientError("Error on subprocess")

        self.mysql.get_cluster_status()
        _json_loads.assert_not_called()

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    def test_rescan_cluster(self, _run_mysqlsh_script):
        """Test a successful execution of rescan_cluster()."""
        self.mysql.rescan_cluster()
        expected_commands = "\n".join((
            "cluster = dba.get_cluster('test_cluster')",
            "cluster.rescan({})",
        ))
        _run_mysqlsh_script.assert_called_once_with(
            expected_commands,
            user="serverconfig",
            password="serverconfigpassword",
            host="127.0.0.1:33062",
        )

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    def test_set_instance_option(self, _run_mysqlsh_script):
        """Test execution of set_instance_option()."""
        expected_commands = "\n".join((
            f"cluster = dba.get_cluster('{self.mysql.cluster_name}')",
            f"cluster.set_instance_option('{self.mysql.instance_address}', 'label', 'label-0')",
        ))
        self.mysql.set_instance_option("label", "label-0")
        _run_mysqlsh_script.assert_called_once_with(
            expected_commands,
            user="serverconfig",
            password="serverconfigpassword",
            host="127.0.0.1:33062",
        )

        _run_mysqlsh_script.reset_mock()
        _run_mysqlsh_script.side_effect = MySQLClientError("Error on subprocess")
        with self.assertRaises(MySQLSetInstanceOptionError):
            self.mysql.set_instance_option("label", "label-0")

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlcli_script")
    def test_get_member_state(self, _run_mysqlcli_script):
        """Test execution of get_member_state()."""
        _run_mysqlcli_script.return_value = [
            ("ONLINE", "SECONDARY", "<uuid>", "<notuuid>"),
            ("ONLINE", "PRIMARY", "<uuid>", "<uuid>"),
        ]

        # disable tenacity retry
        self.mysql.get_member_state.retry.retry = tenacity.retry_if_not_result(lambda _: True)

        state = self.mysql.get_member_state()
        self.assertEqual(state, ("online", "primary"))
        _run_mysqlcli_script.return_value = [
            ("ONLINE", "SECONDARY", "<uuid>", "<uuid>"),
            ("ONLINE", "PRIMARY", "<uuid>", "<notuuid>"),
        ]

        state = self.mysql.get_member_state()
        self.assertEqual(state, ("online", "secondary"))

        _run_mysqlcli_script.return_value = [
            ("OFFLINE", "", "", "<uuid>"),
        ]

        state = self.mysql.get_member_state()
        self.assertEqual(state, ("offline", "unknown"))

        _run_mysqlcli_script.return_value = []

        with self.assertRaises(MySQLNoMemberStateError):
            self.mysql.get_member_state()

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    def test_rescan_cluster_failure(self, _run_mysqlsh_script):
        """Test an exception executing rescan_cluster()."""
        _run_mysqlsh_script.side_effect = MySQLClientError("Error on subprocess")

        with self.assertRaises(MySQLRescanClusterError):
            self.mysql.rescan_cluster()

    def test_error(self):
        """Test Error class."""
        error = Error("Error message")

        self.assertEqual(error.__repr__(), "<charms.mysql.v0.mysql.Error ('Error message',)>")
        self.assertEqual(error.name, "<charms.mysql.v0.mysql.Error>")
        self.assertEqual(error.message, "Error message")

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    def test_delete_users_for_unit_failure(self, _run_mysqlsh_script):
        """Test failure to delete users for unit."""
        _run_mysqlsh_script.side_effect = MySQLClientError

        with self.assertRaises(MySQLDeleteUsersForUnitError):
            self.mysql.delete_users_for_unit("foouser")

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    def test_delete_users_for_relation_failure(self, _run_mysqlsh_script):
        """Test failure to delete users for relation."""
        _run_mysqlsh_script.side_effect = MySQLClientError

        with self.assertRaises(MySQLDeleteUsersForRelationError):
            self.mysql.delete_users_for_relation("foouser")

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    def test_delete_user(self, _run_mysqlsh_script):
        """Test delete_user() method."""
        expected_commands = "\n".join((
            "shell.connect_to_primary()",
            "session.run_sql(\"DROP USER `testuser`@'%'\")",
        ))
        self.mysql.delete_user("testuser")
        _run_mysqlsh_script.assert_called_once_with(
            expected_commands,
            user="serverconfig",
            password="serverconfigpassword",
            host="127.0.0.1:33062",
        )

        _run_mysqlsh_script.side_effect = MySQLClientError
        with self.assertRaises(MySQLDeleteUserError):
            self.mysql.delete_user("testuser")

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    def test_promote_cluster_to_primary(self, _run_mysqlsh_script):
        """Test promote_cluster_to_primary() method."""
        self.mysql.promote_cluster_to_primary("test_cluster")
        expected_commands = "\n".join((
            "shell.connect_to_primary()",
            "cs = dba.get_cluster_set()",
            "cs.set_primary_cluster('test_cluster')",
        ))

        _run_mysqlsh_script.assert_called_once_with(
            expected_commands,
            user="serverconfig",
            password="serverconfigpassword",
            host="127.0.0.1:33062",
        )

        _run_mysqlsh_script.side_effect = MySQLClientError
        with self.assertRaises(MySQLPromoteClusterToPrimaryError):
            self.mysql.promote_cluster_to_primary("test_cluster")

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    def test_get_mysql_version(self, _run_mysqlsh_script):
        """Test get_mysql_version() method."""
        _run_mysqlsh_script.return_value = "<VERSION>8.0.29-0ubuntu0.20.04.3</VERSION>"

        version = self.mysql.get_mysql_version()
        expected_commands = "\n".join((
            'result = session.run_sql("SELECT version()")',
            'print(f"<VERSION>{result.fetch_one()[0]}</VERSION>")',
        ))

        _run_mysqlsh_script.assert_called_once_with(
            expected_commands,
            user="serverconfig",
            password="serverconfigpassword",
            host="127.0.0.1:33062",
        )

        self.assertEqual(version, "8.0.29-0ubuntu0.20.04.3")

        _run_mysqlsh_script.side_effect = MySQLClientError
        with self.assertRaises(MySQLGetMySQLVersionError):
            self.mysql.get_mysql_version()

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    def test_grant_privileges_to_user(self, _run_mysqlsh_script):
        """Test the successful execution of grant_privileges_to_user."""
        expected_commands = "\n".join((
            "shell.connect_to_primary()",
            "session.run_sql(\"GRANT CREATE USER ON *.* TO 'test_user'@'%' WITH GRANT OPTION\")",
        ))

        self.mysql.grant_privileges_to_user(
            "test_user", "%", ["CREATE USER"], with_grant_option=True
        )

        _run_mysqlsh_script.assert_called_with(
            expected_commands,
            user="serverconfig",
            password="serverconfigpassword",
            host="127.0.0.1:33062",
        )

        _run_mysqlsh_script.reset_mock()

        expected_commands = "\n".join((
            "shell.connect_to_primary()",
            "session.run_sql(\"GRANT SELECT, UPDATE ON *.* TO 'test_user'@'%'\")",
        ))

        self.mysql.grant_privileges_to_user("test_user", "%", ["SELECT", "UPDATE"])

        _run_mysqlsh_script.assert_called_with(
            expected_commands,
            user="serverconfig",
            password="serverconfigpassword",
            host="127.0.0.1:33062",
        )

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    def test_update_user_password(self, _run_mysqlsh_script):
        """Test the successful execution of update_user_password."""
        _run_mysqlsh_script.return_value = "<PRIMARY_ADDRESS>1.1.1.1</PRIMARY_ADDRESS>"

        self.mysql.update_user_password("test_user", "test_password")
        expected_commands = "\n".join((
            "session.run_sql(\"ALTER USER 'test_user'@'%' IDENTIFIED BY 'test_password';\")",
            'session.run_sql("FLUSH PRIVILEGES;")',
        ))

        _run_mysqlsh_script.assert_called_with(
            expected_commands,
            user="serverconfig",
            password="serverconfigpassword",
            host="1.1.1.1:33062",
        )

    @patch("charms.mysql.v0.mysql.MySQLBase.is_cluster_replica", return_value=False)
    @patch("charms.mysql.v0.mysql.MySQLBase.get_cluster_status", return_value=SHORT_CLUSTER_STATUS)
    def test_get_cluster_endpoints(self, _, _is_cluster_replica):
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
    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlcli_script")
    def test_cluster_metadata_exists(self, _run_mysqlcli_script, _run_mysqlsh_script):
        """Test cluster_metadata_exists method."""
        commands = "\n".join((
            "result = session.run_sql(\"SHOW DATABASES LIKE 'mysql_innodb_cluster_metadata'\")",
            "content = result.fetch_all()",
            "if content:",
            (
                '  result = session.run_sql("SELECT cluster_name FROM mysql_innodb_cluster_metadata'
                f".clusters where cluster_name = '{self.mysql.cluster_name}';\")"
            ),
            "  print(bool(result.fetch_one()))",
            "else:",
            "  print(False)",
        ))

        _run_mysqlsh_script.return_value = "True\n"

        self.assertTrue(self.mysql.cluster_metadata_exists("1.2.3.4"))
        _run_mysqlsh_script.assert_called_once_with(
            commands,
            user="serverconfig",
            password="serverconfigpassword",
            host="1.2.3.4:33062",
            timeout=60,
            exception_as_warning=True,
        )
        _run_mysqlcli_script.assert_not_called()

        _run_mysqlsh_script.reset_mock()
        _run_mysqlsh_script.side_effect = MySQLClientError
        with self.assertRaises(MySQLClusterMetadataExistsError):
            self.mysql.cluster_metadata_exists("1.2.3.4")

        _run_mysqlsh_script.reset_mock()

        query = (
            "SELECT cluster_name "
            "FROM mysql_innodb_cluster_metadata.clusters "
            "WHERE EXISTS "
            "("
            "SELECT * "
            "FROM information_schema.schemata "
            "WHERE schema_name = 'mysql_innodb_cluster_metadata'"
            ")",
        )

        _run_mysqlcli_script.return_value = [[self.mysql.cluster_name]]

        self.assertTrue(self.mysql.cluster_metadata_exists())
        _run_mysqlsh_script.assert_not_called()
        _run_mysqlcli_script.assert_called_once_with(
            query,
            user="root",
            password="password",
            timeout=60,
            exception_as_warning=True,
        )

        _run_mysqlcli_script.reset_mock()
        _run_mysqlcli_script.side_effect = MySQLClientError
        with self.assertRaises(MySQLClusterMetadataExistsError):
            self.mysql.cluster_metadata_exists()

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    def test_offline_mode_and_hidden_instance_exists(self, _run_mysqlsh_script):
        """Test the offline_mode_and_hidden_instance_exists() method."""
        commands = (
            "cluster_topology = dba.get_cluster('test_cluster').status()['defaultReplicaSet']['topology']",
            "selected_instances = [label for label, member in cluster_topology.items() if 'Instance has offline_mode enabled' in member.get('instanceErrors', '') and member.get('hiddenFromRouter')]",
            "print(f'<OFFLINE_MODE_INSTANCES>{len(selected_instances)}</OFFLINE_MODE_INSTANCES>')",
        )

        _run_mysqlsh_script.return_value = "<OFFLINE_MODE_INSTANCES>1</OFFLINE_MODE_INSTANCES>"

        exists = self.mysql.offline_mode_and_hidden_instance_exists()
        self.assertTrue(exists)
        _run_mysqlsh_script.assert_called_once_with(
            "\n".join(commands),
            user="serverconfig",
            password="serverconfigpassword",
            host="127.0.0.1:33062",
        )

        _run_mysqlsh_script.reset_mock()
        _run_mysqlsh_script.return_value = "<OFFLINE_MODE_INSTANCES>0</OFFLINE_MODE_INSTANCES>"

        exists = self.mysql.offline_mode_and_hidden_instance_exists()
        self.assertFalse(exists)
        _run_mysqlsh_script.assert_called_once_with(
            "\n".join(commands),
            user="serverconfig",
            password="serverconfigpassword",
            host="127.0.0.1:33062",
        )

        _run_mysqlsh_script.reset_mock()
        _run_mysqlsh_script.side_effect = MySQLClientError()

        with self.assertRaises(MySQLOfflineModeAndHiddenInstanceExistsError):
            self.mysql.offline_mode_and_hidden_instance_exists()

        _run_mysqlsh_script.reset_mock()
        _run_mysqlsh_script.return_value = "garbage"

        with self.assertRaises(MySQLOfflineModeAndHiddenInstanceExistsError):
            self.mysql.offline_mode_and_hidden_instance_exists()

    def test_get_innodb_buffer_pool_parameters(self):
        """Test the successful execution of get_innodb_buffer_pool_parameters()."""
        available_memory = 16484458496

        pool_size, chunk_size, gr_message_cache = self.mysql.get_innodb_buffer_pool_parameters(
            available_memory
        )
        self.assertEqual(11408506880, pool_size)
        self.assertEqual(1426063360, chunk_size)
        self.assertEqual(None, gr_message_cache)

        available_memory = 3221000000
        pool_size, chunk_size, gr_message_cache = self.mysql.get_innodb_buffer_pool_parameters(
            available_memory
        )
        self.assertEqual(1342177280, pool_size)
        self.assertEqual(167772160, chunk_size)
        self.assertEqual(None, gr_message_cache)

        available_memory = 1073741825
        pool_size, chunk_size, gr_message_cache = self.mysql.get_innodb_buffer_pool_parameters(
            available_memory
        )
        self.assertEqual(536870912, pool_size)
        self.assertIsNone(chunk_size)
        self.assertEqual(134217728, gr_message_cache)

    def test_get_innodb_buffer_pool_parameters_exception(self):
        """Test a failure in execution of get_innodb_buffer_pool_parameters()."""
        with self.assertRaises(MySQLGetAutoTuningParametersError):
            self.mysql.get_innodb_buffer_pool_parameters("wrong type")

    def test_get_max_connections(self):
        self.assertEqual(1310, self.mysql.get_max_connections(16484458496))

        with self.assertRaises(MySQLGetAutoTuningParametersError):
            self.mysql.get_max_connections(12582910)

        with self.assertRaises(MySQLGetAutoTuningParametersError):
            self.mysql.get_max_connections(125)

    @patch("charms.mysql.v0.mysql.MySQLBase._execute_commands")
    def test_execute_backup_commands(self, _execute_commands):
        """Test successful execution of execute_backup_commands()."""
        _execute_commands.side_effect = [
            ("16", None),
            ("/tmp/base/directory/xtra_backup_ABCD", None),
            ("stdout", "stderr"),
        ]

        stdout, stderr = self.mysql.execute_backup_commands(
            "s3_directory",
            {
                "path": "s3_path",
                "region": "s3_region",
                "bucket": "s3_bucket",
                "access-key": "s3_access_key",
                "secret-key": "s3_secret_key",
                "endpoint": "s3_endpoint",
                "s3-api-version": "s3_api_version",
                "s3-uri-style": "s3_uri_style",
            },
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
        _expected_xtrabackup_commands = [
            "/xtrabackup/location --defaults-file=/defaults/file.cnf",
            "--defaults-group=mysqld",
            "--no-version-check",
            "--parallel=16",
            "--user=backups",
            "--password=backupspassword",
            "--socket=/mysqld/socket/file.sock",
            "--lock-ddl",
            "--backup",
            "--stream=xbstream",
            "--xtrabackup-plugin-dir=/xtrabackup/plugin/dir",
            "--target-dir=/tmp/base/directory/xtra_backup_ABCD",
            "--no-server-version-check",
            "| /xbcloud/location put",
            "--curl-retriable-errors=7",
            "--insecure",
            "--parallel=10",
            "--md5",
            "--storage=S3",
            "--s3-region=s3_region",
            "--s3-bucket=s3_bucket",
            "--s3-endpoint=s3_endpoint",
            "--s3-api-version=s3_api_version",
            "--s3-bucket-lookup=s3_uri_style",
            "s3_directory",
        ]

        self.assertEqual(
            sorted(_execute_commands.mock_calls),
            sorted([
                call(_expected_nproc_commands),
                call(_expected_tmp_dir_commands, user="test_user", group="test_group"),
                call(
                    _expected_xtrabackup_commands,
                    bash=True,
                    user="test_user",
                    group="test_group",
                    env_extra={
                        "ACCESS_KEY_ID": "s3_access_key",
                        "SECRET_ACCESS_KEY": "s3_secret_key",
                    },
                    stream_output="stderr",
                ),
            ]),
        )

    @patch("charms.mysql.v0.mysql.MySQLBase._execute_commands")
    def test_execute_backup_commands_exceptions(self, _execute_commands):
        """Test a failure in the execution of execute_backup_commands()."""
        _execute_commands.side_effect = MySQLExecError("failure")

        args = [
            "s3_directory",
            {
                "path": "s3_path",
                "region": "s3_region",
                "bucket": "s3_bucket",
                "access-key": "s3_access_key",
                "secret-key": "s3_secret_key",
                "endpoint": "s3_endpoint",
                "s3-api-version": "s3_api_version",
                "s3-uri-style": "s3_uri_style",
            },
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
            "backup-id",
            {
                "path": "s3_path",
                "region": "s3_region",
                "bucket": "s3_bucket",
                "access-key": "s3_access_key",
                "secret-key": "s3_secret_key",
                "endpoint": "s3_endpoint",
                "s3-api-version": "s3_api_version",
                "s3-uri-style": "s3_uri_style",
            },
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
        _expected_retrieve_backup_commands = [
            "xbcloud/location get",
            "--curl-retriable-errors=7",
            "--parallel=10",
            "--storage=S3",
            "--s3-region=s3_region",
            "--s3-bucket=s3_bucket",
            "--s3-endpoint=s3_endpoint",
            "--s3-bucket-lookup=s3_uri_style",
            "--s3-api-version=s3_api_version",
            "s3_path/backup-id",
            "| xbstream/location",
            "--decompress",
            "-x",
            "-C mysql/data/directory/#mysql_sst_ABCD",
            "--parallel=16",
        ]

        self.assertEqual(
            sorted(_execute_commands.mock_calls),
            sorted([
                call(_expected_nproc_commands),
                call(_expected_temp_dir_commands, user="test-user", group="test-group"),
                call(
                    _expected_retrieve_backup_commands,
                    bash=True,
                    env_extra={
                        "ACCESS_KEY_ID": "s3_access_key",
                        "SECRET_ACCESS_KEY": "s3_secret_key",
                    },
                    user="test-user",
                    group="test-group",
                    stream_output="stderr",
                ),
            ]),
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
                "backup-id",
                {
                    "path": "s3_path",
                    "region": "s3_region",
                    "bucket": "s3_bucket",
                    "access-key": "s3_access_key",
                    "secret-key": "s3_secret_key",
                    "endpoint": "s3_endpoint",
                    "s3-api-version": "s3_api_version",
                    "s3-uri-style": "s3_uri_style",
                },
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
                "backup-id",
                {
                    "path": "s3_path",
                    "region": "s3_region",
                    "bucket": "s3_bucket",
                    "access-key": "s3_access_key",
                    "secret-key": "s3_secret_key",
                    "endpoint": "s3_endpoint",
                    "s3-api-version": "s3_api_version",
                    "s3-uri-style": "s3_uri_style",
                },
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
                "backup-id",
                {
                    "path": "s3_path",
                    "region": "s3_region",
                    "bucket": "s3_bucket",
                    "access-key": "s3_access_key",
                    "secret-key": "s3_secret_key",
                    "endpoint": "s3_endpoint",
                    "s3-api-version": "s3_api_version",
                    "s3-uri-style": "s3_uri_style",
                },
                "mysql/data/directory",
                "xbcloud/location",
                "xbstream/location",
                user="test-user",
                group="test-group",
            )

    @patch(
        "charms.mysql.v0.mysql.MySQLBase.get_innodb_buffer_pool_parameters",
        return_value=(1234, 5678, None),
    )
    @patch("charms.mysql.v0.mysql.MySQLBase.get_available_memory")
    @patch("charms.mysql.v0.mysql.MySQLBase._execute_commands")
    def test_prepare_backup_for_restore(
        self,
        _execute_commands,
        _get_available_memory,
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
        _get_available_memory.assert_called_once()
        _execute_commands.assert_called_once_with(
            _expected_prepare_backup_command,
            user="test-user",
            group="test-group",
        )

    @patch(
        "charms.mysql.v0.mysql.MySQLBase.get_innodb_buffer_pool_parameters",
        return_value=(1234, 5678, None),
    )
    @patch("charms.mysql.v0.mysql.MySQLBase.get_available_memory")
    @patch("charms.mysql.v0.mysql.MySQLBase._execute_commands")
    def test_prepare_backup_for_restore_failure(
        self,
        _execute_commands,
        _get_available_memory,
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

        _get_innodb_buffer_pool_parameters.side_effect = MySQLGetAutoTuningParametersError()
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

        _expected_commands = [
            "find",
            "mysql/data/directory",
            "-not",
            "-path",
            "mysql/data/directory/#mysql_sst_*",
            "-not",
            "-path",
            "mysql/data/directory",
            "-delete",
        ]

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
            "SET PERSIST ssl_ca='ca_path'",
            "SET PERSIST ssl_key='key_path'",
            "SET PERSIST ssl_cert='cert_path'",
            "SET PERSIST require_secure_transport=on",
            "ALTER INSTANCE RELOAD TLS",
        )

        self.mysql.tls_setup("ca_path", "key_path", "cert_path", True)

        _run_mysqlcli_script.assert_called_with(
            commands,
            user=self.mysql.server_config_user,
            password=self.mysql.server_config_password,
        )

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlcli_script")
    def test_tls_restore_default(self, _run_mysqlcli_script):
        """Test the successful execution of tls_set_custom."""
        commands = (
            "SET PERSIST ssl_ca='ca.pem'",
            "SET PERSIST ssl_key='server-key.pem'",
            "SET PERSIST ssl_cert='server-cert.pem'",
            "SET PERSIST require_secure_transport=off",
            "ALTER INSTANCE RELOAD TLS",
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

        _run_mysqlsh_script.assert_called_with(
            "\n".join(commands),
            user="serverconfig",
            password="serverconfigpassword",
            host="127.0.0.1:33062",
        )

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    def test_are_locks_acquired(self, _run_mysqlsh_script):
        """Test are_locks_acquired."""
        commands = (
            "result = session.run_sql(\"SELECT COUNT(*) FROM mysql.juju_units_operations WHERE status='in-progress';\")",
            "print(f'<LOCKS>{result.fetch_one()[0]}</LOCKS>')",
        )
        _run_mysqlsh_script.return_value = "<LOCKS>0</LOCKS>"
        assert self.mysql.are_locks_acquired() is False
        _run_mysqlsh_script.assert_called_with(
            "\n".join(commands),
            user="serverconfig",
            password="serverconfigpassword",
            host="127.0.0.1:33062",
        )

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    def test_get_mysql_user_for_unit(self, _run_mysqlsh_script):
        """Test get_mysql_user_for_unit."""
        commands = (
            "result = session.run_sql(\"SELECT USER, ATTRIBUTE->>'$.router_id' FROM "
            "INFORMATION_SCHEMA.USER_ATTRIBUTES WHERE ATTRIBUTE->'$.created_by_user'='relation-1' AND"
            " ATTRIBUTE->'$.created_by_juju_unit'='mysql-router-k8s/0'\")",
            "print(result.fetch_all())",
        )
        _run_mysqlsh_script.return_value = (
            '[["mysql_router1_znpcqeg7zp2v",'
            ' "mysql-router-k8s-0.mysql-router-k8s-endpoints.novo.svc.cluster.local::system"]]'
        )
        self.mysql.get_mysql_router_users_for_unit(
            relation_id=1, mysql_router_unit_name="mysql-router-k8s/0"
        )
        _run_mysqlsh_script.assert_called_with(
            "\n".join(commands),
            user="serverconfig",
            password="serverconfigpassword",
            host="127.0.0.1:33062",
        )
        _run_mysqlsh_script.reset_mock()
        _run_mysqlsh_script.side_effect = MySQLClientError
        with self.assertRaises(MySQLGetRouterUsersError):
            self.mysql.get_mysql_router_users_for_unit(
                relation_id=1, mysql_router_unit_name="mysql-router-k8s/0"
            )

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    def test_remove_router_from_cluster_metadata(self, _run_mysqlsh_script):
        """Test remove_user_from_cluster_metadata."""
        commands = (
            "cluster = dba.get_cluster()",
            'cluster.remove_router_metadata("1")',
        )

        self.mysql.remove_router_from_cluster_metadata(router_id="1")
        _run_mysqlsh_script.assert_called_with(
            "\n".join(commands),
            user="serverconfig",
            password="serverconfigpassword",
            host="127.0.0.1:33062",
        )
        _run_mysqlsh_script.reset_mock()
        _run_mysqlsh_script.side_effect = MySQLClientError

        with self.assertRaises(MySQLRemoveRouterFromMetadataError):
            self.mysql.remove_router_from_cluster_metadata(router_id="1")

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    def test_set_dynamic_variables(self, _run_mysqlsh_script):
        """Test dynamic_variables."""
        commands = ('session.run_sql("SET GLOBAL variable=value")',)
        self.mysql.set_dynamic_variable(variable="variable", value="value")
        _run_mysqlsh_script.assert_called_with(
            "\n".join(commands),
            user="serverconfig",
            password="serverconfigpassword",
            host="127.0.0.1:33062",
        )

        commands = ('session.run_sql("SET GLOBAL variable=`/a/path/value`")',)
        self.mysql.set_dynamic_variable(variable="variable", value="/a/path/value")
        _run_mysqlsh_script.assert_called_with(
            "\n".join(commands),
            user="serverconfig",
            password="serverconfigpassword",
            host="127.0.0.1:33062",
        )

        _run_mysqlsh_script.reset_mock()
        _run_mysqlsh_script.side_effect = MySQLClientError

        with self.assertRaises(MySQLSetVariableError):
            self.mysql.set_dynamic_variable(variable="variable", value="value")

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    def test_get_variable_value(self, _run_mysqlsh_script):
        """Test get_variable_value."""
        _run_mysqlsh_script.return_value = '[["super_read_only", "OFF"]]'

        self.assertEqual(self.mysql.get_variable_value("super_read_only"), "OFF")

        _run_mysqlsh_script.reset_mock()
        _run_mysqlsh_script.side_effect = MySQLClientError

        with self.assertRaises(MySQLGetVariableError):
            self.mysql.get_variable_value("variable")

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    def test_set_cluster_primary(self, _run_mysqlsh_script):
        """Test set_cluster_primary."""
        commands = (
            "shell.connect_to_primary()",
            "cluster = dba.get_cluster('test_cluster')",
            "cluster.set_primary_instance('test')",
        )
        self.mysql.set_cluster_primary("test")
        _run_mysqlsh_script.assert_called_with(
            "\n".join(commands),
            user="serverconfig",
            password="serverconfigpassword",
            host="127.0.0.1:33062",
        )

        _run_mysqlsh_script.reset_mock()
        _run_mysqlsh_script.side_effect = MySQLClientError("Error")
        with self.assertRaises(MySQLSetClusterPrimaryError):
            self.mysql.set_cluster_primary(new_primary_address="10.0.0.2")

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    def test_verify_server_upgradable(self, _run_mysqlsh_script):
        """Test is_server_upgradable."""
        commands = (
            "try:\n    util.check_for_server_upgrade(options={'outputFormat': 'JSON'})",
            "except ValueError:",
            "    if session.run_sql('select @@version').fetch_all()[0][0].split('-')[0] in shell.version:",
            "        print('SAME_VERSION')",
            "    else:",
            "        raise",
        )
        _run_mysqlsh_script.return_value = (
            "Some info header to be stripped\n"
            '{"serverAddress": "10.1.148.145:33060",'
            '"serverVersion": "8.0.32-0ubuntu0.22.04.2 - (Ubuntu)",'
            '"targetVersion": "8.0.34",'
            '"errorCount": 0,'
            '"warningCount": 0,'
            '"noticeCount": 0,'
            '"summary": "No known compatibility errors or issues were found.",'
            '"checksPerformed": ['
            '{"id": "checkTableOutput",'
            '"title": "Issues reported by \'check table x for upgrade\' command",'
            '"status": "OK",'
            '"detectedProblems": [] }],'
            '"manualChecks": []}'
        )
        self.mysql.verify_server_upgradable("2.3.4.5")
        _run_mysqlsh_script.assert_called_with(
            "\n".join(commands),
            user="serverconfig",
            password="serverconfigpassword",
            host="2.3.4.5:33062",
        )

        _run_mysqlsh_script.return_value = (
            '{"serverAddress": "10.1.148.145:33060",'
            '"serverVersion": "8.0.32-0ubuntu0.22.04.2 - (Ubuntu)",'
            '"targetVersion": "8.0.34",'
            '"errorCount": 2,'
            '"warningCount": 0,'
            '"noticeCount": 0,'
            '"summary": "No known compatibility errors or issues were found.",'
            '"checksPerformed": ['
            '{"id": "checkTableOutput",'
            '"title": "Issues reported by \'check table x for upgrade\' command",'
            '"status": "OK",'
            '"detectedProblems": [] }],'
            '"manualChecks": []}'
        )
        with self.assertRaises(MySQLServerNotUpgradableError):
            self.mysql.verify_server_upgradable()

    @patch("charms.mysql.v0.mysql.MySQLBase.get_cluster_status")
    def test_get_primary_label(self, _get_cluster_status):
        """Test get_primary_label."""
        _get_cluster_status.return_value = SHORT_CLUSTER_STATUS

        self.assertEqual(self.mysql.get_primary_label(), "mysql-k8s-1")

    @patch("charms.mysql.v0.mysql.MySQLBase.get_cluster_status")
    def test_is_unit_primary(self, _get_cluster_status):
        """Test is_unit_primary."""
        _get_cluster_status.return_value = SHORT_CLUSTER_STATUS

        self.assertTrue(self.mysql.is_unit_primary("mysql-k8s-1"))
        self.assertFalse(self.mysql.is_unit_primary("mysql-k8s-2"))

    @patch("charms.mysql.v0.mysql.RECOVERY_CHECK_TIME", 0.1)
    @patch("charms.mysql.v0.mysql.MySQLBase.get_member_state")
    def test_hold_if_recovering(self, mock_get_member_state):
        """Test hold_if_recovering."""
        mock_get_member_state.return_value = ("online", "primary")
        self.mysql.hold_if_recovering()
        self.assertEqual(mock_get_member_state.call_count, 1)

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlcli_script")
    def test_set_instance_offline_mode(self, _run_mysqlsh_script):
        """Test execution of set_instance_offline_mode()."""
        self.mysql.set_instance_offline_mode(True)

        _run_mysqlsh_script.assert_called_once_with(
            ("SET @@GLOBAL.offline_mode = ON",),
            user="serverconfig",
            password="serverconfigpassword",
        )

        _run_mysqlsh_script.reset_mock()

        _run_mysqlsh_script.side_effect = MySQLClientError("Error on subprocess")
        with self.assertRaises(MySQLSetInstanceOfflineModeError):
            self.mysql.set_instance_offline_mode(True)

    @patch("charms.mysql.v0.mysql.MySQLBase.get_available_memory")
    def test_render_mysqld_configuration(self, _get_available_memory):
        """Test render_mysqld_configuration."""
        # 32GB of memory, production profile
        _get_available_memory.return_value = 32341442560

        expected_config = {
            "bind-address": "0.0.0.0",
            "mysqlx-bind-address": "0.0.0.0",
            "admin_address": "127.0.0.1",
            "report_host": "127.0.0.1",
            "max_connections": "724",
            "innodb_buffer_pool_size": "23219666944",
            "log_error_services": "log_filter_internal;log_sink_internal",
            "log_error": "/var/log/mysql/error.log",
            "general_log": "OFF",
            "general_log_file": "/var/log/mysql/general.log",
            "slow_query_log_file": "/var/log/mysql/slow.log",
            "binlog_expire_logs_seconds": "604800",
            "loose-audit_log_format": "JSON",
            "loose-audit_log_policy": "LOGINS",
            "loose-audit_log_strategy": "ASYNCHRONOUS",
            "loose-audit_log_file": "/var/log/mysql/audit.log",
            "innodb_buffer_pool_chunk_size": "2902458368",
        }
        self.maxDiff = None

        _, rendered_config = self.mysql.render_mysqld_configuration(
            profile="production",
            binlog_retention_days=7,
            audit_log_enabled=True,
            audit_log_strategy="async",
            audit_log_policy="LOGINS",
        )
        self.assertEqual(rendered_config, expected_config)

        # < 2GB of memory, production profile
        memory_limit = 2147483600

        expected_config["innodb_buffer_pool_size"] = "536870912"
        del expected_config["innodb_buffer_pool_chunk_size"]
        expected_config["performance-schema-instrument"] = "'memory/%=OFF'"
        expected_config["max_connections"] = "127"

        _, rendered_config = self.mysql.render_mysqld_configuration(
            profile="production",
            binlog_retention_days=7,
            audit_log_enabled=True,
            audit_log_strategy="async",
            audit_log_policy="LOGINS",
            memory_limit=memory_limit,
        )
        self.assertEqual(rendered_config, expected_config)

        # testing profile
        expected_config["innodb_buffer_pool_size"] = "20971520"
        expected_config["innodb_buffer_pool_chunk_size"] = "1048576"
        expected_config["loose-group_replication_message_cache_size"] = "134217728"
        expected_config["max_connections"] = "100"

        _, rendered_config = self.mysql.render_mysqld_configuration(
            profile="testing",
            binlog_retention_days=7,
            audit_log_enabled=True,
            audit_log_strategy="async",
            audit_log_policy="LOGINS",
        )
        self.assertEqual(rendered_config, expected_config)

        # 10GB, max connections set by value
        memory_limit = 10106700800
        # max_connections set
        _, rendered_config = self.mysql.render_mysqld_configuration(
            profile="production",
            binlog_retention_days=7,
            audit_log_enabled=True,
            audit_log_strategy="async",
            audit_log_policy="LOGINS",
            experimental_max_connections=500,
            memory_limit=memory_limit,
        )

        self.assertEqual(rendered_config["max_connections"], "500")

        # max_connections set,constrained by memory, but enforced
        _, rendered_config = self.mysql.render_mysqld_configuration(
            profile="production",
            binlog_retention_days=7,
            audit_log_enabled=True,
            audit_log_strategy="async",
            audit_log_policy="LOGINS",
            experimental_max_connections=800,
            memory_limit=memory_limit,
        )

        self.assertEqual(rendered_config["max_connections"], "800")

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    def test_create_replica_cluster(self, _run_mysqlsh_script):
        """Test create_replica_cluster."""
        endpoint = "address:3306"
        replica_cluster_name = "replica_cluster"
        instance_label = "label"
        method = "auto"
        options = {
            "recoveryProgress": 0,
            "recoveryMethod": method,
            "timeout": 0,
            "communicationStack": "MySQL",
        }
        commands = (
            "shell.connect_to_primary()",
            "cs = dba.get_cluster_set()",
            f"repl_cluster = cs.create_replica_cluster('{endpoint}','{replica_cluster_name}', {options})",
            f"repl_cluster.set_instance_option('{endpoint}', 'label', '{instance_label}')",
        )
        self.mysql.create_replica_cluster(
            endpoint,
            replica_cluster_name,
            instance_label,
        )
        _run_mysqlsh_script.assert_called_with(
            "\n".join(commands),
            user="serverconfig",
            password="serverconfigpassword",
            host="127.0.0.1:33062",
            exception_as_warning=True,
        )

        _run_mysqlsh_script.reset_mock()
        _run_mysqlsh_script.side_effect = MySQLClientError

        with self.assertRaises(MySQLCreateReplicaClusterError):
            self.mysql.create_replica_cluster(
                endpoint,
                replica_cluster_name,
                instance_label,
            )

        options["recoveryMethod"] = "clone"
        commands2 = (
            "shell.connect_to_primary()",
            "cs = dba.get_cluster_set()",
            f"repl_cluster = cs.create_replica_cluster('{endpoint}','{replica_cluster_name}', {options})",
            f"repl_cluster.set_instance_option('{endpoint}', 'label', '{instance_label}')",
        )
        _run_mysqlsh_script.assert_has_calls([
            call(
                "\n".join(commands),
                user="serverconfig",
                password="serverconfigpassword",
                host="127.0.0.1:33062",
                exception_as_warning=True,
            ),
            call(
                "\n".join(commands2),
                user="serverconfig",
                password="serverconfigpassword",
                host="127.0.0.1:33062",
                exception_as_warning=False,
            ),
        ])

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    def test_remove_replica_cluster(self, _run_mysqlsh_script):
        """Test remove_replica_cluster."""
        replica_cluster_name = "replica_cluster"
        commands = [
            "shell.connect_to_primary()",
            "cs = dba.get_cluster_set()",
            f"cs.remove_cluster('{replica_cluster_name}')",
        ]
        self.mysql.remove_replica_cluster(replica_cluster_name)
        _run_mysqlsh_script.assert_called_with(
            "\n".join(commands),
            user="serverconfig",
            password="serverconfigpassword",
            host="127.0.0.1:33062",
        )

        _run_mysqlsh_script.reset_mock()
        commands[2] = f"cs.remove_cluster('{replica_cluster_name}', {{'force': True}})"
        self.mysql.remove_replica_cluster(replica_cluster_name, force=True)
        _run_mysqlsh_script.assert_called_with(
            "\n".join(commands),
            user="serverconfig",
            password="serverconfigpassword",
            host="127.0.0.1:33062",
        )

        _run_mysqlsh_script.reset_mock()
        _run_mysqlsh_script.side_effect = MySQLClientError

        with self.assertRaises(MySQLRemoveReplicaClusterError):
            self.mysql.remove_replica_cluster(replica_cluster_name)

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    def test_get_replica_cluster_status(self, _run_mysqlsh_script):
        """Test get_replica_cluster_status."""
        replica_cluster_name = "replica_cluster"
        _run_mysqlsh_script.return_value = "OK "
        status = self.mysql.get_replica_cluster_status(replica_cluster_name)
        self.assertEqual(status, "ok")

        _run_mysqlsh_script.side_effect = MySQLClientError
        status = self.mysql.get_replica_cluster_status(replica_cluster_name)
        self.assertEqual(status, "unknown")

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    def test_get_cluster_node_count(self, _run_mysqlsh_script):
        """Test get_cluster_node_count."""
        _run_mysqlsh_script.return_value = "<NODES>2</NODES>"
        count = self.mysql.get_cluster_node_count()
        self.assertEqual(count, 2)

        _run_mysqlsh_script.side_effect = MySQLClientError
        count = self.mysql.get_cluster_node_count()
        self.assertEqual(count, 0)

        query = (
            "SELECT COUNT(*) FROM performance_schema.replication_group_members"
            " WHERE member_state = 'ONLINE'"
        )
        commands = (
            f'result = session.run_sql("{query}")',
            'print(f"<NODES>{result.fetch_one()[0]}</NODES>")',
        )
        self.mysql.get_cluster_node_count(node_status=MySQLMemberState.ONLINE)
        _run_mysqlsh_script.assert_called_with(
            "\n".join(commands),
            user="serverconfig",
            password="serverconfigpassword",
            host="127.0.0.1:33062",
            timeout=30,
            exception_as_warning=True,
        )

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    def test_get_cluster_set_global_primary(self, _run_mysqlsh_script):
        """Test get_cluster_set_global_primary."""
        _run_mysqlsh_script.return_value = "<PRIMARY_ADDRESS>mysql-k8s-1</PRIMARY_ADDRESS>"
        primary = self.mysql.get_cluster_set_global_primary_address()
        self.assertEqual(primary, "mysql-k8s-1")

        _run_mysqlsh_script.side_effect = MySQLClientError
        with self.assertRaises(MySQLGetClusterPrimaryAddressError):
            self.mysql.get_cluster_set_global_primary_address()

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlsh_script")
    def test_is_cluster_auto_rejoin_ongoing(self, _run_mysqlsh_script):
        """Test is_cluster_auto_rejoin_ongoing."""
        _run_mysqlsh_script.return_value = (
            "<COMPLETED_ATTEMPTS>1</COMPLETED_ATTEMPTS>\n"
            "<ESTIMATED_ATTEMPTS>3</ESTIMATED_ATTEMPTS>\n"
        )
        assert self.mysql.is_cluster_auto_rejoin_ongoing() is True

        _run_mysqlsh_script.return_value = (
            "<COMPLETED_ATTEMPTS>3</COMPLETED_ATTEMPTS>\n"
            "<ESTIMATED_ATTEMPTS>3</ESTIMATED_ATTEMPTS>\n"
        )
        assert self.mysql.is_cluster_auto_rejoin_ongoing() is False

        _run_mysqlsh_script.return_value = ""
        _run_mysqlsh_script.side_effect = MySQLClientError
        with self.assertRaises(MySQLClientError):
            self.mysql.is_cluster_auto_rejoin_ongoing()

    @patch("charms.mysql.v0.mysql.MySQLBase.get_cluster_set_status")
    def test_is_cluster_replica(self, _get_cluster_set_status):
        """Test is_cluster_replica."""
        _get_cluster_set_status.return_value = CLUSTER_SET_STATUS

        self.assertTrue(self.mysql.is_cluster_replica())

    @patch("charms.mysql.v0.mysql.MySQLBase.get_cluster_set_status")
    def test_get_cluster_set_name(self, _get_cluster_set_status):
        """Test cluster_set_name."""
        _get_cluster_set_status.return_value = CLUSTER_SET_STATUS

        self.assertEqual(self.mysql.get_cluster_set_name(), self.mysql.cluster_set_name)

    @patch("charms.mysql.v0.mysql.MySQLBase._file_exists", return_value=True)
    @patch("charms.mysql.v0.mysql.MySQLBase.get_variable_value")
    @patch("charms.mysql.v0.mysql.MySQLBase._get_installed_plugins")
    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlcli_script")
    def test_install_plugin(
        self,
        _run_mysqlcli_script,
        _get_installed_plugins,
        _get_variable_value,
        _file_exists,
    ):
        """Test install_plugin."""
        _get_variable_value.return_value = "ON"

        # ensure no install if already installed
        _get_installed_plugins.return_value = {"plugin1"}
        self.mysql.install_plugins(["plugin1"])
        _run_mysqlcli_script.assert_not_called()
        _run_mysqlcli_script.reset_mock()

        # ensure not installed if unsupported
        _get_installed_plugins.return_value = set()
        self.mysql.install_plugins(["plugin1"])
        _run_mysqlcli_script.assert_not_called()
        _run_mysqlcli_script.reset_mock()

        # ensure installed
        _get_installed_plugins.return_value = set()
        self.mysql.install_plugins(["audit_log"])
        _run_mysqlcli_script.assert_called_once_with(
            (
                "SET GLOBAL super_read_only=OFF",
                "INSTALL PLUGIN audit_log SONAME 'audit_log.so';",
                "SET GLOBAL super_read_only=ON",
            ),
            user=self.mysql.server_config_user,
            password=self.mysql.server_config_password,
        )
        _run_mysqlcli_script.reset_mock()

        # ensure installed with super_read_only already off
        _get_variable_value.return_value = "OFF"
        self.mysql.install_plugins(["audit_log"])
        _run_mysqlcli_script.assert_called_once_with(
            ("INSTALL PLUGIN audit_log SONAME 'audit_log.so';",),
            user=self.mysql.server_config_user,
            password=self.mysql.server_config_password,
        )

        # ensure raise exception
        _get_installed_plugins.return_value = set()
        self.mysql.install_plugins(["audit_log"])
        _run_mysqlcli_script.side_effect = MySQLClientError
        with self.assertRaises(MySQLPluginInstallError):
            self.mysql.install_plugins(["audit_log"])

    @patch("charms.mysql.v0.mysql.MySQLBase.get_variable_value")
    @patch("charms.mysql.v0.mysql.MySQLBase._get_installed_plugins")
    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlcli_script")
    def test_uninstall_plugin(
        self,
        _run_mysqlcli_script,
        _get_installed_plugins,
        _get_variable_value,
    ):
        """Test uninstall_plugin."""
        # ensure not uninstalled if not installed
        _get_installed_plugins.return_value = set()
        self.mysql.uninstall_plugins(["plugin1"])
        _run_mysqlcli_script.assert_not_called()
        _run_mysqlcli_script.reset_mock()

        # ensure uninstalled
        _get_variable_value.return_value = "ON"
        _get_installed_plugins.return_value = {"audit_log"}
        self.mysql.uninstall_plugins(["audit_log"])
        _run_mysqlcli_script.assert_called_once_with(
            (
                "SET GLOBAL super_read_only=OFF",
                "UNINSTALL PLUGIN audit_log;",
                "SET GLOBAL super_read_only=ON",
            ),
            user=self.mysql.server_config_user,
            password=self.mysql.server_config_password,
        )
        _run_mysqlcli_script.reset_mock()

        # ensure uninstalled with super_read_only already off
        _get_variable_value.return_value = "OFF"
        _get_installed_plugins.return_value = {"audit_log"}
        self.mysql.uninstall_plugins(["audit_log"])
        _run_mysqlcli_script.assert_called_once_with(
            ("UNINSTALL PLUGIN audit_log;",),
            user=self.mysql.server_config_user,
            password=self.mysql.server_config_password,
        )

        # ensure raise exception
        _get_installed_plugins.return_value = {"audit_log"}
        self.mysql.uninstall_plugins(["audit_log"])
        _run_mysqlcli_script.side_effect = MySQLClientError
        with self.assertRaises(MySQLPluginInstallError):
            self.mysql.uninstall_plugins(["audit_log"])

    @patch("charms.mysql.v0.mysql.MySQLBase._run_mysqlcli_script")
    def test_get_installed_plugins(self, _run_mysqlcli_script):
        """Test get_installed_plugins."""
        _run_mysqlcli_script.return_value = [["audit_log", "clone", "group_replication"]]
        self.mysql._run_mysqlcli_script = _run_mysqlcli_script

        plugins = self.mysql._get_installed_plugins()
        self.assertEqual(plugins, {"audit_log"})

        _run_mysqlcli_script.side_effect = MySQLClientError
        with self.assertRaises(MySQLClientError):
            self.mysql._get_installed_plugins()

    def test_strip_off_password(self):
        _input = """
("Traceback (most recent call last):",
  File "/var/lib/juju/agents/unit-mysql-k8s-edge-0/charm/src/mysql_k8s_helpers.py", line 642, in _run_mysqlsh_script
    stdout, _ = process.wait_output()
  File "/var/lib/juju/agents/unit-mysql-k8s-edge-0/charm/venv/lib/python3.10/site-packages/ops/pebble.py", line 1771, in wait_output
    raise ExecError[AnyStr](self._command, exit_code, out_value, err_value)
ops.pebble.ExecError: non-zero exit code 1 executing ['/usr/bin/mysqlsh', '--passwords-from-stdin', '--uri=serverconfig@mysql-k8s-edge-0.mysql-k8s-edge-endpoints.stg-alutay-datasql-juju361.svc.cluster.local:33062', '--python', '--verbose=0', '-c', 'shell.options.set(\'useWizards\', False)\nprint(\'###\')\nsh$
ll.connect_to_primary()\nsession.run_sql("CREATE DATABASE IF NOT EXISTS `continuous_writes_database`;")\nsession.run_sql("CREATE USER `relation-21_ff7306c7454f44`@`%` IDENTIFIED BY \'s1ffxPedAmX58aOdCRSzxEpm\' ATTRIBUTE \'{}\';")\nsession.run_sql("GRANT USAGE ON *.* TO `relation-21_ff7306c7454f44`@`%`;")\nses
sion.run_sql("GRANT ALL PRIVILEGES ON `continuous_writes_database`.* TO `relation-21_ff7306c7454f44`@`%`;")'], stdout="\x1b[1mPlease provide the password for 'serverconfig@mysql-k8s-edge-0.mysql-k8s-edge-endpoints.stg-alutay-datasql-juju361.svc.cluster.local:33062': \x1b[0m###\n", stderr='Cannot set LC_ALL to
 locale en_US.UTF-8: No such file or directory\n\x1b[36mNOTE: \x1b[0mAlready connected to a PRIMARY.\nTraceback (most recent call last):\n  File "<string>", line 5, in <module>\nmysqlsh.DBError: MySQL Error (1396): ClassicSession.run_sql: Operation CREATE USER failed for \'relation-21_ff7306c7454f44\'@\'%\'\n
"""
        output = self.mysql.strip_off_passwords(_input)
        self.assertTrue("s1ffxPedAmX58aOdCRSzxEpm" not in output)

    def test_strip_off_passwords_from_exception(self):
        # Simulate an exception with a password in the message
        original_exception = Exception("The error")
        original_exception.cmd = [
            "CREATE USER `relation-21_ff7306c7454f44`@`%` IDENTIFIED BY 's1ffxPedAmX58aOdCRSzxEpm' ATTRIBUTE '{}';",
        ]

        self.mysql.strip_off_passwords_from_exception(original_exception)

        self.assertNotIn("s1ffxPedAmX58aOdCRSzxEpm", original_exception.cmd[0])

    def test_abstract_methods(self):
        """Test abstract methods."""
        with self.assertRaises(NotImplementedError):
            self.mysql.wait_until_mysql_connection()

        with self.assertRaises(NotImplementedError):
            self.mysql._run_mysqlsh_script("", "", "", "")

        with self.assertRaises(NotImplementedError):
            self.mysql._run_mysqlcli_script(("",), "", "")

        with self.assertRaises(NotImplementedError):
            self.mysql._execute_commands([])

        with self.assertRaises(NotImplementedError):
            self.mysql.is_mysqld_running()

        with self.assertRaises(NotImplementedError):
            self.mysql.stop_mysqld()

        with self.assertRaises(NotImplementedError):
            self.mysql.start_mysqld()

        with self.assertRaises(NotImplementedError):
            self.mysql.get_available_memory()

        with self.assertRaises(NotImplementedError):
            self.mysql.reset_data_dir()
