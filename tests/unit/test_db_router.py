# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import call, patch

from charms.mysql.v0.mysql import (
    MySQLCheckUserExistenceError,
    MySQLConfigureRouterUserError,
    MySQLCreateApplicationDatabaseError,
    MySQLCreateApplicationScopedUserError,
)
from ops.model import BlockedStatus
from ops.testing import Harness

from charm import MySQLOperatorCharm


@patch("charms.rolling_ops.v0.rollingops.RollingOpsManager._on_process_locks")
class TestDBRouter(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(MySQLOperatorCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()
        self.peer_relation_id = self.harness.add_relation("database-peers", "database-peers")
        self.harness.add_relation_unit(self.peer_relation_id, "mysql/1")
        self.db_router_relation_id = self.harness.add_relation("db-router", "app")
        self.harness.add_relation_unit(self.db_router_relation_id, "app/0")
        self.charm = self.harness.charm

    @patch("relations.db_router.DBRouterRelation._on_leader_elected")
    @patch("charm.MySQLOperatorCharm.unit_initialized", return_value=True)
    @patch("relations.db_router.generate_random_password", return_value="super_secure_password")
    @patch("mysql_vm_helpers.MySQL.get_cluster_primary_address", return_value="2.2.2.2")
    @patch("mysql_vm_helpers.MySQL.does_mysql_user_exist", return_value=False)
    @patch("mysql_vm_helpers.MySQL.configure_mysqlrouter_user")
    @patch("mysql_vm_helpers.MySQL.create_database")
    @patch("mysql_vm_helpers.MySQL.create_scoped_user")
    def test_db_router_relation_changed(
        self,
        _create_scoped_user,
        _create_database,
        _configure_mysqlrouter_user,
        _does_mysql_user_exist,
        _get_cluster_primary_address,
        _generate_random_password,
        _,
        _unit_initialized,
        _on_leader_elected,
    ):
        # run start-up events to enable usage of the helper class
        self.harness.set_leader(True)
        self.charm.on.config_changed.emit()

        # confirm that the relation databag is empty
        db_router_relation_databag = self.harness.get_relation_data(
            self.db_router_relation_id, self.harness.charm.app
        )
        db_router_relation = self.charm.model.get_relation("db-router")
        app_unit = next(iter(db_router_relation.units))

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

        self.assertEqual(_generate_random_password.call_count, 2)
        self.assertEqual(_does_mysql_user_exist.call_count, 2)
        self.assertEqual(
            sorted(_does_mysql_user_exist.mock_calls),
            sorted([
                call("mysqlrouteruser", "1.1.1.3"),
                call("keystone_user", "1.1.1.2"),
            ]),
        )

        _configure_mysqlrouter_user.assert_called_once_with(
            "mysqlrouteruser", "super_secure_password", "1.1.1.3", "app/0"
        )
        _create_database.assert_called_once_with(
            "keystone_database",
        )
        _create_scoped_user.assert_called_once_with(
            "keystone_database",
            "keystone_user",
            "super_secure_password",
            "1.1.1.2",
            unit_name="app/0",
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
                "db_host": '"2.2.2.2"',
                "mysqlrouter_password": '"super_secure_password"',
                "mysqlrouter_allowed_units": '"app/0"',
                "MRUP_password": '"super_secure_password"',
                "MRUP_allowed_units": '"app/0"',
            },
        )

    @patch("relations.db_router.DBRouterRelation._on_leader_elected")
    @patch("charm.MySQLOperatorCharm.unit_initialized", return_value=True)
    @patch("relations.db_router.generate_random_password", return_value="super_secure_password")
    @patch("mysql_vm_helpers.MySQL.does_mysql_user_exist", return_value=False)
    @patch("mysql_vm_helpers.MySQL.configure_mysqlrouter_user")
    @patch("mysql_vm_helpers.MySQL.create_database")
    @patch("mysql_vm_helpers.MySQL.create_scoped_user")
    def test_db_router_relation_changed_exceptions(
        self,
        _create_scoped_user,
        _create_database,
        _configure_mysqlrouter_user,
        _does_mysql_user_exist,
        _generate_random_password,
        _,
        _unit_initialized,
        _on_leader_elected,
    ):
        # run start-up events to enable usage of the helper class
        self.harness.set_leader(True)
        self.charm.on.config_changed.emit()

        # confirm that the relation databag is empty
        db_router_relation_databag = self.harness.get_relation_data(
            self.db_router_relation_id, self.harness.charm.app
        )
        db_router_relation = self.charm.model.get_relation("db-router")
        app_unit = next(iter(db_router_relation.units))

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

        # test an exception while creating the application database
        _create_database.side_effect = MySQLCreateApplicationDatabaseError
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

        _create_database.reset_mock()
        _create_scoped_user.reset_mock()

        # test an exception while creating the application scoped user
        _create_scoped_user.side_effect = MySQLCreateApplicationScopedUserError
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

        _create_database.reset_mock()
        _create_scoped_user.reset_mock()
