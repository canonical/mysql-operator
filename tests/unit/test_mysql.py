# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit test for MySQL shared library."""

import copy
import unittest
from unittest.mock import MagicMock, call, patch

import tenacity
from charms.mysql.v0.mysql import (
    LEGACY_ROLE_ROUTER,
    MODERN_ROLE_ROUTER,
    ROLE_BACKUP,
    ROLE_DBA,
    ROLE_DDL,
    ROLE_DML,
    ROLE_READ,
    ROLE_STATS,
    UNIT_ADD_LOCKNAME,
    Error,
    MySQLAddInstanceToClusterError,
    MySQLBase,
    MySQLCheckUserExistenceError,
    MySQLClusterMetadataExistsError,
    MySQLConfigureInstanceError,
    MySQLConfigureMySQLRolesError,
    MySQLConfigureMySQLUsersError,
    MySQLConfigureRouterUserError,
    MySQLCreateApplicationDatabaseError,
    MySQLCreateApplicationScopedUserError,
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
    MySQLInitializeJujuOperationsTableError,
    MySQLLockAcquisitionError,
    MySQLOfflineModeAndHiddenInstanceExistsError,
    MySQLPrepareBackupForRestoreError,
    MySQLPromoteClusterToPrimaryError,
    MySQLRemoveInstanceError,
    MySQLRemoveReplicaClusterError,
    MySQLRemoveRouterFromMetadataError,
    MySQLRescanClusterError,
    MySQLRestoreBackupError,
    MySQLRetrieveBackupWithXBCloudError,
    MySQLSetClusterPrimaryError,
    MySQLSetInstanceOfflineModeError,
    MySQLSetInstanceOptionError,
    MySQLSetVariableError,
    MySQLUnableToGetMemberStateError,
)
from mysql_shell.builders import CharmAuthorizationQueryBuilder
from mysql_shell.executors.errors import ExecutionError
from mysql_shell.models import (
    ClusterGlobalStatus,
    InstanceRole,
    InstanceState,
)

from constants import CHARMED_MYSQLSH, MYSQLD_SOCK_FILE

SHORT_CLUSTER_STATUS = {
    "defaultReplicaSet": {
        "topology": {
            "mysql-k8s-0": {
                "address": "mysql-k8s-0.mysql-k8s-endpoints:3306",
                "memberRole": "SECONDARY",
                "mode": "R/O",
                "status": "ONLINE",
            },
            "mysql-k8s-1": {
                "address": "mysql-k8s-1.mysql-k8s-endpoints:3306",
                "memberRole": "PRIMARY",
                "mode": "R/W",
                "status": "ONLINE",
            },
            "mysql-k8s-2": {
                "address": "mysql-k8s-2.mysql-k8s-endpoints:3306",
                "memberRole": "",
                "mode": "R/O",
                "status": "OFFLINE",
            },
        }
    }
}

CLUSTER_SET_STATUS = {
    "clusters": {
        "test_cluster": {
            "clusterRole": "REPLICA",
            "clusterSetReplicationStatus": "OK",
            "globalStatus": "OK",
        },
        "lisbon": {
            "clusterRole": "PRIMARY",
            "globalStatus": "OK",
            "primary": "juju-3f9f94-1.lxd:3306",
        },
    },
    "domainName": "test_cluster_set",
    "globalPrimaryInstance": "juju-3f9f94-1.lxd:3306",
    "primaryCluster": "lisbon",
    "status": "HEALTHY",
    "statusText": "all clusters available.",
}


class TestMySQLBase(unittest.TestCase):
    # Patch abstract methods so it's
    # possible to instantiate abstract class.
    @patch.multiple(MySQLBase, __abstractmethods__=set())
    def setUp(self):
        self.mock_executor_cls = MagicMock()
        self.mock_executor = self.mock_executor_cls.return_value
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
            CHARMED_MYSQLSH,
            self.mock_executor_cls,
        )  # pyright: ignore

    def test_configure_mysql_router_roles(self):
        """Test successful configuration of MySQL router role."""
        self.mock_executor.execute_sql.return_value = []

        search_query = (
            "SELECT user, host "
            "FROM mysql.user "
            "WHERE user LIKE '{role}' AND authentication_string=''"
        )
        create_query = ";".join((
            "CREATE ROLE {role}",
            "GRANT CREATE ON *.* TO {role}",
            "GRANT CREATE USER ON *.* TO {role}",
            "GRANT ALL ON *.* TO {role} WITH GRANT OPTION",
        ))

        self.mysql.configure_mysql_router_roles()
        self.mock_executor.execute_sql.assert_has_calls([
            call(search_query.format(role="%router")),
            call(create_query.format(role=LEGACY_ROLE_ROUTER)),
            call(create_query.format(role=MODERN_ROLE_ROUTER)),
        ])

    def test_configure_mysql_router_roles_fail(self):
        """Test failure to configure the MySQL router role."""
        self.mock_executor.execute_sql.side_effect = ExecutionError

        with self.assertRaises(MySQLConfigureMySQLRolesError):
            self.mysql.configure_mysql_router_roles()

    def test_configure_mysql_system_roles(self):
        """Test successful configuration of MySQL system roles."""
        self.mock_executor.execute_sql.return_value = []

        search_query = (
            "SELECT user, host "
            "FROM mysql.user "
            "WHERE user LIKE 'charmed_%' AND authentication_string=''"
        )

        builder = CharmAuthorizationQueryBuilder(
            role_admin=ROLE_DBA,
            role_backup=ROLE_BACKUP,
            role_ddl=ROLE_DDL,
            role_stats=ROLE_STATS,
            role_reader=ROLE_READ,
            role_writer=ROLE_DML,
        )
        create_query = builder.build_instance_auth_roles_query()

        self.mysql.configure_mysql_system_roles()
        self.mock_executor.execute_sql.assert_has_calls([
            call(search_query),
            call(create_query),
        ])

    def test_configure_mysql_system_roles_fail(self):
        """Test failure to configure the MySQL system roles."""
        self.mock_executor.execute_sql.side_effect = ExecutionError

        with self.assertRaises(MySQLConfigureMySQLRolesError):
            self.mysql.configure_mysql_system_roles()

    def test_configure_mysql_system_users(self):
        """Test successful configuration of MySQL system users."""
        self.mock_executor.execute_sql.return_value = []

        queries = ";".join([
            "UPDATE mysql.user SET authentication_string=null WHERE User='root' and Host='localhost'",
            "ALTER USER 'root'@'localhost' IDENTIFIED BY 'password'",
            "CREATE USER 'serverconfig'@'%' IDENTIFIED BY 'serverconfigpassword'",
            "CREATE USER 'monitoring'@'%' IDENTIFIED BY 'monitoringpassword' WITH MAX_USER_CONNECTIONS 3",
            "CREATE USER 'backups'@'%' IDENTIFIED BY 'backupspassword'",
            "GRANT ALL ON *.* TO 'serverconfig'@'%' WITH GRANT OPTION",
            "GRANT charmed_stats TO 'monitoring'@'%'",
            "GRANT charmed_backup TO 'backups'@'%'",
            "REVOKE BINLOG_ADMIN, CONNECTION_ADMIN, ENCRYPTION_KEY_ADMIN, GROUP_REPLICATION_ADMIN, REPLICATION_SLAVE_ADMIN, SET_USER_ID, SUPER, SYSTEM_USER, SYSTEM_VARIABLES_ADMIN, VERSION_TOKEN_ADMIN ON *.* FROM 'root'@'localhost'",
            "FLUSH PRIVILEGES",
        ])

        self.mysql.configure_mysql_system_users()
        self.mock_executor.execute_sql.assert_called_once_with(queries)

    def test_configure_mysql_system_users_fail(self):
        """Test failure to configure the MySQL system users."""
        self.mock_executor.execute_sql.side_effect = ExecutionError

        with self.assertRaises(MySQLConfigureMySQLUsersError):
            self.mysql.configure_mysql_system_users()

    def test_does_mysql_user_exist(self):
        """Test successful execution of does_mysql_user_exist."""
        # Test passing in a custom hostname
        query = (
            "SELECT user, host, attribute "
            "FROM information_schema.user_attributes "
            "WHERE user LIKE 'test_username' AND attribute LIKE '%'"
        )

        self.mysql.does_mysql_user_exist("test_username", "1.1.1.1")
        self.mock_executor.execute_sql.assert_called_once_with(query)

        # Reset the mock
        self.mock_executor.execute_sql.reset_mock()

        self.mysql.does_mysql_user_exist("test_username", "1.1.1.2")
        self.mock_executor.execute_sql.assert_called_once_with(query)

    def test_does_mysql_user_exist_failure(self):
        """Test failure in execution of does_mysql_user_exist."""
        self.mock_executor.execute_sql.side_effect = ExecutionError

        with self.assertRaises(MySQLCheckUserExistenceError):
            self.mysql.does_mysql_user_exist("test_username", "1.1.1.1")

    @patch("charms.mysql.v0.mysql.MySQLBase.get_cluster_primary_address")
    def test_configure_mysqlrouter_user(self, _get_cluster_primary_address):
        """Test the successful execution of configure_mysqlrouter_user."""
        commands = ";".join((
            "CREATE USER 'test_username'@'1.1.1.1' IDENTIFIED BY 'test_password' ATTRIBUTE '{\\\"unit_name\\\": \\\"app/0\\\"}'",
            "GRANT CREATE USER ON *.* TO 'test_username'@'1.1.1.1' WITH GRANT OPTION",
            "GRANT SELECT, INSERT, UPDATE, DELETE, EXECUTE ON mysql_innodb_cluster_metadata.* TO 'test_username'@'1.1.1.1'",
            "GRANT SELECT ON mysql.user TO 'test_username'@'1.1.1.1'",
            "GRANT SELECT ON performance_schema.replication_group_members TO 'test_username'@'1.1.1.1'",
            "GRANT SELECT ON performance_schema.replication_group_member_stats TO 'test_username'@'1.1.1.1'",
            "GRANT SELECT ON performance_schema.global_variables TO 'test_username'@'1.1.1.1'",
        ))

        self.mysql.configure_mysqlrouter_user("test_username", "test_password", "1.1.1.1", "app/0")
        self.mock_executor.execute_sql.assert_called_once_with(commands)

    @patch("charms.mysql.v0.mysql.MySQLBase.get_cluster_primary_address")
    def test_configure_mysqlrouter_user_failure(self, _get_cluster_primary_address):
        """Test failure to configure the MySQLRouter user."""
        self.mock_executor.execute_sql.side_effect = ExecutionError

        with self.assertRaises(MySQLConfigureRouterUserError):
            self.mysql.configure_mysqlrouter_user(
                "test_username",
                "test_password",
                "1.1.1.1",
                "app/0",
            )

    @patch("charms.mysql.v0.mysql.MySQLBase.get_cluster_primary_address")
    @patch("charms.mysql.v0.mysql.MySQLBase.get_non_system_databases")
    @patch("charms.mysql.v0.mysql.MySQLBase._build_mysql_database_dba_role")
    def test_create_application_database(
        self,
        _build_mysql_database_dba_role,
        _get_non_system_databases,
        _get_cluster_primary_address,
    ):
        """Test the successful execution of create_application_database."""
        _build_mysql_database_dba_role.return_value = "test_database_00"
        _get_non_system_databases.return_value = {"test_database"}

        self.mysql.create_database("test_database")
        self.mock_executor.execute_sql.assert_not_called()

        _get_non_system_databases.return_value = set()
        query = ";".join([
            "CREATE DATABASE `test_database`",
            "GRANT SELECT ON `test_database`.* TO 'charmed_read'",
            "GRANT SELECT, INSERT, DELETE, UPDATE ON `test_database`.* TO 'charmed_dml'",
            "CREATE ROLE 'test_database_00'",
            "GRANT SELECT, INSERT, DELETE, UPDATE, EXECUTE, ALTER, ALTER ROUTINE, CREATE, CREATE ROUTINE, CREATE VIEW, DROP, INDEX, LOCK TABLES, REFERENCES, TRIGGER ON `test_database`.* TO 'test_database_00'",
        ])

        self.mysql.create_database("test_database")
        self.mock_executor.execute_sql.assert_called_once_with(query)

    @patch("charms.mysql.v0.mysql.MySQLBase.get_cluster_primary_address")
    @patch("charms.mysql.v0.mysql.MySQLBase.get_non_system_databases")
    @patch("charms.mysql.v0.mysql.MySQLBase._build_mysql_database_dba_role")
    def test_create_application_database_failure(
        self,
        _build_mysql_database_dba_role,
        _get_non_system_databases,
        _get_cluster_primary_address,
    ):
        """Test failure to create application database and scoped user."""
        _build_mysql_database_dba_role.return_value = "test_database_00"
        _get_non_system_databases.return_value = set()
        self.mock_executor.execute_sql.side_effect = ExecutionError

        with self.assertRaises(MySQLCreateApplicationDatabaseError):
            self.mysql.create_database("test_database")

    @patch("charms.mysql.v0.mysql.MySQLBase.get_cluster_primary_address")
    def test_create_application_scoped_user(self, _get_cluster_primary_address):
        """Test the successful execution of create_application_scoped_user."""
        create_commands = ";".join((
            "CREATE USER 'test_username'@'1.1.1.1' IDENTIFIED BY 'test_password' ATTRIBUTE '{\\\"unit_name\\\": \\\"app/0\\\"}'",
            "",
        ))
        grant_commands = ";".join((
            "GRANT USAGE ON *.* TO `test_username`@`1.1.1.1`",
            "GRANT ALL PRIVILEGES ON `test_database`.* TO `test_username`@`1.1.1.1`",
        ))

        self.mysql.create_scoped_user(
            "test_database",
            "test_username",
            "test_password",
            "1.1.1.1",
            unit_name="app/0",
        )

        self.mock_executor.execute_sql.assert_has_calls([
            call(create_commands),
            call(grant_commands),
        ])

    @patch("charms.mysql.v0.mysql.MySQLBase.get_cluster_primary_address")
    def test_create_application_scoped_user_failure(self, _get_cluster_primary_address):
        """Test failure to create application scoped user."""
        self.mock_executor.execute_sql.side_effect = ExecutionError

        with self.assertRaises(MySQLCreateApplicationScopedUserError):
            self.mysql.create_scoped_user(
                "test_database",
                "test_username",
                "test_password",
                "1.1.1.1",
                unit_name="app/0",
            )

    @patch("charms.mysql.v0.mysql.MySQLBase.get_cluster_primary_address")
    def test_create_application_scoped_user_invalid(self, _get_cluster_primary_address):
        """Test failure to create an invalid application scoped user."""
        with self.assertRaises(MySQLCreateApplicationScopedUserError):
            self.mysql.create_scoped_user(
                "test_database",
                "test_username",
                "test_password",
                "1.1.1.1",
                unit_name="app/0",
                extra_roles=[ROLE_BACKUP],
            )

    def test_configure_instance(self):
        """Test a successful execution of configure_instance."""
        # Test with create_cluster_admin=False
        commands = [
            "dba.configure_instance(options={'restart': 'true'})",
        ]

        self.mysql.configure_instance(create_cluster_admin=False)
        self.mock_executor.execute_py.assert_called_once_with("\n".join(commands))

        self.mock_executor.reset_mock()

        # Test with create_cluster_admin=True
        commands = [
            "dba.configure_instance(options={'restart': 'true', 'clusterAdmin': 'clusteradmin', 'clusterAdminPassword': 'clusteradminpassword'})",
        ]

        self.mysql.configure_instance(create_cluster_admin=True)
        self.mock_executor.execute_py.assert_called_once_with("\n".join(commands))

        self.mock_executor.reset_mock()
        self.mock_executor.execute_py.side_effect = ExecutionError

        with self.assertRaises(MySQLConfigureInstanceError):
            self.mysql.configure_instance()

    def test_initialize_juju_units_operations_table(self):
        """Test a successful initialization of the mysql.juju_units_operations table."""
        queries = ";".join((
            (
                "CREATE TABLE IF NOT EXISTS `mysql`.`juju_units_operations` ( "
                "    task VARCHAR(20), "
                "    executor VARCHAR(20), "
                "    status VARCHAR(20), "
                "    PRIMARY KEY(task) "
                ")"
            ),
            (
                "INSERT INTO `mysql`.`juju_units_operations` (task, executor, status) "
                "VALUES ('unit-add', '', 'not-started') "
                "ON DUPLICATE KEY UPDATE "
                "    executor = '', "
                "    status = 'not-started'"
            ),
            (
                "INSERT INTO `mysql`.`juju_units_operations` (task, executor, status) "
                "VALUES ('unit-teardown', '', 'not-started') "
                "ON DUPLICATE KEY UPDATE "
                "    executor = '', "
                "    status = 'not-started'"
            ),
        ))

        self.mysql.initialize_juju_units_operations_table()
        self.mock_executor.execute_sql.assert_called_once_with(queries)

    def test_initialize_juju_units_operations_table_exception(self):
        """Test an exception initialization of the mysql.juju_units_operations table."""
        self.mock_executor.execute_sql.side_effect = ExecutionError

        with self.assertRaises(MySQLInitializeJujuOperationsTableError):
            self.mysql.initialize_juju_units_operations_table()

    def test_create_cluster(self):
        """Test a successful execution of create_cluster."""
        create_commands = [
            "dba.create_cluster('test_cluster', {'communicationStack': 'MySQL'})",
        ]
        update_commands = [
            "cluster = dba.get_cluster('test_cluster')",
            "cluster.set_instance_option('127.0.0.1:3306', 'label', 'mysql-0')",
        ]

        self.mysql.create_cluster("mysql-0")

        self.mock_executor.execute_py.assert_has_calls([
            call("\n".join(create_commands)),
            call("\n".join(update_commands)),
        ])

    def test_create_cluster_exceptions(self):
        """Test exceptions raised while running create_cluster."""
        self.mock_executor.execute_py.side_effect = ExecutionError

        with self.assertRaises(MySQLCreateClusterError):
            self.mysql.create_cluster("mysql-0")

    def test_create_cluster_set(self):
        """Test a successful execution of create_cluster."""
        commands = [
            "shell.connect_to_primary()",
            "cluster = dba.get_cluster('test_cluster')",
            "cluster.create_cluster_set('test_cluster_set')",
        ]

        self.mysql.create_cluster_set()
        self.mock_executor.execute_py.assert_called_once_with("\n".join(commands))

    def test_create_cluster_set_exceptions(self):
        """Test exceptions raised while running create_cluster."""
        self.mock_executor.execute_py.side_effect = ExecutionError

        with self.assertRaises(MySQLCreateClusterSetError):
            self.mysql.create_cluster_set()

    @patch("charms.mysql.v0.mysql.MySQLBase.get_cluster_primary_address")
    @patch("charms.mysql.v0.mysql.MySQLBase._release_lock")
    @patch("charms.mysql.v0.mysql.MySQLBase._acquire_lock", return_value=True)
    def test_add_instance_to_cluster(
        self,
        _acquire_lock,
        _release_lock,
        _get_cluster_primary_address,
    ):
        """Test a successful execution of create_cluster."""
        commands = [
            "cluster = dba.get_cluster('test_cluster')",
            "cluster.add_instance('127.0.0.2:3306', {'recoveryMethod': 'auto', 'password': 'clusteradminpassword', 'label': 'mysql-1'})",
        ]

        self.mysql.add_instance_to_cluster(
            instance_address="127.0.0.2",
            instance_unit_label="mysql-1",
        )

        _acquire_lock.assert_called_once()
        _release_lock.assert_called_once()
        self.mock_executor.execute_py.assert_called_once_with("\n".join(commands))

    @patch("charms.mysql.v0.mysql.MySQLBase.get_cluster_primary_address")
    @patch("charms.mysql.v0.mysql.MySQLBase._release_lock")
    @patch("charms.mysql.v0.mysql.MySQLBase._acquire_lock", return_value=True)
    def test_add_instance_to_cluster_exception(
        self,
        _acquire_lock,
        _release_lock,
        _get_cluster_primary_address,
    ):
        """Test exceptions raised while running add_instance_to_cluster."""
        self.mock_executor.execute_py.side_effect = ExecutionError

        with self.assertRaises(MySQLAddInstanceToClusterError):
            self.mysql.add_instance_to_cluster(
                instance_address="127.0.0.2",
                instance_unit_label="mysql-1",
            )
            _acquire_lock.assert_called_once()
            _release_lock.assert_called_once()

    def test_is_instance_configured_for_innodb(self):
        """Test with no exceptions while calling the is_instance_configured_for_innodb method."""
        self.mock_executor.execute_py.return_value = '{"status": "ok"}'

        commands = [
            "result = dba.check_instance_configuration(options=None)",
            "print(result)",
        ]

        result = self.mysql.is_instance_configured_for_innodb("127.0.0.2")
        self.assertTrue(result)
        self.mock_executor.execute_py.assert_called_once_with("\n".join(commands))

    def test_is_instance_configured_for_innodb_exceptions(self):
        """Test an exception while calling the is_instance_configured_for_innodb method."""
        self.mock_executor.execute_py.side_effect = ExecutionError

        commands = [
            "result = dba.check_instance_configuration(options=None)",
            "print(result)",
        ]

        result = self.mysql.is_instance_configured_for_innodb("127.0.0.2")
        self.assertFalse(result)
        self.mock_executor.execute_py.assert_called_once_with("\n".join(commands))

    @patch("charms.mysql.v0.mysql.MySQLBase.get_cluster_node_count")
    @patch("charms.mysql.v0.mysql.MySQLBase._acquire_lock")
    @patch("charms.mysql.v0.mysql.MySQLBase._release_lock")
    def test_remove_primary_instance(
        self,
        _release_lock,
        _acquire_lock,
        _get_cluster_node_count,
    ):
        """Test with no exceptions while running the remove_instance() method."""
        _get_cluster_node_count.return_value = 2

        commands = [
            "cluster = dba.get_cluster('test_cluster')",
            "cluster.remove_instance('127.0.0.1:3306', {'password': 'clusteradminpassword', 'force': 'true'})",
        ]

        self.mysql.remove_instance("mysql-0")

        _acquire_lock.assert_called_once_with(
            executor=self.mock_executor,
            unit_label="mysql-0",
            unit_task="unit-teardown",
        )
        _release_lock.assert_called_once_with(
            executor=self.mock_executor,
            unit_label="mysql-0",
            unit_task="unit-teardown",
        )

        self.mock_executor.execute_py.assert_called_once_with("\n".join(commands))

    @patch("charms.mysql.v0.mysql.MySQLBase.get_cluster_node_count")
    @patch("charms.mysql.v0.mysql.MySQLBase._acquire_lock")
    @patch("charms.mysql.v0.mysql.MySQLBase._release_lock")
    def test_remove_primary_instance_error_acquiring_lock(
        self,
        _release_lock,
        _acquire_lock,
        _get_cluster_node_count,
    ):
        """Test an issue acquiring lock while running the remove_instance() method."""
        _get_cluster_node_count.return_value = 2
        _acquire_lock.return_value = False

        with self.assertRaises(MySQLLockAcquisitionError):
            self.mysql.remove_instance("mysql-0")

        _acquire_lock.assert_called_once_with(
            executor=self.mock_executor,
            unit_label="mysql-0",
            unit_task="unit-teardown",
        )
        _release_lock.assert_not_called()

    @patch("charms.mysql.v0.mysql.MySQLBase.get_cluster_node_count")
    @patch("charms.mysql.v0.mysql.MySQLBase._acquire_lock")
    @patch("charms.mysql.v0.mysql.MySQLBase._release_lock")
    def test_remove_primary_instance_error(
        self,
        _release_lock,
        _acquire_lock,
        _get_cluster_node_count,
    ):
        """Test an issue releasing locks while running the remove_instance() method."""
        _get_cluster_node_count.return_value = 2
        self.mock_executor.execute_py.side_effect = ExecutionError

        commands = [
            "cluster = dba.get_cluster('test_cluster')",
            "cluster.remove_instance('127.0.0.1:3306', {'password': 'clusteradminpassword', 'force': 'true'})",
        ]

        # Disable tenacity retry
        self.mysql.remove_instance.retry.retry = tenacity.retry_if_not_result(lambda _: True)

        with self.assertRaises(MySQLRemoveInstanceError):
            self.mysql.remove_instance("mysql-0")

        _acquire_lock.assert_called_once_with(
            executor=self.mock_executor,
            unit_label="mysql-0",
            unit_task="unit-teardown",
        )
        _release_lock.assert_called_once_with(
            executor=self.mock_executor,
            unit_label="mysql-0",
            unit_task="unit-teardown",
        )

        self.mock_executor.execute_py.assert_called_once_with("\n".join(commands))

    def test_acquire_lock(self):
        """Test a successful execution of _acquire_lock()."""
        query = (
            "UPDATE `mysql`.`juju_units_operations` "
            "SET status = 'in-progress', executor = 'mysql-0' "
            "WHERE task = 'unit-teardown' AND executor = ''"
        )

        self.mock_executor.execute_sql.return_value = [{"executor": "mysql-0"}]

        acquired_lock = self.mysql._acquire_lock(self.mock_executor, "mysql-0", "unit-teardown")
        self.mock_executor.execute_sql.assert_has_calls([call(query)])
        self.assertTrue(acquired_lock)

    def test_issue_with_acquire_lock(self):
        """Test an issue while executing _acquire_lock()."""
        query = (
            "UPDATE `mysql`.`juju_units_operations` "
            "SET status = 'in-progress', executor = 'mysql-0' "
            "WHERE task = 'unit-teardown' AND executor = ''"
        )

        self.mock_executor.execute_sql.side_effect = ExecutionError

        acquired_lock = self.mysql._acquire_lock(self.mock_executor, "mysql-0", "unit-teardown")
        self.mock_executor.execute_sql.assert_called_once_with(query)
        self.assertFalse(acquired_lock)

    def test_release_lock(self):
        """Test a successful execution of _acquire_lock()."""
        query = (
            "UPDATE `mysql`.`juju_units_operations` "
            "SET status = 'not-started', executor = '' "
            "WHERE task = 'unit-teardown' AND executor = 'mysql-0'"
        )

        self.mysql._release_lock(self.mock_executor, "mysql-0", "unit-teardown")
        self.mock_executor.execute_sql.assert_called_once_with(query)

    def test_get_cluster_primary_address(self):
        """Test a successful execution of _get_cluster_primary_address()."""
        self.mock_executor.execute_py.return_value = (
            '{"defaultReplicaSet": {"status": "OK", "primary": "1.1.1.1:3306"}}'
        )

        primary_address = self.mysql.get_cluster_primary_address()
        self.assertEqual(primary_address, "1.1.1.1")

        self.mock_executor.execute_py.return_value = (
            '{"defaultReplicaSet": {"status": "NO_QUORUM", "primary": "1.1.1.1:3306"}}'
        )

        with self.assertRaises(MySQLGetClusterPrimaryAddressError):
            self.mysql.get_cluster_primary_address()

    @patch("charms.mysql.v0.mysql.MySQLBase.cluster_metadata_exists", return_value=True)
    def test_is_instance_in_cluster(self, _cluster_metadata_exists):
        """Test a successful execution of is_instance_in_cluster() method."""
        self.mock_executor.execute_py.return_value = (
            '{"defaultReplicaSet": {"topology": {"mysql-0": {"status": "ONLINE"}}}}'
        )
        self.assertTrue(self.mysql.is_instance_in_cluster("mysql-0"))

        self.mock_executor.execute_py.return_value = (
            '{"defaultReplicaSet": {"topology": {"mysql-0": {"status": "NOT_A_MEMBER"}}}}'
        )
        self.assertFalse(self.mysql.is_instance_in_cluster("mysql-0"))

    def test_is_instance_in_cluster_exception(self):
        """Test an exception executing is_instance_in_cluster() method."""
        self.mock_executor.execute_py.side_effect = ExecutionError

        result = self.mysql.is_instance_in_cluster("mysql-0")
        self.assertFalse(result)

    def test_get_cluster_status(self):
        """Test a successful execution of get_cluster_status() method."""
        commands = [
            "cluster = dba.get_cluster('test_cluster')",
            "status = cluster.status({'extended': False})",
            "print(status)",
        ]

        self.mock_executor.execute_py.return_value = '{"status": "ONLINE"}'
        self.mysql.get_cluster_status()
        self.mock_executor.execute_py.assert_called_once_with(
            "\n".join(commands),
            timeout=30,
        )

    @patch("json.loads")
    def test_get_cluster_status_failure(self, _json_loads):
        """Test an exception executing get_cluster_status() method."""
        self.mock_executor.execute_py.side_effect = ExecutionError

        self.mysql.get_cluster_status()
        _json_loads.assert_not_called()

    def test_rescan_cluster(self):
        """Test a successful execution of rescan_cluster()."""
        commands = [
            "cluster = dba.get_cluster('test_cluster')",
            "cluster.rescan({})",
        ]

        self.mysql.rescan_cluster()
        self.mock_executor.execute_py.assert_called_once_with("\n".join(commands))

    def test_set_instance_option(self):
        """Test execution of set_instance_option()."""
        commands = [
            f"cluster = dba.get_cluster('{self.mysql.cluster_name}')",
            f"cluster.set_instance_option('{self.mysql.instance_address}:3306', 'label', 'label-0')",
        ]

        self.mysql.set_instance_option("label", "label-0")
        self.mock_executor.execute_py.assert_called_once_with("\n".join(commands))

        self.mock_executor.execute_py.reset_mock()

        self.mock_executor.execute_py.side_effect = ExecutionError
        with self.assertRaises(MySQLSetInstanceOptionError):
            self.mysql.set_instance_option("label", "label-0")

    def test_get_member_role(self):
        """Test execution of get_member_role()."""
        # Disable tenacity retry
        self.mysql.get_member_role.retry.retry = tenacity.retry_if_not_result(lambda _: True)

        self.mock_executor.execute_sql.return_value = [{"member_role": "PRIMARY"}]
        role = self.mysql.get_member_role()
        self.assertEqual(role, InstanceRole.PRIMARY)

        self.mock_executor.execute_sql.return_value = [{"member_role": "SECONDARY"}]
        role = self.mysql.get_member_role()
        self.assertEqual(role, InstanceRole.SECONDARY)

        self.mock_executor.execute_sql.side_effect = ExecutionError
        with self.assertRaises(MySQLUnableToGetMemberStateError):
            self.mysql.get_member_role()

    def test_get_member_state(self):
        """Test execution of get_member_state()."""
        # Disable tenacity retry
        self.mysql.get_member_state.retry.retry = tenacity.retry_if_not_result(lambda _: True)

        self.mock_executor.execute_sql.return_value = [{"member_state": "ONLINE"}]
        state = self.mysql.get_member_state()
        self.assertEqual(state, InstanceState.ONLINE)

        self.mock_executor.execute_sql.return_value = [{"member_state": "OFFLINE"}]
        state = self.mysql.get_member_state()
        self.assertEqual(state, InstanceState.OFFLINE)

        self.mock_executor.execute_sql.side_effect = ExecutionError
        with self.assertRaises(MySQLUnableToGetMemberStateError):
            self.mysql.get_member_state()

    def test_rescan_cluster_failure(self):
        """Test an exception executing rescan_cluster()."""
        self.mock_executor.execute_py.side_effect = ExecutionError

        with self.assertRaises(MySQLRescanClusterError):
            self.mysql.rescan_cluster()

    def test_error(self):
        """Test Error class."""
        error = Error("Error message")

        self.assertEqual(error.__repr__(), "<charms.mysql.v0.mysql.Error ('Error message',)>")
        self.assertEqual(error.name, "<charms.mysql.v0.mysql.Error>")
        self.assertEqual(error.message, "Error message")

    @patch("charms.mysql.v0.mysql.MySQLBase.get_cluster_primary_address")
    def test_delete_users_for_unit_failure(self, _get_cluster_primary_address):
        """Test failure to delete users for unit."""
        self.mock_executor.execute_sql.side_effect = ExecutionError

        with self.assertRaises(MySQLDeleteUsersForUnitError):
            self.mysql.delete_users_for_unit("foouser")

    @patch("charms.mysql.v0.mysql.MySQLBase.get_cluster_primary_address")
    def test_delete_users_for_relation_failure(self, _get_cluster_primary_address):
        """Test failure to delete users for relation."""
        self.mock_executor.execute_sql.side_effect = ExecutionError

        with self.assertRaises(MySQLDeleteUsersForRelationError):
            self.mysql.delete_users_for_relation("foouser")

    @patch("charms.mysql.v0.mysql.MySQLBase.get_cluster_primary_address")
    def test_delete_user(self, _get_cluster_primary_address):
        """Test delete_user() method."""
        query = "DROP USER IF EXISTS 'testuser'@'%'"

        self.mysql.delete_user("testuser")
        self.mock_executor.execute_sql.assert_called_once_with(query)

        self.mock_executor.execute_sql.side_effect = ExecutionError
        with self.assertRaises(MySQLDeleteUserError):
            self.mysql.delete_user("testuser")

    def test_promote_cluster_to_primary(self):
        """Test promote_cluster_to_primary() method."""
        commands = [
            "shell.connect_to_primary()",
            "cluster_set = dba.get_cluster_set()",
            "cluster_set.set_primary_cluster('test_cluster')",
        ]

        self.mysql.promote_cluster_to_primary("test_cluster")
        self.mock_executor.execute_py.assert_called_once_with("\n".join(commands))

        self.mock_executor.execute_py.side_effect = ExecutionError
        with self.assertRaises(MySQLPromoteClusterToPrimaryError):
            self.mysql.promote_cluster_to_primary("test_cluster")

    def test_get_mysql_version(self):
        """Test get_mysql_version() method."""
        self.mock_executor.execute_sql.return_value = [
            {"version": "8.0.29-0ubuntu0.20.04.3"},
        ]

        query = "SELECT @@GLOBAL.`version` AS `version`"

        version = self.mysql.get_mysql_version()
        self.assertEqual(version, "8.0.29")
        self.mock_executor.execute_sql.assert_called_once_with(query)

        self.mock_executor.execute_sql.reset_mock()

        self.mock_executor.execute_sql.side_effect = ExecutionError
        with self.assertRaises(MySQLGetMySQLVersionError):
            self.mysql.get_mysql_version()

    @patch("charms.mysql.v0.mysql.MySQLBase.get_cluster_global_primary_address")
    def test_update_user_password(self, _get_cluster_global_primary_address):
        """Test the successful execution of update_user_password."""
        _get_cluster_global_primary_address.return_value = "1.1.1.1"

        query = "ALTER USER 'test_user'@'%' IDENTIFIED BY 'test_password'"

        self.mysql.update_user_password("test_user", "test_password")
        self.mock_executor.execute_sql.assert_called_once_with(query)

    def test_cluster_metadata_exists(self):
        """Test cluster_metadata_exists method."""
        query = "SELECT cluster_name FROM mysql_innodb_cluster_metadata.clusters"

        self.mock_executor.execute_sql.return_value = [{"cluster_name": self.mysql.cluster_name}]
        self.assertTrue(self.mysql.cluster_metadata_exists("1.2.3.4"))
        self.mock_executor.execute_sql.assert_called_once_with(query)

        self.mock_executor.execute_sql.reset_mock()

        self.mock_executor.execute_sql.return_value = [{"cluster_name": self.mysql.cluster_name}]
        self.assertTrue(self.mysql.cluster_metadata_exists())
        self.mock_executor.execute_sql.assert_called_once_with(query)

        self.mock_executor.execute_sql.reset_mock()

        self.mock_executor.execute_sql.side_effect = ExecutionError
        with self.assertRaises(MySQLClusterMetadataExistsError):
            self.mysql.cluster_metadata_exists("1.2.3.4")

        self.mock_executor.execute_sql.side_effect = ExecutionError
        with self.assertRaises(MySQLClusterMetadataExistsError):
            self.mysql.cluster_metadata_exists()

    @patch("charms.mysql.v0.mysql.MySQLBase.get_cluster_topology")
    def test_offline_mode_and_hidden_instance_exists(self, _get_cluster_topology):
        """Test the offline_mode_and_hidden_instance_exists() method."""
        _get_cluster_topology.return_value = {
            "cluster-1": {
                "hiddenFromRouter": True,
                "instanceErrors": "Instance has offline_mode enabled",
            },
        }

        exists = self.mysql.offline_mode_and_hidden_instance_exists()
        self.assertTrue(exists)

        _get_cluster_topology.reset_mock()
        _get_cluster_topology.return_value = {
            "cluster-1": {
                "hiddenFromRouter": False,
            },
        }

        exists = self.mysql.offline_mode_and_hidden_instance_exists()
        self.assertFalse(exists)

        _get_cluster_topology.reset_mock()
        _get_cluster_topology.side_effect = ExecutionError()

        with self.assertRaises(MySQLOfflineModeAndHiddenInstanceExistsError):
            self.mysql.offline_mode_and_hidden_instance_exists()

        _get_cluster_topology.reset_mock()
        _get_cluster_topology.return_value = "garbage"

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
        _expected_tmp_dir_commands = [
            "mktemp",
            "--directory",
            "/tmp/base/directory/xtra_backup_XXXX",
        ]
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
            [
                "find",
                "/temp/base/directory",
                "-wholename",
                "/temp/base/directory/xtra_backup_*",
                "-delete",
            ],
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
        _expected_temp_dir_commands = [
            "mktemp",
            "--directory",
            "mysql/data/directory/#mysql_sst_XXXX",
        ]
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
    def test_retrieve_backup_with_xbcloud_failure(self, _execute_commands):
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

        _expected_prepare_backup_command = [
            "xtrabackup/location",
            "--prepare",
            "--use-memory=1234",
            "--no-version-check",
            "--rollback-prepared-trx",
            "--xtrabackup-plugin-dir=xtrabackup/plugin/dir",
            "--target-dir=backup/location",
        ]

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
    def test_empty_data_files(self, _execute_commands):
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
    def test_empty_data_files_failure(self, _execute_commands):
        """Test failure of empty_data_files()."""
        _execute_commands.side_effect = MySQLExecError("failure")

        with self.assertRaises(MySQLEmptyDataDirectoryError):
            self.mysql.empty_data_files(
                "mysql/data/directory",
                user="test-user",
                group="test-group",
            )

    @patch("charms.mysql.v0.mysql.MySQLBase._execute_commands")
    def test_restore_backup(self, _execute_commands):
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

        _expected_commands = [
            "xtrabackup/location",
            "--defaults-file=defaults/config/file",
            "--defaults-group=mysqld",
            "--datadir=mysql/data/directory",
            "--no-version-check",
            "--move-back",
            "--force-non-empty-directories",
            "--xtrabackup-plugin-dir=xtrabackup/plugin/directory",
            "--target-dir=backup/location",
        ]

        _execute_commands.assert_called_once_with(
            _expected_commands,
            user="test-user",
            group="test-group",
        )

    @patch("charms.mysql.v0.mysql.MySQLBase._execute_commands")
    def test_restore_backup_failure(self, _execute_commands):
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
    def test_delete_temp_restore_directory(self, _execute_commands):
        """Test successful execution of delete_temp_restore_directory()."""
        self.mysql.delete_temp_restore_directory(
            "mysql/data/directory",
            user="test-user",
            group="test-group",
        )

        _expected_commands = [
            "find",
            "mysql/data/directory",
            "-wholename",
            "mysql/data/directory/#mysql_sst_*",
            "-delete",
        ]

        _execute_commands.assert_called_once_with(
            _expected_commands,
            user="test-user",
            group="test-group",
        )

    @patch("charms.mysql.v0.mysql.MySQLBase._execute_commands")
    def test_delete_temp_restore_directory_failure(self, _execute_commands):
        """Test failure of delete_temp_restore_directory()."""
        _execute_commands.side_effect = MySQLExecError("failure")

        with self.assertRaises(MySQLDeleteTempRestoreDirectoryError):
            self.mysql.delete_temp_restore_directory(
                "mysql/data/directory",
                user="test-user",
                group="test-group",
            )

    def test_tls_set_custom(self):
        """Test the successful execution of tls_set_custom."""
        queries = [
            "SET @@PERSIST.`ssl_ca` = 'ca_path'",
            "SET @@PERSIST.`ssl_key` = 'key_path'",
            "SET @@PERSIST.`ssl_cert` = 'cert_path'",
            "SET @@PERSIST.`require_secure_transport` = 'ON'",
            "ALTER INSTANCE RELOAD TLS",
        ]

        self.mysql.tls_setup("ca_path", "key_path", "cert_path", True)
        self.mock_executor.execute_sql.assert_has_calls([call(query) for query in queries])

    def test_tls_restore_default(self):
        """Test the successful execution of tls_set_custom."""
        queries = [
            "SET @@PERSIST.`ssl_ca` = 'ca.pem'",
            "SET @@PERSIST.`ssl_key` = 'server-key.pem'",
            "SET @@PERSIST.`ssl_cert` = 'server-cert.pem'",
            "SET @@PERSIST.`require_secure_transport` = 'OFF'",
            "ALTER INSTANCE RELOAD TLS",
        ]

        self.mysql.tls_setup()
        self.mock_executor.execute_sql.assert_has_calls([call(query) for query in queries])

    def test_kill_client_sessions(self):
        """Test kill_client_sessions."""
        search_query = (
            "SELECT processlist_id "
            "FROM performance_schema.threads "
            "WHERE connection_type IS NOT NULL AND name LIKE '%'"
        )
        stop_query = "KILL CONNECTION '123'"

        self.mock_executor.execute_sql.return_value = [{"processlist_id": 123}]
        self.mysql.kill_client_sessions()
        self.mock_executor.execute_sql.assert_has_calls([
            call(search_query),
            call(stop_query),
        ])

    def test_are_locks_acquired(self):
        """Test are_locks_acquired."""
        query = (
            "SELECT executor "
            "FROM `mysql`.`juju_units_operations` "
            f"WHERE task = '{UNIT_ADD_LOCKNAME}' AND status = 'in-progress'"
        )

        self.mock_executor.execute_sql.return_value = []
        assert self.mysql.are_locks_acquired("0.0.0.0", UNIT_ADD_LOCKNAME) is False
        self.mock_executor.execute_sql.assert_called_with(query)

    def test_get_mysql_user_for_unit(self):
        """Test get_mysql_user_for_unit."""
        query = (
            "SELECT user, host, attribute "
            "FROM information_schema.user_attributes "
            "WHERE user LIKE '%' "
            'AND attribute LIKE \'%\\"created_by_user\\": \\"relation-1\\"%\' '
            'AND attribute LIKE \'%\\"created_by_juju_unit\\": \\"mysql-router-k8s/0\\"%\''
        )

        self.mock_executor.execute_sql.return_value = [
            {
                "USER": "mysql_router1",
                "HOST": "0.0.0.0",
                "ATTRIBUTE": (
                    "{"
                    '"created_by_user": "relation-1",'
                    '"created_by_juju_unit": "mysql-router-k8s/0"'
                    "}"
                ),
            },
        ]
        self.mysql.get_mysql_router_users_for_unit(
            relation_id=1,
            mysql_router_unit_name="mysql-router-k8s/0",
        )

        self.mock_executor.execute_sql.assert_called_with(query)

        self.mock_executor.execute_sql.reset_mock()
        self.mock_executor.execute_sql.side_effect = ExecutionError
        with self.assertRaises(MySQLGetRouterUsersError):
            self.mysql.get_mysql_router_users_for_unit(
                relation_id=1,
                mysql_router_unit_name="mysql-router-k8s/0",
            )

    def test_remove_router_from_cluster_metadata(self):
        """Test remove_user_from_cluster_metadata."""
        commands = [
            "cluster = dba.get_cluster('test_cluster')",
            "cluster.remove_router_metadata('1::system')",
        ]

        self.mysql.remove_router_from_cluster_metadata(router_id="1::system")
        self.mock_executor.execute_py.assert_called_with("\n".join(commands))

        self.mock_executor.execute_py.reset_mock()
        self.mock_executor.execute_py.side_effect = ExecutionError

        with self.assertRaises(MySQLRemoveRouterFromMetadataError):
            self.mysql.remove_router_from_cluster_metadata(router_id="1::system")

    def test_set_dynamic_variables(self):
        """Test dynamic_variables."""
        commands = ["SET @@GLOBAL.`variable` = 'value'"]
        self.mysql.set_dynamic_variable(variable="variable", value="value")
        self.mock_executor.execute_sql.assert_called_with("\n".join(commands))

        commands = ["SET @@GLOBAL.`variable` = '/a/path/value'"]
        self.mysql.set_dynamic_variable(variable="variable", value="/a/path/value")
        self.mock_executor.execute_sql.assert_called_with("\n".join(commands))

        self.mock_executor.execute_sql.reset_mock()
        self.mock_executor.execute_sql.side_effect = ExecutionError
        with self.assertRaises(MySQLSetVariableError):
            self.mysql.set_dynamic_variable(variable="variable", value="value")

    def test_set_cluster_primary(self):
        """Test set_cluster_primary."""
        commands = [
            "cluster = dba.get_cluster('test_cluster')",
            "cluster.set_primary_instance('10.0.0.2:3306')",
        ]

        self.mysql.set_cluster_primary("10.0.0.2")
        self.mock_executor.execute_py.assert_called_with("\n".join(commands))

        self.mock_executor.execute_py.reset_mock()
        self.mock_executor.execute_py.side_effect = ExecutionError()
        with self.assertRaises(MySQLSetClusterPrimaryError):
            self.mysql.set_cluster_primary("10.0.0.2")

    @patch("charms.mysql.v0.mysql.MySQLBase.get_cluster_status")
    def test_get_primary_label(self, _get_cluster_status):
        """Test get_primary_label."""
        _get_cluster_status.return_value = SHORT_CLUSTER_STATUS

        self.assertEqual(self.mysql.get_primary_label(), "mysql-k8s-1")

    @patch("charms.mysql.v0.mysql.RECOVERY_CHECK_TIME", 0.1)
    @patch("charms.mysql.v0.mysql.MySQLBase.get_member_state")
    def test_hold_if_recovering(self, mock_get_member_state):
        """Test hold_if_recovering."""
        mock_get_member_state.return_value = "ONLINE"
        self.mysql.hold_if_recovering()
        self.assertEqual(mock_get_member_state.call_count, 1)

    def test_set_instance_offline_mode(self):
        """Test execution of set_instance_offline_mode()."""
        self.mysql.set_instance_offline_mode(True)
        self.mock_executor.execute_sql.assert_called_once_with(
            "SET @@GLOBAL.`offline_mode` = 'ON'",
        )

        self.mock_executor.execute_sql.reset_mock()

        self.mock_executor.execute_sql.side_effect = ExecutionError()
        with self.assertRaises(MySQLSetInstanceOfflineModeError):
            self.mysql.set_instance_offline_mode(True)

    @patch("charms.mysql.v0.mysql.MySQLBase.get_available_memory")
    def test_render_mysqld_configuration(self, _get_available_memory):
        """Test render_mysqld_configuration."""
        # 32GB of memory, production profile
        _get_available_memory.return_value = 32341442560

        expected_config = {
            "bind_address": "0.0.0.0",
            "mysqlx_bind_address": "0.0.0.0",
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
            "loose-group_replication_paxos_single_leader": "ON",
            "innodb_buffer_pool_chunk_size": "2902458368",
            "gtid_mode": "ON",
            "enforce_gtid_consistency": "ON",
            "activate_all_roles_on_login": "ON",
            "max_connect_errors": "10000",
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

    def test_create_replica_cluster(self):
        """Test create_replica_cluster."""
        endpoint = "address:3306"
        replica_cluster_name = "replica_cluster"
        instance_label = "label"
        options = {
            "recoveryProgress": 0,
            "recoveryMethod": "",
            "timeout": 0,
            "communicationStack": "MySQL",
        }

        creation_commands = [
            "shell.connect_to_primary()",
            "cluster_set = dba.get_cluster_set()",
            f"cluster_set.create_replica_cluster('{endpoint}', '{replica_cluster_name}', {{options}})",
        ]
        updating_commands = [
            f"cluster = dba.get_cluster('{replica_cluster_name}')",
            f"cluster.set_instance_option('{endpoint}', 'label', '{instance_label}')",
        ]

        auto_options = copy.copy(options)
        auto_options["recoveryMethod"] = "auto"

        self.mysql.create_replica_cluster(endpoint, replica_cluster_name, instance_label)
        self.mock_executor.execute_py.assert_has_calls([
            call("\n".join(creation_commands).format(options=auto_options)),
            call("\n".join(updating_commands)),
        ])

        clone_options = copy.copy(options)
        clone_options["recoveryMethod"] = "clone"

        self.mock_executor.execute_py.reset_mock()
        self.mock_executor.execute_py.side_effect = ExecutionError
        with self.assertRaises(MySQLCreateReplicaClusterError):
            self.mysql.create_replica_cluster(endpoint, replica_cluster_name, instance_label)
            self.mock_executor.execute_py.assert_has_calls([
                call("\n".join(creation_commands).format(options=auto_options)),
                call("\n".join(updating_commands)),
                call("\n".join(creation_commands).format(options=clone_options)),
                call("\n".join(updating_commands)),
            ])

    def test_remove_replica_cluster(self):
        """Test remove_replica_cluster."""
        replica_cluster_name = "replica_cluster"
        commands = [
            "shell.connect_to_primary()",
            "cluster_set = dba.get_cluster_set()",
            f"cluster_set.remove_cluster('{replica_cluster_name}', {{'force': 'False'}})",
        ]
        self.mysql.remove_replica_cluster(replica_cluster_name)
        self.mock_executor.execute_py.assert_called_with("\n".join(commands))
        self.mock_executor.execute_py.reset_mock()

        commands = [
            "shell.connect_to_primary()",
            "cluster_set = dba.get_cluster_set()",
            f"cluster_set.remove_cluster('{replica_cluster_name}', {{'force': 'True'}})",
        ]
        self.mysql.remove_replica_cluster(replica_cluster_name, force=True)
        self.mock_executor.execute_py.assert_called_with("\n".join(commands))
        self.mock_executor.execute_py.reset_mock()

        self.mock_executor.execute_py.side_effect = ExecutionError
        with self.assertRaises(MySQLRemoveReplicaClusterError):
            self.mysql.remove_replica_cluster(replica_cluster_name)

    @patch("charms.mysql.v0.mysql.MySQLBase.get_cluster_set_status")
    def test_get_replica_cluster_status(self, _get_cluster_set_status):
        """Test get_replica_cluster_status."""
        replica_cluster_name = "replica_cluster"
        replica_cluster_status = ClusterGlobalStatus.OK

        _get_cluster_set_status.return_value = {
            "clusters": {
                replica_cluster_name: {
                    "globalStatus": replica_cluster_status,
                }
            }
        }
        status = self.mysql.get_replica_cluster_status(replica_cluster_name)
        self.assertEqual(status, replica_cluster_status)

        _get_cluster_set_status.return_value = None
        status = self.mysql.get_replica_cluster_status(replica_cluster_name)
        self.assertEqual(status, ClusterGlobalStatus.UNKNOWN)

    def test_get_cluster_node_count(self):
        """Test get_cluster_node_count."""
        self.mock_executor.execute_sql.return_value = [
            {"member_id": "1"},
            {"member_id": "2"},
        ]

        count = self.mysql.get_cluster_node_count(node_status=InstanceState.ONLINE)
        self.assertEqual(count, 2)

        self.mock_executor.execute_sql.side_effect = ExecutionError
        count = self.mysql.get_cluster_node_count()
        self.assertEqual(count, 0)

    def test_get_cluster_global_primary_address(self):
        """Test get_cluster_set_global_primary."""
        self.mock_executor.execute_py.return_value = (
            "{"
            '   "clusters": {"db1": {"globalStatus": "OK", "primary": "mysql-k8s-1"}},'
            '   "primaryCluster": "db1"'
            "}"
        )
        primary = self.mysql.get_cluster_global_primary_address()
        self.assertEqual(primary, "mysql-k8s-1")

        self.mock_executor.execute_py.reset_mock()

        self.mock_executor.execute_py.side_effect = ExecutionError
        with self.assertRaises(MySQLGetClusterPrimaryAddressError):
            self.mysql.get_cluster_global_primary_address()

    def test_is_cluster_auto_rejoin_ongoing(self):
        """Test is_cluster_auto_rejoin_ongoing."""
        self.mock_executor.execute_sql.return_value = [{"work_completed": 1, "work_estimated": 3}]
        assert self.mysql.is_cluster_auto_rejoin_ongoing() is True

        self.mock_executor.execute_sql.return_value = [{"work_completed": 3, "work_estimated": 3}]
        assert self.mysql.is_cluster_auto_rejoin_ongoing() is False

        self.mock_executor.execute_sql.return_value = []
        self.mock_executor.execute_sql.side_effect = ExecutionError
        with self.assertRaises(ExecutionError):
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

    @patch("charms.mysql.v0.mysql.MySQLBase._plugin_file_exists", return_value=True)
    @patch("charms.mysql.v0.mysql.MySQLBase._read_only_disabled")
    def test_install_plugin(self, _read_only_disabled, _plugin_file_exists):
        """Test install_plugin."""
        # ensure no install if already installed
        self.mock_executor.execute_sql.return_value = [{"name": "plugin1"}]
        self.mysql.install_plugins(["plugin1"])
        self.mock_executor.execute_sql.assert_has_calls([
            call("SELECT name FROM mysql.plugin WHERE name LIKE '%'"),
        ])
        self.mock_executor.execute_sql.reset_mock()

        # ensure not installed if unsupported
        self.mock_executor.execute_sql.return_value = []
        self.mysql.install_plugins(["plugin1"])
        self.mock_executor.execute_sql.assert_has_calls([
            call("SELECT name FROM mysql.plugin WHERE name LIKE '%'"),
        ])
        self.mock_executor.execute_sql.reset_mock()

        # ensure installed
        self.mock_executor.execute_sql.return_value = []
        self.mysql.install_plugins(["audit_log"])
        self.mock_executor.execute_sql.assert_has_calls([
            call("SELECT name FROM mysql.plugin WHERE name LIKE '%'"),
            call("INSTALL PLUGIN `audit_log` SONAME 'audit_log.so'"),
        ])

    @patch("charms.mysql.v0.mysql.MySQLBase._read_only_disabled")
    def test_uninstall_plugin(self, _read_only_disabled):
        """Test uninstall_plugin."""
        # ensure not uninstalled if not installed
        self.mock_executor.execute_sql.return_value = []
        self.mysql.uninstall_plugins(["plugin1"])
        self.mock_executor.execute_sql.assert_has_calls([
            call("SELECT name FROM mysql.plugin WHERE name LIKE '%'"),
        ])

        self.mock_executor.execute_sql.reset_mock()

        # ensure uninstalled
        self.mock_executor.execute_sql.return_value = [{"name": "audit_log"}]
        self.mysql.uninstall_plugins(["audit_log"])
        self.mock_executor.execute_sql.assert_has_calls([
            call("SELECT name FROM mysql.plugin WHERE name LIKE '%'"),
            call("UNINSTALL PLUGIN `audit_log`"),
        ])

    def test_strip_off_password(self):
        _input = """
("Traceback (most recent call last):",
  File "/var/lib/juju/agents/unit-mysql-k8s-edge-0/charm/src/mysql_k8s_helpers.py", line 642, in _run_mysqlsh_script
    stdout, _ = process.wait_output()
  File "/var/lib/juju/agents/unit-mysql-k8s-edge-0/charm/venv/lib/python3.10/site-packages/ops/pebble.py", line 1771, in wait_output
    raise ExecError[AnyStr](self._command, exit_code, out_value, err_value)
ops.pebble.ExecError: non-zero exit code 1 executing ['/usr/bin/mysqlsh', '--passwords-from-stdin', '--uri=serverconfig@mysql-k8s-edge-0.mysql-k8s-edge-endpoints.stg-alutay-datasql-juju361.svc.cluster.local:33062', '--python', '--verbose=0', '-c', 'shell.options.set(\'useWizards\', False)\nprint(\'###\')\nsh$
ll.connect_to_primary()\nsession.run_sql("CREATE DATABASE IF NOT EXISTS `continuous_writes`;")\nsession.run_sql("CREATE USER `relation-21_ff7306c7454f44`@`%` IDENTIFIED BY \'s1ffxPedAmX58aOdCRSzxEpm\' ATTRIBUTE \'{}\';")\nsession.run_sql("GRANT USAGE ON *.* TO `relation-21_ff7306c7454f44`@`%`;")\nses
sion.run_sql("GRANT ALL PRIVILEGES ON `continuous_writes`.* TO `relation-21_ff7306c7454f44`@`%`;")'], stdout="\x1b[1mPlease provide the password for 'serverconfig@mysql-k8s-edge-0.mysql-k8s-edge-endpoints.stg-alutay-datasql-juju361.svc.cluster.local:33062': \x1b[0m###\n", stderr='Cannot set LC_ALL to
 locale en_US.UTF-8: No such file or directory\n\x1b[36mNOTE: \x1b[0mAlready connected to a PRIMARY.\nTraceback (most recent call last):\n  File "<string>", line 5, in <module>\nmysqlsh.DBError: MySQL Error (1396): ClassicSession.run_sql: Operation CREATE USER failed for \'relation-21_ff7306c7454f44\'@\'%\'\n
"""
        output = self.mysql.strip_off_passwords(_input)
        self.assertTrue("s1ffxPedAmX58aOdCRSzxEpm" not in output)

    def test_abstract_methods(self):
        """Test abstract methods."""
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
