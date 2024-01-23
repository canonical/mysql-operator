# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import unittest
from pathlib import Path
from unittest.mock import PropertyMock, patch

import pytest
from charms.mysql.v0.mysql import MySQLCharmBase, MySQLSecretError
from ops import RelationDataTypeError
from ops.testing import Harness
from parameterized import parameterized

from .helpers import patch_network_get


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

    @pytest.fixture
    def use_caplog(self, caplog):
        self._caplog = caplog

    @patch_network_get(private_address="1.1.1.1")
    def test_get_secret(self):
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
    @patch_network_get(private_address="1.1.1.1")
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
    @patch_network_get(private_address="1.1.1.1")
    def test_set_secret(self, scope):
        self.harness.set_leader()

        entity = getattr(self.charm, scope)

        assert "password" not in self.harness.get_relation_data(self.peer_relation_id, entity)
        self.charm.set_secret(scope, "password", "test-password")
        assert (
            self.harness.get_relation_data(self.peer_relation_id, entity)["password"]
            == "test-password"
        )

        self.charm.set_secret(scope, "password", None)
        assert "password" not in self.harness.get_relation_data(self.peer_relation_id, entity)

        with self.assertRaises(MySQLSecretError):
            self.charm.set_secret("not-a-scope", "password", "test")  # type: ignore

    @parameterized.expand([("app", True), ("unit", True), ("unit", False)])
    @patch_network_get(private_address="1.1.1.1")
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
    @patch_network_get(private_address="1.1.1.1")
    @pytest.mark.usefixtures("with_juju_secrets")
    def test_invalid_secret(self, scope, is_leader):
        # App has to be leader, unit can be either
        self.harness.set_leader(is_leader)

        with self.assertRaises(RelationDataTypeError):
            self.harness.charm.set_secret(scope, "somekey", 1)  # type: ignore

        self.harness.charm.set_secret(scope, "somekey", "")
        assert self.harness.charm.get_secret(scope, "somekey") is None

    @parameterized.expand([("app", True), ("unit", True), ("unit", False)])
    @patch_network_get(private_address="1.1.1.1")
    @pytest.mark.usefixtures("with_juju_secrets")
    def test_migration_from_databag(self, scope, is_leader):
        """Check if we're moving on to use secrets when live upgrade from databag to Secrets usage."""
        # App has to be leader, unit can be either
        self.harness.set_leader(is_leader)

        # Getting current password
        entity = getattr(self.charm, scope)
        self.harness.update_relation_data(
            self.peer_relation_id, entity.name, {"operator-password": "bla"}
        )
        assert self.harness.charm.get_secret(scope, "operator-password") == "bla"

        # Reset new secret
        self.harness.charm.set_secret(scope, "operator-password", "blablabla")
        assert self.harness.charm.model.get_secret(label=f"mysql.{scope}")
        assert self.harness.charm.get_secret(scope, "operator-password") == "blablabla"
        assert "operator-password" not in self.harness.get_relation_data(
            self.peer_relation_id, getattr(self.charm, scope).name
        )

    @pytest.mark.usefixtures("without_juju_secrets")
    @pytest.mark.usefixtures("use_caplog")
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

        with self._caplog.at_level(logging.ERROR):
            self.harness.charm.remove_secret("app", "replication")
            assert (
                "Non-existing field 'replication' was attempted to be removed" in self._caplog.text
            )

            self.harness.charm.remove_secret("unit", "somekey")
            assert "Non-existing field 'somekey' was attempted to be removed" in self._caplog.text

            self.harness.charm.remove_secret("app", "non-existing-secret")
            assert (
                "Non-existing field 'non-existing-secret' was attempted to be removed"
                in self._caplog.text
            )

            self.harness.charm.remove_secret("unit", "non-existing-secret")
            assert (
                "Non-existing field 'non-existing-secret' was attempted to be removed"
                in self._caplog.text
            )

    @pytest.mark.usefixtures("with_juju_secrets")
    @pytest.mark.usefixtures("use_caplog")
    def test_delete_existing_password_secrets(self):
        """NOTE: currently ops.testing seems to allow for non-leader to remove secrets too!"""
        self.harness.set_leader()
        self.harness.charm.set_secret("app", "replication", "somepw")
        self.harness.charm.set_secret("app", "replication", "")
        assert self.harness.charm.get_secret("app", "replication") is None

        self.harness.charm.set_secret("unit", "somekey", "somesecret")
        self.harness.charm.set_secret("unit", "somekey", "")
        assert self.harness.charm.get_secret("unit", "somekey") is None

        with self._caplog.at_level(logging.ERROR):
            self.harness.charm.remove_secret("app", "operator-password")
            assert (
                "Non-existing secret {'operator-password'} was attempted to be removed."
                in self._caplog.text
            )

            self.harness.charm.remove_secret("unit", "operator-password")
            assert (
                "Non-existing secret {'operator-password'} was attempted to be removed."
                in self._caplog.text
            )

            self.harness.charm.remove_secret("app", "non-existing-secret")
            assert (
                "Non-existing field 'non-existing-secret' was attempted to be removed"
                in self._caplog.text
            )

            self.harness.charm.remove_secret("unit", "non-existing-secret")
            assert (
                "Non-existing field 'non-existing-secret' was attempted to be removed"
                in self._caplog.text
            )

    def test_abstract_methods(self):
        """Test abstract methods."""
        with self.assertRaises(NotImplementedError):
            self.harness.charm.get_unit_hostname()

        with self.assertRaises(NotImplementedError):
            self.harness.charm._mysql
