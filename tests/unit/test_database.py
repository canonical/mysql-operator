# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import PropertyMock, patch

from ops.testing import Harness

from charm import MySQLOperatorCharm
from constants import DB_RELATION_NAME


class TestDatabase(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(MySQLOperatorCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()
        self.peer_relation_id = self.harness.add_relation("database-peers", "database-peers")
        self.harness.add_relation_unit(self.peer_relation_id, "mysql/1")
        self.database_relation_id = self.harness.add_relation(DB_RELATION_NAME, "app")
        self.harness.add_relation_unit(self.database_relation_id, "app/0")
        self.charm = self.harness.charm

    @patch("charm.MySQLOperatorCharm.unit_initialized")
    @patch("charm.MySQLOperatorCharm.cluster_initialized", new_callable=PropertyMock)
    @patch(
        "charm.MySQLOperatorCharm.get_cluster_endpoints",
        return_value=("2.2.2.2:3306", "2.2.2.1:3306,2.2.2.3:3306", ""),
    )
    @patch("mysql_vm_helpers.MySQL.get_mysql_version", return_value="8.0.29-0ubuntu0.20.04.3")
    @patch("mysql_vm_helpers.MySQL.create_application_database_and_scoped_user")
    @patch(
        "relations.mysql_provider.generate_random_password", return_value="super_secure_password"
    )
    def test_database_requested(
        self,
        _generate_random_password,
        _create_application_database_and_scoped_user,
        _get_mysql_version,
        _get_cluster_endpoints,
        _cluster_initialized,
        _unit_initialized,
    ):
        _unit_initialized.return_value = False
        _cluster_initialized.return_value = False
        # run start-up events to enable usage of the helper class
        with patch("charms.rolling_ops.v0.rollingops.RollingOpsManager._on_process_locks") as _:
            self.harness.set_leader(True)
        self.charm.on.config_changed.emit()

        # confirm that the relation databag is empty
        database_relation_databag = self.harness.get_relation_data(
            self.database_relation_id, self.harness.charm.app
        )
        database_relation = self.charm.model.get_relation(DB_RELATION_NAME)
        app_unit = next(iter(database_relation.units))

        self.assertEqual(database_relation_databag, {})
        self.assertEqual(database_relation.data.get(app_unit), {})
        self.assertEqual(database_relation.data.get(self.charm.unit), {})

        _cluster_initialized.return_value = True
        # update the app leader unit data to trigger database_requested event
        self.harness.update_relation_data(
            self.database_relation_id, "app", {"database": "test_db"}
        )

        username = (
            f"relation-{self.database_relation_id}_{self.harness.model.uuid.replace('-', '')}"
        )[:26]
        self.assertEqual(
            database_relation_databag,
            {
                "data": '{"database": "test_db"}',
                "password": "super_secure_password",
                "username": username,
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
