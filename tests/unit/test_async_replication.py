# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import PropertyMock, patch

import pytest
from charms.mysql.v0.async_replication import (
    PRIMARY_RELATION,
    REPLICA_RELATION,
    ClusterSetInstanceState,
    States,
)
from ops import BlockedStatus, MaintenanceStatus, WaitingStatus
from ops.testing import ActionFailed, Harness

from charm import MySQLOperatorCharm
from constants import (
    BACKUPS_PASSWORD_KEY,
    CLUSTER_ADMIN_PASSWORD_KEY,
    MONITORING_PASSWORD_KEY,
    ROOT_PASSWORD_KEY,
    SERVER_CONFIG_PASSWORD_KEY,
)

from .helpers import patch_network_get


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

    @patch("python_hosts.Hosts.write")
    @patch("charm.MySQLOperatorCharm._mysql")
    def test_async_relation_broken_primary(self, _mysql, _write):
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
    @patch("python_hosts.Hosts.write")
    @patch("charm.MySQLOperatorCharm._mysql")
    def test_primary_created(self, _mysql, _write):
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

    @patch_network_get(private_address="1.1.1.1")
    @patch("python_hosts.Hosts.write")
    @patch("ops.framework.EventBase.defer")
    @patch(
        "charms.mysql.v0.async_replication.MySQLAsyncReplicationReplica.returning_cluster",
        new_callable=PropertyMock,
    )
    @patch(
        "charms.mysql.v0.async_replication.MySQLAsyncReplicationReplica.state",
        new_callable=PropertyMock,
    )
    @patch("charm.MySQLOperatorCharm._mysql")
    def test_replica_changed_syncing(self, _mysql, _state, _returning_cluster, _defer, _write):
        """Test replica changed for syncing state."""
        self.harness.set_leader(True)
        self.charm.on.config_changed.emit()

        self.harness.update_relation_data(
            self.peers_relation_id, self.charm.unit.name, {"unit-initialized": "True"}
        )
        async_relation_id = self.harness.add_relation(REPLICA_RELATION, "db1")

        # 1. returning cluster
        _state.return_value = States.SYNCING
        _returning_cluster.return_value = True
        _mysql.get_member_state.return_value = ("online", "primary")

        with self.harness.hooks_disabled():
            self.harness.update_relation_data(
                self.peers_relation_id, self.charm.app.name, {"removed-from-cluster-set": "true"}
            )

        self.harness.update_relation_data(async_relation_id, "db1", {"some": "data"})

        _mysql.create_cluster.assert_called()
        _mysql.create_cluster_set.assert_called()
        _mysql.initialize_juju_units_operations_table.assert_called()
        _mysql.rescan_cluster.assert_called()
        _defer.assert_called()

        # 2. not initialized
        _mysql.reset_mock()
        _defer.reset_mock()
        _returning_cluster.return_value = False
        _mysql.get_cluster_node_count.return_value = 3
        self.harness.update_relation_data(async_relation_id, "db1", {"some": "data1"})
        _defer.assert_called()

        # 3. incompat version
        _defer.reset_mock()
        _mysql.get_cluster_node_count.return_value = 1
        _mysql.get_mysql_version.return_value = "8.0.36"
        self.harness.update_relation_data(async_relation_id, "db1", {"mysql-version": "8.0.35"})

        self.assertTrue(isinstance(self.charm.unit.status, BlockedStatus))
        _defer.assert_not_called()

        # 4. syncing
        secret_dict = {
            SERVER_CONFIG_PASSWORD_KEY: "pass",
            CLUSTER_ADMIN_PASSWORD_KEY: "pass",
            MONITORING_PASSWORD_KEY: "pass",
            BACKUPS_PASSWORD_KEY: "pass",
            ROOT_PASSWORD_KEY: "pass",
        }
        secret = self.harness.charm.app.add_secret(secret_dict, label="async-secret")
        assert secret.id

        original_cluster_name = self.charm.app_peer_data["cluster-name"]
        self.harness.update_relation_data(
            async_relation_id,
            "db1",
            {
                "mysql-version": "8.0.36",
                "secret-id": secret.id,
                "cluster-name": original_cluster_name,
            },
        )

        _mysql.dissolve_cluster.assert_called_once()
        _mysql.update_user_password.assert_called()
        self.assertNotEqual(original_cluster_name, self.charm.app_peer_data["cluster-name"])

    @patch("python_hosts.Hosts.write")
    @patch("charm.MySQLOperatorCharm._on_update_status")
    @patch(
        "charms.mysql.v0.async_replication.MySQLAsyncReplicationReplica.state",
        new_callable=PropertyMock,
    )
    @patch("charm.MySQLOperatorCharm._mysql")
    def test_replica_changed_ready(self, _mysql, _state, _update_status, _write):
        """Test replica changed for ready state."""
        self.harness.set_leader(True)
        self.charm.on.config_changed.emit()
        _state.return_value = States.READY
        _mysql.get_cluster_set_name.return_value = "cluster-set-test"

        async_relation_id = self.harness.add_relation(REPLICA_RELATION, "db1")
        self.harness.update_relation_data(
            async_relation_id,
            "db1",
            {"some": "data2"},
        )

        _update_status.assert_called_once()
        self.assertEqual(self.charm.app_peer_data["cluster-set-domain-name"], "cluster-set-test")
        self.assertEqual(self.charm.app_peer_data["units-added-to-cluster"], "1")

    @patch("python_hosts.Hosts.write")
    @patch("ops.framework.EventBase.defer")
    @patch(
        "charms.mysql.v0.async_replication.MySQLAsyncReplicationReplica.state",
        new_callable=PropertyMock,
    )
    @patch("charm.MySQLOperatorCharm._mysql")
    def test_replica_changed_recovering(self, _mysql, _state, _defer, _write):
        """Test replica changed for ready state."""
        self.harness.set_leader(True)
        self.charm.on.config_changed.emit()
        _state.return_value = States.RECOVERING
        _mysql.get_cluster_node_count.return_value = 2

        with self.harness.hooks_disabled():
            async_relation_id = self.harness.add_relation(REPLICA_RELATION, "db1")
        self.harness.update_relation_data(
            async_relation_id,
            "db1",
            {"some": "data3"},
        )

        self.assertEqual(self.charm.app_peer_data["units-added-to-cluster"], "2")
        _defer.assert_called_once()

    def test_replica_created_non_leader(self):
        """Test replica changed for non-leader unit."""
        self.harness.set_leader(False)
        self.charm.unit_peer_data["member-state"] = "online"
        self.harness.add_relation(REPLICA_RELATION, "db1")

        self.assertEqual(self.charm.unit_peer_data["member-state"], "waiting")

    @patch("charm.MySQLOperatorCharm._mysql")
    def test_replica_changed_non_leader(self, _mysql):
        """Test replica changed for non-leader unit."""
        self.harness.set_leader(False)
        with self.harness.hooks_disabled():
            async_relation_id = self.harness.add_relation(REPLICA_RELATION, "db1")

        _mysql.is_instance_in_cluster.return_value = False

        self.harness.update_relation_data(
            async_relation_id,
            "db1",
            {"replica-state": "initialized"},
        )

        self.assertEqual(self.charm.unit_peer_data["member-state"], "waiting")

    # actions
    @patch("charm.MySQLOperatorCharm._mysql")
    def test_promote_standby_cluster(self, _mysql):
        self.harness.set_leader(True)

        _mysql.is_cluster_replica.return_value = True

        self.harness.run_action(
            "promote-standby-cluster",
            {"cluster-set-name": self.charm.app_peer_data["cluster-set-domain-name"]},
        )

        _mysql.promote_cluster_to_primary.assert_called_with(
            self.charm.app_peer_data["cluster-name"], False
        )

        _mysql.reset_mock()

        self.harness.run_action(
            "promote-standby-cluster",
            {
                "cluster-set-name": self.charm.app_peer_data["cluster-set-domain-name"],
                "force": True,
            },
        )

        _mysql.promote_cluster_to_primary.assert_called_with(
            self.charm.app_peer_data["cluster-name"], True
        )

    @patch("charm.MySQLOperatorCharm._on_update_status")
    @patch("charm.MySQLOperatorCharm._mysql")
    def test_fence_cluster(self, _mysql, _update_status):
        self.harness.set_leader(True)
        # fail on wrong cluster set name
        with self.assertRaises(ActionFailed):
            self.harness.run_action(
                "fence-writes",
                {"cluster-set-name": "incorrect-name"},
            )

        cluster_set_name = self.charm.app_peer_data["cluster-set-domain-name"]
        _mysql.get_member_state.return_value = ("online", "primary")
        _mysql.is_cluster_replica.return_value = True
        # fail on replica
        with self.assertRaises(ActionFailed):
            self.harness.run_action(
                "fence-writes",
                {"cluster-set-name": cluster_set_name},
            )

        del self.async_primary.role
        _mysql.is_cluster_replica.return_value = False
        _mysql.is_cluster_writes_fenced.return_value = True
        # fail on fence already fenced
        with self.assertRaises(ActionFailed):
            self.harness.run_action(
                "fence-writes",
                {"cluster-set-name": cluster_set_name},
            )

        _mysql.is_cluster_writes_fenced.return_value = False

        with self.harness.hooks_disabled():
            self.harness.add_relation(REPLICA_RELATION, "db1")

        self.harness.run_action(
            "fence-writes",
            {"cluster-set-name": cluster_set_name},
        )

        _mysql.fence_writes.assert_called_once()
        _update_status.assert_called_once()

    @patch("charm.MySQLOperatorCharm._on_update_status")
    @patch("charm.MySQLOperatorCharm._mysql")
    def test_unfence_cluster(self, _mysql, _update_status):
        self.harness.set_leader(True)

        _mysql.is_cluster_replica.return_value = False
        _mysql.get_member_state.return_value = ("online", "primary")
        _mysql.is_cluster_writes_fenced.return_value = True

        with self.harness.hooks_disabled():
            self.harness.add_relation(REPLICA_RELATION, "db1")

        self.harness.run_action(
            "unfence-writes",
            {"cluster-set-name": self.charm.app_peer_data["cluster-set-domain-name"]},
        )

        _mysql.unfence_writes.assert_called_once()
        _update_status.assert_called_once()

    @patch("charm.MySQLOperatorCharm._mysql")
    def test_rejoin_cluster_action(self, _mysql):
        with self.assertRaises(ActionFailed):
            self.harness.run_action("rejoin-cluster")

        self.harness.set_leader(True)
        _mysql.is_cluster_in_cluster_set.return_value = False
        with self.assertRaises(ActionFailed):
            self.harness.run_action(
                "rejoin-cluster", {"cluster-name": self.charm.app_peer_data["cluster-name"]}
            )

        _mysql.is_cluster_in_cluster_set.return_value = True
        _mysql.get_replica_cluster_status.return_value = "ok"
        with self.assertRaises(ActionFailed):
            self.harness.run_action(
                "rejoin-cluster", {"cluster-name": self.charm.app_peer_data["cluster-name"]}
            )

        # happy path
        _mysql.is_cluster_in_cluster_set.return_value = True
        _mysql.get_replica_cluster_status.return_value = "invalidated"

        self.harness.run_action(
            "rejoin-cluster", {"cluster-name": self.charm.app_peer_data["cluster-name"]}
        )

        _mysql.rejoin_cluster.assert_called_once_with(self.charm.app_peer_data["cluster-name"])
