# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import patch

from ops.testing import Harness
import pytest

from charm import MySQLOperatorCharm
from charms.mysql.v0.async_replication import (
    PRIMARY_RELATION,
    REPLICA_RELATION,
    ClusterSetInstanceState,
    States,
)


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
        self.async_primary_relation_id = self.harness.add_relation(PRIMARY_RELATION, "db2")
        _mysql.is_cluster_replica.return_value = True
        _mysql.get_member_state.return_value = (None, "primary")
        _mysql.is_instance_in_cluster.return_value = False
        _mysql.get_replica_cluster_status.return_value = "ok"

        self.harness.remove_relation(self.async_primary_relation_id)

        self.assertEqual(self.charm.app_peer_data["removed-from-cluster-set"], "true")
        self.assertNotIn("unit-initialized", self.charm.unit_peer_data)
        self.assertNotIn("units-added-to-cluster", self.charm.app_peer_data)

    @patch("charm.MySQLOperatorCharm._mysql")
    def test_get_state(self, _mysql):
        self.async_primary_relation_id = self.harness.add_relation(PRIMARY_RELATION, "db2")
        relation = self.harness.model.get_relation(
            PRIMARY_RELATION, self.async_primary_relation_id
        )
        assert relation
        self.assertEqual(self.async_primary.get_state(relation), States.UNINITIALIZED)

        self.harness.update_relation_data(
            self.async_primary_relation_id, self.charm.app.name, {"is-replica": "true"}
        )
        self.assertEqual(self.async_primary.get_state(relation), States.FAILED)

        self.harness.update_relation_data(
            self.async_primary_relation_id,
            self.charm.app.name,
            {"is-replica": "", "secret-id": "secret"},
        )
        self.assertEqual(self.async_primary.get_state(relation), States.SYNCING)

        self.harness.update_relation_data(
            self.async_primary_relation_id,
            "db2",
            {"endpoint": "db2-endpoint", "cluster-name": "other-cluster"},
        )
        _mysql.get_replica_cluster_status.return_value = "ok"
        self.assertEqual(self.async_primary.get_state(relation), States.READY)

        _mysql.get_replica_cluster_status.return_value = "unknown"
        self.assertEqual(self.async_primary.get_state(relation), States.INITIALIZING)

        _mysql.get_replica_cluster_status.return_value = "recovering"
        self.assertEqual(self.async_primary.get_state(relation), States.RECOVERING)

    
