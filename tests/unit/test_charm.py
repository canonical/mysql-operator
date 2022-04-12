# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import patch

from ops.model import ActiveStatus, BlockedStatus, WaitingStatus
from ops.testing import Harness

from charm import MySQLOperatorCharm
from tests.unit.helpers import patch_network_get


class TestCharm(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(MySQLOperatorCharm)
        self.peer_relation_id = self.harness.add_relation("mysql-replicas", "mysql-replicas")
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()
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

    @patch_network_get(private_address="1.1.1.1")
    @patch("mysqlsh_helpers.MySQL.configure_mysql_users")
    @patch("mysqlsh_helpers.MySQL.configure_instance")
    def test_on_start_sets_mysql_config_in_peer_databag(
        self, _configure_instance, _configure_mysql_users
    ):
        self.harness.add_relation_unit(self.peer_relation_id, "mysql/1")

        peer_relation_databag = self.harness.get_relation_data(
            self.peer_relation_id, self.harness.charm.app
        )
        self.assertEqual(peer_relation_databag, {})

        self.harness.set_leader(True)
        self.charm.on.start.emit()

        peer_relation_databag = self.harness.get_relation_data(
            self.peer_relation_id, self.harness.charm.app
        )
        expected_peer_relation_databag_keys = [
            "cluster_name",
            "root_password",
            "server_config_password",
            "cluster_admin_password",
        ]
        self.assertEqual(
            sorted(peer_relation_databag.keys()), sorted(expected_peer_relation_databag_keys)
        )

        self.assertTrue(isinstance(self.harness.model.unit.status, ActiveStatus))
