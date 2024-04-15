# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import patch

from ops.testing import Harness

from charm import MySQLOperatorCharm
from charms.mysql.v0.mysql import RouterUser
from constants import DB_RELATION_NAME

from .helpers import patch_network_get


class TestDatase(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(MySQLOperatorCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()
        self.peer_relation_id = self.harness.add_relation("database-peers", "database-peers")
        self.harness.add_relation_unit(self.peer_relation_id, "mysql/1")
        self.database_relation_id = self.harness.add_relation(DB_RELATION_NAME, "app")
        self.harness.add_relation_unit(self.database_relation_id, "app/0")
        self.charm = self.harness.charm

    @patch_network_get(private_address="1.1.1.1")
    @patch("mysql_vm_helpers.MySQL.get_mysql_version", return_value="8.0.29-0ubuntu0.20.04.3")
    @patch(
        "mysql_vm_helpers.MySQL.get_cluster_endpoints",
        return_value=("2.2.2.2:3306", "2.2.2.1:3306,2.2.2.3:3306", ""),
    )
    @patch("mysql_vm_helpers.MySQL.create_application_database_and_scoped_user")
    @patch(
        "relations.mysql_provider.generate_random_password", return_value="super_secure_password"
    )
    def test_database_requested(
        self,
        _generate_random_password,
        _create_application_database_and_scoped_user,
        _get_cluster_endpoints,
        _get_mysql_version,
    ):
        # run start-up events to enable usage of the helper class
        self.harness.set_leader(True)
        self.charm.on.config_changed.emit()

        # confirm that the relation databag is empty
        database_relation_databag = self.harness.get_relation_data(
            self.database_relation_id, self.harness.charm.app
        )
        database_relation = self.charm.model.get_relation(DB_RELATION_NAME)
        app_unit = list(database_relation.units)[0]

        # simulate cluster initialized by editing the flag
        self.harness.update_relation_data(
            self.peer_relation_id, self.charm.app.name, {"units-added-to-cluster": "1"}
        )

        self.assertEqual(database_relation_databag, {})
        self.assertEqual(database_relation.data.get(app_unit), {})
        self.assertEqual(database_relation.data.get(self.charm.unit), {})

        # update the app leader unit data to trigger database_requested event
        self.harness.update_relation_data(
            self.database_relation_id, "app", {"database": "test_db"}
        )

        self.assertEqual(
            database_relation_databag,
            {
                "data": '{"database": "test_db"}',
                "password": "super_secure_password",
                "username": f"relation-{self.database_relation_id}",
                "endpoints": "2.2.2.2:3306",
                "version": "8.0.29-0ubuntu0.20.04.3",
                "database": "test_db",
                "read-only-endpoints": "2.2.2.1:3306,2.2.2.3:3306",
            },
        )

        _generate_random_password.assert_called_once()
        _create_application_database_and_scoped_user.assert_called_once()
        _get_cluster_endpoints.assert_called_once()
        _get_mysql_version.assert_called_once()

    @patch("relations.mysql_provider.MySQLProvider._on_database_broken")
    @patch("mysql_vm_helpers.MySQL.remove_router_from_cluster_metadata")
    @patch("mysql_vm_helpers.MySQL.delete_user")
    @patch("mysql_vm_helpers.MySQL.get_mysql_router_users_for_unit")
    def test_relation_departed(
        self,
        _get_users,
        _delete_user,
        _remove_router,
        _on_database_broken,
    ):
        self.harness.set_leader(True)

        router_user = RouterUser(username="user1", router_id="router_id")
        _get_users.return_value = [router_user]

        self.harness.remove_relation(self.database_relation_id)
        _delete_user.assert_called_once_with("user1")
        _remove_router.assert_called_once_with("router_id")

    def test_remove_unit_from_endpoints(self):
        self.harness.set_leader(True)
        self.charm.on.config_changed.emit()
        self.harness.update_relation_data(
            self.peer_relation_id, self.charm.app.name, {"units-added-to-cluster": "1"}
        )

        self.harness.update_relation_data(
            self.database_relation_id,
            self.charm.app.name,
            {
                "data": '{"database": "test_db"}',
                "password": "super_secure_password",
                "username": f"relation-{self.database_relation_id}",
                "endpoints": "2.2.2.2:3306",
                "version": "8.0.36-0ubuntu0.22.04.3",
                "database": "test_db",
                "read-only-endpoints": "2.2.2.1:3306",
            },
        )

        remove_unit = self.harness.model.get_unit("mysql/1")
        with patch("charm.MySQLOperatorCharm.get_unit_ip", return_value="2.2.2.1"):
            self.charm.database_relation.remove_unit_from_endpoints(remove_unit)

        relation_data = self.harness.get_relation_data(
            self.database_relation_id, self.charm.app.name
        )

        self.assertNotIn("read-only-endpoints", relation_data.keys())
