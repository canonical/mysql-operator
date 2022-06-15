# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import call, patch

from charms.mysql.v0.mysql import (
    MySQLCheckUserExistenceError,
    MySQLConfigureInstanceError,
    MySQLConfigureMySQLUsersError,
    MySQLConfigureRouterUserError,
    MySQLCreateApplicationDatabaseAndScopedUserError,
    MySQLCreateClusterError,
    MySQLInitializeJujuOperationsTableError,
)
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus
from ops.testing import Harness

from charm import MySQLOperatorCharm
from tests.unit.helpers import patch_network_get


class TestCharm(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(MySQLOperatorCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()
        self.peer_relation_id = self.harness.add_relation("database-peers", "database-peers")
        self.harness.add_relation_unit(self.peer_relation_id, "mysql/1")
        self.db_router_relation_id = self.harness.add_relation("db-router", "app")
        self.shared_db_relation_id = self.harness.add_relation("shared-db", "other-app")
        self.harness.add_relation_unit(self.db_router_relation_id, "app/0")
        self.harness.add_relation_unit(self.shared_db_relation_id, "other-app/0")
        self.charm = self.harness.charm

    @patch("mysqlsh_helpers.MySQL.install_and_configure_mysql_dependencies")
    def test_on_install(self, _install_and_configure_mysql_dependencies):
        self.charm.on.install.emit()

        self.assertTrue(isinstance(self.harness.model.unit.status, WaitingStatus))

    @patch(
        "mysqlsh_helpers.MySQL.install_and_configure_mysql_dependencies", side_effect=Exception()
    )
    def test_on_install_exception(self, _install_and_configure_mysql_dependencies):
        self.charm.on.install.emit()

        self.assertTrue(isinstance(self.harness.model.unit.status, BlockedStatus))

    def test_on_leader_elected_sets_mysql_passwords_in_peer_databag(self):
        # ensure that the peer relation databag is empty
        peer_relation_databag = self.harness.get_relation_data(
            self.peer_relation_id, self.harness.charm.app
        )
        self.assertEqual(peer_relation_databag, {})

        # trigger the leader_elected event
        self.harness.set_leader(True)

        # ensure passwords set in the peer relation databag
        peer_relation_databag = self.harness.get_relation_data(
            self.peer_relation_id, self.harness.charm.app
        )
        expected_peer_relation_databag_keys = [
            "root-password",
            "server-config-password",
            "cluster-admin-password",
        ]
        self.assertEqual(
            sorted(peer_relation_databag.keys()), sorted(expected_peer_relation_databag_keys)
        )

    def test_on_config_changed_sets_config_cluster_name_in_peer_databag(self):
        # ensure that the peer relation databag is empty
        peer_relation_databag = self.harness.get_relation_data(
            self.peer_relation_id, self.harness.charm.app
        )
        self.assertEqual(peer_relation_databag, {})

        # trigger the leader_elected and config_changed events
        self.harness.set_leader(True)
        self.harness.update_config({"cluster-name": "test-cluster"})

        # ensure that the peer relation has 'cluster_name' set to the config value
        peer_relation_databag = self.harness.get_relation_data(
            self.peer_relation_id, self.harness.charm.app
        )

        self.assertEqual(peer_relation_databag["cluster-name"], "test-cluster")

    def test_on_config_changed_sets_random_cluster_name_in_peer_databag(self):
        # ensure that the peer relation databag is empty
        peer_relation_databag = self.harness.get_relation_data(
            self.peer_relation_id, self.harness.charm.app
        )
        self.assertEqual(peer_relation_databag, {})

        # trigger the leader_elected and config_changed events
        self.harness.set_leader(True)
        self.charm.on.config_changed.emit()

        # ensure that the peer relation has a randomly generated 'cluster_name'
        peer_relation_databag = self.harness.get_relation_data(
            self.peer_relation_id, self.harness.charm.app
        )

        self.assertIsNotNone(peer_relation_databag["cluster-name"])

    @patch_network_get(private_address="1.1.1.1")
    @patch("mysqlsh_helpers.MySQL.wait_until_mysql_connection")
    @patch("mysqlsh_helpers.MySQL.configure_mysql_users")
    @patch("mysqlsh_helpers.MySQL.configure_instance")
    @patch("mysqlsh_helpers.MySQL.initialize_juju_units_operations_table")
    @patch("mysqlsh_helpers.MySQL.create_cluster")
    def test_on_start(
        self,
        _create_cluster,
        _initialize_juju_units_operations_table,
        _configure_instance,
        _configure_mysql_users,
        _wait_until_mysql_connection,
    ):
        # execute on_leader_elected and config_changed to populate the peer databag
        self.harness.set_leader(True)
        self.charm.on.config_changed.emit()

        self.charm.on.start.emit()

        self.assertTrue(isinstance(self.harness.model.unit.status, ActiveStatus))

    @patch_network_get(private_address="1.1.1.1")
    @patch("mysqlsh_helpers.MySQL.configure_mysql_users")
    @patch("mysqlsh_helpers.MySQL.configure_instance")
    @patch("mysqlsh_helpers.MySQL.initialize_juju_units_operations_table")
    @patch("mysqlsh_helpers.MySQL.create_cluster")
    def test_on_start_exceptions(
        self,
        _create_cluster,
        _initialize_juju_units_operations_table,
        _configure_instance,
        _configure_mysql_users,
    ):
        # execute on_leader_elected and config_changed to populate the peer databag
        self.harness.set_leader(True)
        self.charm.on.config_changed.emit()

        # test an exception while configuring mysql users
        _configure_mysql_users.side_effect = MySQLConfigureMySQLUsersError

        self.charm.on.start.emit()
        self.assertTrue(isinstance(self.harness.model.unit.status, BlockedStatus))

        _configure_mysql_users.reset_mock()

        # test an exception while configuring the instance
        _configure_instance.side_effect = MySQLConfigureInstanceError

        self.charm.on.start.emit()
        self.assertTrue(isinstance(self.harness.model.unit.status, BlockedStatus))

        _configure_instance.reset_mock()

        # test an exception initializing the mysql.juju_units_operations table
        _initialize_juju_units_operations_table.side_effect = (
            MySQLInitializeJujuOperationsTableError
        )

        self.charm.on.start.emit()
        self.assertTrue(isinstance(self.harness.model.unit.status, BlockedStatus))

        _initialize_juju_units_operations_table.reset_mock()

        # test an exception with creating a cluster
        _create_cluster.side_effect = MySQLCreateClusterError

        self.charm.on.start.emit()
        self.assertTrue(isinstance(self.harness.model.unit.status, BlockedStatus))

    @patch_network_get(private_address="1.1.1.1")
    @patch("charm.generate_random_password", return_value="super_secure_password")
    @patch("mysqlsh_helpers.MySQL.does_mysql_user_exist", return_value=False)
    @patch("mysqlsh_helpers.MySQL.configure_mysqlrouter_user")
    @patch("mysqlsh_helpers.MySQL.create_application_database_and_scoped_user")
    def test_db_router_relation_changed(
        self,
        _create_application_database_and_scoped_user,
        _configure_mysqlrouter_user,
        _does_mysql_user_exist,
        _generate_random_password,
    ):
        # run start-up events to enable usage of the helper class
        self.harness.set_leader(True)
        self.charm.on.config_changed.emit()

        # confirm that the relation databag is empty
        db_router_relation_databag = self.harness.get_relation_data(
            self.db_router_relation_id, self.harness.charm.app
        )
        db_router_relation = self.charm.model.get_relation("db-router")
        app_unit = list(db_router_relation.units)[0]

        self.assertEqual(db_router_relation_databag, {})
        self.assertEqual(db_router_relation.data.get(app_unit), {})
        self.assertEqual(db_router_relation.data.get(self.charm.unit), {})

        # update the app leader unit data to trigger db_router_relation_changed event
        self.harness.update_relation_data(
            self.db_router_relation_id,
            "app/0",
            {
                "MRUP_database": "keystone_database",
                "MRUP_hostname": "1.1.1.2",
                "MRUP_username": "keystone_user",
                "mysqlrouter_hostname": "1.1.1.3",
                "mysqlrouter_username": "mysqlrouteruser",
            },
        )

        # 4 calls during start-up events, and 2 calls during the db_router_relation_changed event
        self.assertEqual(_generate_random_password.call_count, 6)

        self.assertEqual(_does_mysql_user_exist.call_count, 2)
        self.assertEqual(
            sorted(_does_mysql_user_exist.mock_calls),
            sorted(
                [
                    call("mysqlrouteruser"),
                    call("keystone_user"),
                ]
            ),
        )

        _configure_mysqlrouter_user.assert_called_once_with(
            "mysqlrouteruser", "super_secure_password"
        )
        _create_application_database_and_scoped_user.assert_called_once_with(
            "keystone_database", "keystone_user", "super_secure_password"
        )

        # confirm that credentials in the mysql leader unit databag is set correctly
        self.assertEqual(
            db_router_relation.data.get(app_unit),
            {
                "MRUP_database": "keystone_database",
                "MRUP_hostname": "1.1.1.2",
                "MRUP_username": "keystone_user",
                "mysqlrouter_hostname": "1.1.1.3",
                "mysqlrouter_username": "mysqlrouteruser",
            },
        )

        self.assertEqual(
            db_router_relation.data.get(self.charm.unit),
            {
                "db_host": '"1.1.1.1"',
                "mysqlrouter_password": '"super_secure_password"',
                "mysqlrouter_allowed_units": '"app/0"',
                "MRUP_password": '"super_secure_password"',
                "MRUP_allowed_units": '"app/0"',
            },
        )

    @patch_network_get(private_address="1.1.1.1")
    @patch("charm.generate_random_password", return_value="super_secure_password")
    @patch("mysqlsh_helpers.MySQL.does_mysql_user_exist", return_value=False)
    @patch("mysqlsh_helpers.MySQL.configure_mysqlrouter_user")
    @patch("mysqlsh_helpers.MySQL.create_application_database_and_scoped_user")
    def test_db_router_relation_changed_exceptions(
        self,
        _create_application_database_and_scoped_user,
        _configure_mysqlrouter_user,
        _does_mysql_user_exist,
        _generate_random_password,
    ):
        # run start-up events to enable usage of the helper class
        self.harness.set_leader(True)
        self.charm.on.config_changed.emit()

        # confirm that the relation databag is empty
        db_router_relation_databag = self.harness.get_relation_data(
            self.db_router_relation_id, self.harness.charm.app
        )
        db_router_relation = self.charm.model.get_relation("db-router")
        app_unit = list(db_router_relation.units)[0]

        self.assertEqual(db_router_relation_databag, {})
        self.assertEqual(db_router_relation.data.get(app_unit), {})
        self.assertEqual(db_router_relation.data.get(self.charm.unit), {})

        # test an exception while configuring mysql users
        _does_mysql_user_exist.side_effect = MySQLCheckUserExistenceError
        self.harness.update_relation_data(
            self.db_router_relation_id,
            "app/0",
            {
                "MRUP_database": "keystone_database",
                "MRUP_hostname": "1.1.1.2",
                "MRUP_username": "keystone_user",
                "mysqlrouter_hostname": "1.1.1.3",
                "mysqlrouter_username": "mysqlrouteruser",
            },
        )

        self.assertTrue(isinstance(self.harness.model.unit.status, BlockedStatus))

        _does_mysql_user_exist.reset_mock()

        # test an exception while creating the mysql router user
        _configure_mysqlrouter_user.side_effect = MySQLConfigureRouterUserError
        self.harness.update_relation_data(
            self.db_router_relation_id,
            "app/0",
            {
                "MRUP_database": "keystone_database",
                "MRUP_hostname": "1.1.1.2",
                "MRUP_username": "keystone_user",
                "mysqlrouter_hostname": "1.1.1.3",
                "mysqlrouter_username": "mysqlrouteruser",
            },
        )

        self.assertTrue(isinstance(self.harness.model.unit.status, BlockedStatus))

        _configure_mysqlrouter_user.reset_mock()

        # test an exception while creating the application database and scoped user
        _create_application_database_and_scoped_user.side_effect = (
            MySQLCreateApplicationDatabaseAndScopedUserError
        )
        self.harness.update_relation_data(
            self.db_router_relation_id,
            "app/0",
            {
                "MRUP_database": "keystone_database",
                "MRUP_hostname": "1.1.1.2",
                "MRUP_username": "keystone_user",
                "mysqlrouter_hostname": "1.1.1.3",
                "mysqlrouter_username": "mysqlrouteruser",
            },
        )

        self.assertTrue(isinstance(self.harness.model.unit.status, BlockedStatus))

        _create_application_database_and_scoped_user.reset_mock()

    @patch_network_get(private_address="1.1.1.1")
    @patch("mysqlsh_helpers.MySQL.get_cluster_primary_address", return_value="1.1.1.1")
    @patch("charm.generate_random_password", return_value="super_secure_password")
    @patch("mysqlsh_helpers.MySQL.create_application_database_and_scoped_user")
    def test_shared_db_relation_changed(
        self,
        _create_application_database_and_scoped_user,
        _generate_random_password,
        _get_cluster_primary_address,
    ):
        # run start-up events to enable usage of the helper class
        self.harness.set_leader(True)
        self.charm.on.config_changed.emit()

        # confirm that the relation databag is empty
        shared_db_relation_databag = self.harness.get_relation_data(
            self.shared_db_relation_id, self.harness.charm.app
        )
        shared_db_relation = self.charm.model.get_relation("shared-db")
        app_unit = list(shared_db_relation.units)[0]

        self.assertEqual(shared_db_relation_databag, {})
        self.assertEqual(shared_db_relation.data.get(app_unit), {})
        self.assertEqual(shared_db_relation.data.get(self.charm.unit), {})

        # update the app leader unit data to trigger shared_db_relation_changed event
        self.harness.update_relation_data(
            self.shared_db_relation_id,
            "other-app/0",
            {
                "database": "shared_database",
                "hostname": "1.1.1.2",
                "username": "shared_user",
            },
        )

        # 4 calls during start-up events, and 1 calls during the shared_db_relation_changed event
        self.assertEqual(_generate_random_password.call_count, 5)
        _create_application_database_and_scoped_user.assert_called_once_with(
            "shared_database", "shared_user", "super_secure_password"
        )

        # confirm that the relation databag is populated
        self.assertEqual(
            shared_db_relation.data.get(self.charm.unit),
            {
                "db_host": "1.1.1.1",
                "db_port": "3306",
                "wait_timeout": "3600",
                "password": "super_secure_password",
                "allowed_units": "other-app/0",
            },
        )

        # Confirm that user is registered with the relation
        self.assertEqual(
            shared_db_relation.data.get(self.charm.app),
            {
                f"relation_id_{self.shared_db_relation_id}_db_user": "shared_user",
                f"relation_id_{self.shared_db_relation_id}_db_name": "shared_database",
            },
        )

    @patch_network_get(private_address="1.1.1.1")
    @patch("charm.generate_random_password", return_value="super_secure_password")
    @patch("mysqlsh_helpers.MySQL.create_application_database_and_scoped_user")
    def test_shared_db_relation_changed_error_on_user_creation(
        self, _create_application_database_and_scoped_user, _generate_random_password
    ):
        # run start-up events to enable usage of the helper class
        self.harness.set_leader(True)
        self.charm.on.config_changed.emit()

        _create_application_database_and_scoped_user.side_effect = (
            MySQLCreateApplicationDatabaseAndScopedUserError("Can't create user")
        )
        # update the app leader unit data to trigger shared_db_relation_changed event
        self.harness.update_relation_data(
            self.shared_db_relation_id,
            "other-app/0",
            {
                "database": "shared_database",
                "hostname": "1.1.1.2",
                "username": "shared_user",
            },
        )

        self.assertTrue(isinstance(self.harness.model.unit.status, BlockedStatus))

        _create_application_database_and_scoped_user.reset_mock()

    @patch_network_get(private_address="1.1.1.1")
    @patch("charm.MySQLOperatorCharm._on_shared_db_departed")
    @patch("mysqlsh_helpers.MySQL.get_cluster_primary_address", return_value="1.1.1.1")
    @patch("mysqlsh_helpers.MySQL.remove_user")
    @patch("charm.generate_random_password", return_value="super_secure_password")
    @patch("mysqlsh_helpers.MySQL.create_application_database_and_scoped_user")
    def test_shared_db_relation_broken(
        self,
        _create_application_database_and_scoped_user,
        _generate_random_password,
        _remove_user,
        _get_cluster_primary_address,
        _on_shared_db_departed,
    ):
        # run start-up events to enable usage of the helper class
        self.harness.set_leader(True)
        self.charm.on.config_changed.emit()

        shared_db_relation = self.charm.model.get_relation("shared-db")
        # update the app leader unit data to trigger shared_db_relation_changed event
        self.harness.update_relation_data(
            self.shared_db_relation_id,
            "other-app/0",
            {
                "database": "shared_database",
                "hostname": "1.1.1.2",
                "username": "shared_user",
            },
        )

        self.harness.remove_relation(self.shared_db_relation_id)

        _remove_user.assert_called_once_with("shared_user")

        self.assertEqual(shared_db_relation.data.get(self.charm.app), {})
