# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import patch

import pytest
from ops.testing import Harness

from charm import MySQLOperatorCharm
from constants import LEGACY_MYSQL, PEER

from .helpers import patch_network_get


class TestMariaDBRelation(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(MySQLOperatorCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()
        self.peer_relation_id = self.harness.add_relation("database-peers", "database-peers")
        self.harness.add_relation_unit(self.peer_relation_id, "mysql/1")
        self.charm = self.harness.charm

    @pytest.mark.usefixtures("without_juju_secrets")
    @patch_network_get(private_address="1.1.1.1")
    @patch("mysql_vm_helpers.MySQL.does_mysql_user_exist", return_value=False)
    @patch("mysql_vm_helpers.MySQL.get_cluster_primary_address", return_value="1.1.1.1:3306")
    @patch(
        "relations.mysql.MySQLRelation._get_or_set_password_in_peer_secrets",
        return_value="super_secure_password",
    )
    @patch("mysql_vm_helpers.MySQL.create_application_database_and_scoped_user")
    def test_maria_db_relation_created(
        self,
        _create_application_database_and_scoped_user,
        _get_or_set_password_in_peer_secrets,
        _get_cluster_primary_address,
        _does_mysql_user_exist,
    ):
        # run start-up events to enable usage of the helper class
        self.harness.set_leader(True)
        self.charm.on.config_changed.emit()
        self.charm.unit_peer_data["unit-initialized"] = "True"
        self.harness.update_config(
            {"mysql-interface-user": "mysql", "mysql-interface-database": "default_database"}
        )

        # Relate to emit relation created event
        self.maria_db_relation_id = self.harness.add_relation(LEGACY_MYSQL, "other-app")
        self.harness.add_relation_unit(self.maria_db_relation_id, "other-app/0")

        self.assertEqual(_get_or_set_password_in_peer_secrets.call_count, 1)
        _create_application_database_and_scoped_user.assert_called_once_with(
            "default_database",
            "mysql",
            "super_secure_password",
            "%",
            unit_name="mysql-legacy-relation",
        )

        _get_cluster_primary_address.assert_called_once()
        _does_mysql_user_exist.assert_called_once_with("mysql", "%")

        maria_db_relation = self.charm.model.get_relation(LEGACY_MYSQL)
        peer_relation = self.charm.model.get_relation(PEER)

        # confirm that the relation databag is populated
        self.assertEqual(
            maria_db_relation.data.get(self.charm.unit),
            {
                "database": "default_database",
                "host": "1.1.1.1",
                "password": "super_secure_password",
                "port": "3306",
                "root_password": peer_relation.data.get(self.charm.app)["root-password"],
                "user": "mysql",
            },
        )

    @patch_network_get(private_address="1.1.1.1")
    @patch("mysql_vm_helpers.MySQL.does_mysql_user_exist", return_value=False)
    @patch("mysql_vm_helpers.MySQL.get_cluster_primary_address", return_value="1.1.1.1:3306")
    @patch(
        "relations.mysql.MySQLRelation._get_or_set_password_in_peer_secrets",
        return_value="super_secure_password",
    )
    @patch("mysql_vm_helpers.MySQL.create_application_database_and_scoped_user")
    def test_maria_db_relation_created_with_secrets(
        self,
        _create_application_database_and_scoped_user,
        _get_or_set_password_in_peer_secrets,
        _get_cluster_primary_address,
        _does_mysql_user_exist,
    ):
        # run start-up events to enable usage of the helper class
        self.harness.set_leader(True)
        self.charm.on.config_changed.emit()
        self.charm.unit_peer_data["unit-initialized"] = "True"
        self.harness.update_config(
            {"mysql-interface-user": "mysql", "mysql-interface-database": "default_database"}
        )

        # Relate to emit relation created event
        self.maria_db_relation_id = self.harness.add_relation(LEGACY_MYSQL, "other-app")
        self.harness.add_relation_unit(self.maria_db_relation_id, "other-app/0")

        self.assertEqual(_get_or_set_password_in_peer_secrets.call_count, 1)
        _create_application_database_and_scoped_user.assert_called_once_with(
            "default_database",
            "mysql",
            "super_secure_password",
            "%",
            unit_name="mysql-legacy-relation",
        )

        _get_cluster_primary_address.assert_called_once()
        _does_mysql_user_exist.assert_called_once_with("mysql", "%")

        maria_db_relation = self.charm.model.get_relation(LEGACY_MYSQL)
        root_pw = self.harness.model.get_secret(label="database-peers.mysql.app").get_content()["root-password"]

        # confirm that the relation databag is populated
        self.assertEqual(
            maria_db_relation.data.get(self.charm.unit),
            {
                "database": "default_database",
                "host": "1.1.1.1",
                "password": "super_secure_password",
                "port": "3306",
                "root_password": root_pw,
                "user": "mysql",
            },
        )

    @patch_network_get(private_address="1.1.1.1")
    @patch("mysql_vm_helpers.MySQL.does_mysql_user_exist", return_value=False)
    @patch("mysql_vm_helpers.MySQL.get_cluster_primary_address", return_value="1.1.1.1:3306")
    @patch("mysql_vm_helpers.MySQL.delete_users_for_unit")
    @patch(
        "relations.mysql.MySQLRelation._get_or_set_password_in_peer_secrets",
        return_value="super_secure_password",
    )
    @patch("mysql_vm_helpers.MySQL.create_application_database_and_scoped_user")
    def test_maria_db_relation_departed(
        self,
        _create_application_database_and_scoped_user,
        _get_or_set_password_in_peer_secrets,
        _delete_users_for_unit,
        _get_cluster_primary_address,
        _does_mysql_user_exist,
    ):
        # run start-up events to enable usage of the helper class
        self.harness.set_leader(True)
        self.charm.on.config_changed.emit()
        self.maria_db_relation_id = self.harness.add_relation(LEGACY_MYSQL, "other-app")
        self.harness.add_relation_unit(self.maria_db_relation_id, "other-app/0")

        self.harness.remove_relation(self.maria_db_relation_id)
        _delete_users_for_unit.assert_called_once_with("mysql-legacy-relation")
