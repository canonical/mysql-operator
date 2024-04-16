# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import patch

import pytest
from charms.mysql.v0.async_replication import (
    PRIMARY_RELATION,
    REPLICA_RELATION,
    ClusterSetInstanceState,
    States,
)
from ops import MaintenanceStatus, WaitingStatus
from ops.testing import Harness

from charm import MySQLOperatorCharm


class TestAsyncRelation(unittest.TestCase):
    def setUp(self) -> None:
        self.harness = Harness(MySQLOperatorCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()
        self.peers_relation_id = self.harness.add_relation("database-peers", "db1")
        self.charm = self.harness.charm
        self.async_primary = self.charm.async_primary
        self.async_replica = self.charm.async_replica

    @patch("charm.MySQLOperatorCharm._mysql")
    def test_role(self, _mysql):
        _mysql.is_cluster_replica.return_value = True
        _mysql.get_member_state.return_value = (None, "primary")
        self.async_primary_relation_id = self.harness.add_relation(PRIMARY_RELATION, "db2")

        self.assertEqual(
            self.async_primary.role, ClusterSetInstanceState("replica", "primary", "primary")
        )
        # reset cached value
        del self.async_primary.role
        _mysql.is_cluster_replica.return_value = False
        _mysql.get_member_state.return_value = (None, "secondary")
        self.assertEqual(
            self.async_primary.role, ClusterSetInstanceState("primary", "secondary", "primary")
        )
        del self.async_primary.role

    @patch("charm.MySQLOperatorCharm._mysql")
    def test_async_relation_broken_primary(self, _mysql):
        self.harness.set_leader(True)
        self.charm.on.config_changed.emit()
        self.async_primary_relation_id = self.harness.add_relation(PRIMARY_RELATION, "db2")
        _mysql.is_cluster_replica.return_value = False
        _mysql.get_member_state.return_value = (None, "primary")
        _mysql.is_cluster_in_cluster_set.return_value = True
        _mysql.get_replica_cluster_status.return_value = "ok"

        self.harness.update_relation_data(
            self.async_primary_relation_id,
            "db2",
            {"cluster-name": self.charm.app_peer_data["cluster-name"]},
        )

        self.harness.remove_relation(self.async_primary_relation_id)

        _mysql.remove_replica_cluster.assert_called_with(
            self.charm.app_peer_data["cluster-name"], force=False
        )

    @patch("charm.MySQLOperatorCharm._mysql")
    def test_async_relation_broken_replica(self, _mysql):
        self.harness.set_leader(True)
        self.charm.on.config_changed.emit()
        async_primary_relation_id = self.harness.add_relation(PRIMARY_RELATION, "db2")
        _mysql.is_cluster_replica.return_value = True
        _mysql.get_member_state.return_value = (None, "primary")
        _mysql.is_instance_in_cluster.return_value = False
        _mysql.get_replica_cluster_status.return_value = "ok"

        self.harness.remove_relation(async_primary_relation_id)

        self.assertEqual(self.charm.app_peer_data["removed-from-cluster-set"], "true")
        self.assertNotIn("unit-initialized", self.charm.unit_peer_data)
        self.assertNotIn("units-added-to-cluster", self.charm.app_peer_data)

    @patch("charm.MySQLOperatorCharm._mysql")
    def test_get_state(self, _mysql):
        async_primary_relation_id = self.harness.add_relation(PRIMARY_RELATION, "db2")
        relation = self.harness.model.get_relation(PRIMARY_RELATION, async_primary_relation_id)
        assert relation
        self.assertEqual(self.async_primary.get_state(relation), States.UNINITIALIZED)

        self.harness.update_relation_data(
            async_primary_relation_id, self.charm.app.name, {"is-replica": "true"}
        )
        self.assertEqual(self.async_primary.get_state(relation), States.FAILED)

        self.harness.update_relation_data(
            async_primary_relation_id,
            self.charm.app.name,
            {"is-replica": "", "secret-id": "secret"},
        )
        self.assertEqual(self.async_primary.get_state(relation), States.SYNCING)

        self.harness.update_relation_data(
            async_primary_relation_id,
            "db2",
            {"endpoint": "db2-endpoint", "cluster-name": "other-cluster"},
        )
        _mysql.get_replica_cluster_status.return_value = "ok"
        self.assertEqual(self.async_primary.get_state(relation), States.READY)

        _mysql.get_replica_cluster_status.return_value = "unknown"
        self.assertEqual(self.async_primary.get_state(relation), States.INITIALIZING)

        _mysql.get_replica_cluster_status.return_value = "recovering"
        self.assertEqual(self.async_primary.get_state(relation), States.RECOVERING)

    @pytest.mark.usefixtures("with_juju_secrets")
    @patch("charm.MySQLOperatorCharm._mysql")
    def test_primary_created(self, _mysql):
        self.harness.set_leader(True)
        self.charm.on.config_changed.emit()

        _mysql.is_cluster_replica.return_value = False
        _mysql.get_mysql_version.return_value = "8.0.36-0ubuntu0.22.04.1"

        self.harness.update_relation_data(
            self.peers_relation_id, self.charm.unit.name, {"unit-initialized": "True"}
        )

        async_primary_relation_id = self.harness.add_relation(
            PRIMARY_RELATION, "db2", app_data={"is-replica": "true"}
        )

        relation_data = self.harness.get_relation_data(
            async_primary_relation_id, self.charm.app.name
        )
        self.assertIn("secret-id", relation_data)
        self.assertEqual(relation_data["mysql-version"], "8.0.36-0ubuntu0.22.04.1")

    @patch("charms.mysql.v0.async_replication.MySQLAsyncReplicationPrimary.get_state")
    @patch("charm.MySQLOperatorCharm._mysql")
    def test_primary_relation_changed(self, _mysql, _get_state):
        self.harness.set_leader(True)
        async_primary_relation_id = self.harness.add_relation(PRIMARY_RELATION, "db2")

        _get_state.return_value = States.INITIALIZING

        # test with donor
        _mysql.get_cluster_endpoints.return_value = (None, "db2-ro-endpoint", None)
        self.harness.update_relation_data(
            async_primary_relation_id,
            "db2",
            {
                "cluster-name": "cuzco",
                "endpoint": "db2-endpoint",
                "node-label": "db2-0",
            },
        )
        _mysql.create_replica_cluster.assert_called_with(
            "db2-endpoint", "cuzco", instance_label="db2-0", donor="db2-ro-endpoint"
        )

        relation_data = self.harness.get_relation_data(
            async_primary_relation_id, self.charm.app.name
        )
        self.assertEqual(relation_data["replica-state"], "initialized")

        # without donor
        _mysql.reset_mock()
        _mysql.get_cluster_endpoints.return_value = (None, None, None)
        self.harness.update_relation_data(
            async_primary_relation_id,
            "db2",
            {
                "cluster-name": "other-name",
            },
        )
        _mysql.create_replica_cluster.assert_called_with(
            "db2-endpoint", "other-name", instance_label="db2-0"
        )

        # recovering state
        _get_state.return_value = States.RECOVERING
        self.harness.update_relation_data(
            async_primary_relation_id,
            "db2",
            {
                "cluster-name": "yet-another-name",
            },
        )

        self.assertTrue(isinstance(self.charm.unit.status, MaintenanceStatus))

    @patch("charm.MySQLOperatorCharm._mysql")
    def test_state(self, _mysql):
        """Test async replica state property."""
        self.assertIsNone(self.async_replica.state)

        async_relation_id = self.harness.add_relation(REPLICA_RELATION, "db1")

        # initial state
        self.assertEqual(self.async_replica.state, States.INITIALIZING)

        # syncing state
        self.harness.update_relation_data(async_relation_id, "db1", {"secret-id": "secret"})
        self.assertEqual(self.async_replica.state, States.SYNCING)

        with self.harness.hooks_disabled():
            self.harness.update_relation_data(
                async_relation_id, "db1", {"replica-state": "initialized"}
            )
            self.harness.update_relation_data(
                async_relation_id, self.charm.app.name, {"endpoint": "endpoint"}
            )

        # recovering
        _mysql.get_cluster_node_count.return_value = 2
        self.assertEqual(self.async_replica.state, States.RECOVERING)

        # ready
        _mysql.get_cluster_node_count.return_value = 1
        self.assertEqual(self.async_replica.state, States.READY)

        # failed
        self.harness.update_relation_data(
            async_relation_id, self.charm.app.name, {"user-data-found": "true"}
        )
        self.assertEqual(self.async_replica.state, States.FAILED)

    @patch("charm.MySQLOperatorCharm._mysql")
    def test_replica_created(self, _mysql):
        """Test replica creation."""
        self.harness.set_leader(True)
        self.charm.on.config_changed.emit()

        self.harness.update_relation_data(
            self.peers_relation_id, self.charm.unit.name, {"unit-initialized": "True"}
        )

        _mysql.get_non_system_databases.return_value = set()

        self.harness.add_relation(REPLICA_RELATION, "db1")

        self.assertTrue(isinstance(self.charm.unit.status, WaitingStatus))

    @patch("charm.MySQLOperatorCharm._mysql")
    def test_replica_created_user_data(self, _mysql):
        """Test replica creation."""
        self.harness.set_leader(True)
        self.charm.on.config_changed.emit()

        self.harness.update_relation_data(
            self.peers_relation_id, self.charm.unit.name, {"unit-initialized": "True"}
        )

        _mysql.get_non_system_databases.return_value = set("a-database")

        async_relation_id = self.harness.add_relation(REPLICA_RELATION, "db1")

        self.assertIn(
            "user-data-found",
            self.harness.get_relation_data(async_relation_id, self.charm.app.name),
        )

    @patch("charms.mysql.v0.async_replication.MySQLAsyncReplicationReplica.returning_cluster")
    @patch("charms.mysql.v0.async_replication.MySQLAsyncReplicationReplica.state")
    @patch("charm.MySQLOperatorCharm._mysql")
    def test_replica_changed(self, _mysql, _state, _returning_cluster):
        """Test replica changed."""
        self.harness.set_leader(True)
        self.charm.on.config_changed.emit()

        self.harness.update_relation_data(
            self.peers_relation_id, self.charm.unit.name, {"unit-initialized": "True"}
        )
        self.harness.add_relation(REPLICA_RELATION, "db1")

        # returning cluster
        _state.return_value = States.SYNCING
        _returning_cluster.return_value = True
        self.harness.update_relation_data(
            self.peers_relation_id, self.charm.app.name, {"removed-from-cluster-set": "true"}
        )

        # _mysql.create_cluster.assert_called()
        # _mysql.create_cluster_set.assert_called()
        # _mysql.initialize_juju_units_operations_table.assert_called()
