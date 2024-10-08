# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from pathlib import Path
from unittest.mock import patch

import pytest
from charms.mysql.v0.mysql import MySQLCharmBase, MySQLSecretError
from ops.testing import Harness
from parameterized import parameterized


class TestCharmBase(unittest.TestCase):
    @patch.multiple(MySQLCharmBase, __abstractmethods__=set())
    def setUp(self):
        self.harness = Harness(
            MySQLCharmBase,
            meta=Path("metadata.yaml").read_text(),
            actions=Path("actions.yaml").read_text(),
        )
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()
        self.charm = self.harness.charm
        self.peer_relation_id = self.harness.add_relation("database-peers", "mysql")
        self.harness.add_relation_unit(self.peer_relation_id, "mysql/1")

    def test_get_secret_databag(self):
        self.harness.set_leader()

        # Test application scope.
        assert self.charm.get_secret("app", "password") is None
        self.harness.update_relation_data(
            self.peer_relation_id, self.charm.app.name, {"password": "test-password"}
        )
        assert self.charm.get_secret("app", "password") == "test-password"

        # Test unit scope.
        assert self.charm.get_secret("unit", "password") is None
        self.harness.update_relation_data(
            self.peer_relation_id, self.charm.unit.name, {"password": "test-password"}
        )
        assert self.charm.get_secret("unit", "password") == "test-password"

    @pytest.mark.usefixtures("without_juju_secrets")
    @patch("charm.MySQLOperatorCharm._on_leader_elected")
    def test_set_secret_databag(self, _):
        self.harness.set_leader()

        # Test application scope.
        assert "password" not in self.harness.get_relation_data(
            self.peer_relation_id, self.charm.app.name
        )
        self.charm.set_secret("app", "password", "test-password")
        assert (
            self.harness.get_relation_data(self.peer_relation_id, self.charm.app.name)["password"]
            == "test-password"
        )

        # Test unit scope.
        assert "password" not in self.harness.get_relation_data(
            self.peer_relation_id, self.charm.unit.name
        )
        self.charm.set_secret("unit", "password", "test-password")
        assert (
            self.harness.get_relation_data(self.peer_relation_id, self.charm.unit.name)["password"]
            == "test-password"
        )

    @parameterized.expand([("app"), ("unit")])
    @pytest.mark.usefixtures("with_juju_secrets")
    def test_set_secret(self, scope):
        self.harness.set_leader()

        entity = getattr(self.charm, scope)

        assert "password" not in self.harness.get_relation_data(self.peer_relation_id, entity)
        self.charm.set_secret(scope, "password", "test-password")
        assert (
            self.harness.get_relation_data(self.peer_relation_id, entity).get("password") is None
        )
        self.charm.get_secret(scope, "password") == "test-password"

        self.charm.set_secret(scope, "password", None)
        assert "password" not in self.harness.get_relation_data(self.peer_relation_id, entity)

        with self.assertRaises(MySQLSecretError):
            self.charm.set_secret("not-a-scope", "password", "test")  # type: ignore

    @parameterized.expand([("app", True), ("unit", True), ("unit", False)])
    @pytest.mark.usefixtures("with_juju_secrets")
    def test_set_reset_new_secret(self, scope, is_leader):
        """NOTE: currently ops.testing seems to allow for non-leader to set secrets too!"""
        # App has to be leader, unit can be either
        self.harness.set_leader(is_leader)
        # Getting current password
        self.harness.charm.set_secret(scope, "new-secret", "bla")
        assert self.harness.charm.get_secret(scope, "new-secret") == "bla"

        # Reset new secret
        self.harness.charm.set_secret(scope, "new-secret", "blablabla")
        assert self.harness.charm.get_secret(scope, "new-secret") == "blablabla"

        # Set another new secret
        self.harness.charm.set_secret(scope, "new-secret2", "blablabla")
        assert self.harness.charm.get_secret(scope, "new-secret2") == "blablabla"

    @parameterized.expand([("app", True), ("unit", True), ("unit", False)])
    @pytest.mark.usefixtures("with_juju_secrets")
    def test_invalid_secret(self, scope, is_leader):
        # App has to be leader, unit can be either
        self.harness.set_leader(is_leader)

        with self.assertRaises(TypeError):
            self.harness.charm.set_secret(scope, "somekey", 1)  # type: ignore

        self.harness.charm.set_secret(scope, "somekey", "")
        assert self.harness.charm.get_secret(scope, "somekey") is None

    @parameterized.expand([
        ("app", True, "root-password"),
        ("unit", True, "key"),
        ("unit", False, "key"),
    ])
    @pytest.mark.usefixtures("with_juju_secrets")
    def test_migration_from_databag(self, scope, is_leader, password_key):
        """Check if we're moving on to use secrets when live upgrade from databag to Secrets."""
        # App has to be leader, unit can be either
        self.harness.set_leader(is_leader)

        # Getting current password
        entity = getattr(self.charm, scope)
        self.harness.update_relation_data(
            self.peer_relation_id, entity.name, {password_key: "bla"}
        )
        assert self.harness.charm.get_secret(scope, password_key) == "bla"

        # Reset new secret
        self.harness.charm.set_secret(scope, password_key, "blablabla")
        assert self.harness.charm.model.get_secret(label=f"database-peers.mysql.{scope}")
        assert self.harness.charm.get_secret(scope, password_key) == "blablabla"
        assert password_key not in self.harness.get_relation_data(
            self.peer_relation_id, getattr(self.charm, scope).name
        )

    @pytest.mark.usefixtures("without_juju_secrets")
    def test_delete_password(self):
        """NOTE: currently ops.testing seems to allow for non-leader to remove secrets too!"""
        self.harness.set_leader()
        self.harness.update_relation_data(
            self.peer_relation_id, self.charm.app.name, {"replication": "somepw"}
        )
        self.harness.charm.set_secret("app", "replication", "")
        assert self.harness.charm.get_secret("app", "replication") is None

        self.harness.update_relation_data(
            self.peer_relation_id, self.charm.unit.name, {"somekey": "somevalue"}
        )
        self.harness.charm.set_secret("unit", "somekey", "")
        assert self.harness.charm.get_secret("unit", "somekey") is None

        # Ensure deleting non-existent secrets does not raise errors
        self.harness.charm.remove_secret("app", "replication")
        self.harness.charm.remove_secret("unit", "somekey")
        self.harness.charm.remove_secret("app", "non-existing-secret")
        self.harness.charm.remove_secret("unit", "non-existing-secret")

    @pytest.mark.usefixtures("with_juju_secrets")
    def test_delete_existing_password_secrets(self):
        """NOTE: currently ops.testing seems to allow for non-leader to remove secrets too!"""
        self.harness.set_leader()
        self.harness.charm.set_secret("app", "replication", "somepw")
        self.harness.charm.set_secret("app", "replication", "")
        assert self.harness.charm.get_secret("app", "replication") is None

        self.harness.charm.set_secret("unit", "somekey", "somesecret")
        self.harness.charm.set_secret("unit", "somekey", "")
        assert self.harness.charm.get_secret("unit", "somekey") is None

        # Ensure deleting non-existing secrets does not raise errors
        self.harness.charm.remove_secret("app", "root-password")
        self.harness.charm.remove_secret("unit", "root-password")
        self.harness.charm.remove_secret("app", "non-existing-secret")
        self.harness.charm.remove_secret("unit", "non-existing-secret")

    def test_abstract_methods(self):
        """Test abstract methods."""
        with self.assertRaises(NotImplementedError):
            self.harness.charm.get_unit_hostname()

        with self.assertRaises(NotImplementedError):
            self.harness.charm._mysql
