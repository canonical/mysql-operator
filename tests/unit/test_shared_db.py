# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import patch

from ops.model import BlockedStatus
from ops.testing import Harness

from charm import MySQLOperatorCharm
from charms.mysql.v0.mysql import MySQLCreateApplicationDatabaseAndScopedUserError
from constants import LEGACY_DB_SHARED
from tests.unit.helpers import patch_network_get


class TestSharedDBRelation(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(MySQLOperatorCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()
        self.peer_relation_id = self.harness.add_relation("database-peers", "database-peers")
        self.harness.add_relation_unit(self.peer_relation_id, "mysql/1")
        self.shared_db_relation_id = self.harness.add_relation("shared-db", "other-app")
        self.harness.add_relation_unit(self.shared_db_relation_id, "other-app/0")
        self.charm = self.harness.charm

    @patch_network_get(private_address="1.1.1.1")
    @patch("mysqlsh_helpers.MySQL.get_cluster_primary_address", return_value="1.1.1.1")
    @patch("relations.shared_db.generate_random_password", return_value="super_secure_password")
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
        shared_db_relation = self.charm.model.get_relation(LEGACY_DB_SHARED)
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
                "private-address": "1.1.1.3",
            },
        )

        # 2 calls during start-up events, and 1 calls during the shared_db_relation_changed event
        self.assertEqual(_generate_random_password.call_count, 1)
        _create_application_database_and_scoped_user.assert_called_once_with(
            "shared_database", "shared_user", "super_secure_password", "1.1.1.3", "other-app/0"
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

    @patch_network_get(private_address="1.1.1.1")
    @patch("utils.generate_random_password", return_value="super_secure_password")
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
    @patch("relations.shared_db.SharedDBRelation._on_shared_db_departed")
    @patch("mysqlsh_helpers.MySQL.get_cluster_primary_address", return_value="1.1.1.1:3306")
    @patch("mysqlsh_helpers.MySQL.delete_users_for_unit")
    @patch("relations.shared_db.generate_random_password", return_value="super_secure_password")
    @patch("mysqlsh_helpers.MySQL.create_application_database_and_scoped_user")
    def test_shared_db_relation_departed(
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

        shared_db_relation = self.charm.model.get_relation(LEGACY_DB_SHARED)
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

        self.harness.remove_relation_unit(self.shared_db_relation_id, "other-app/0")
        # self.charm.on[LEGACY_DB_SHARED].relation_departed.emit(shared_db_relation)

        _remove_user.assert_called_once_with("other-app/0")

        self.assertEqual(shared_db_relation.data.get(self.charm.app), {})
