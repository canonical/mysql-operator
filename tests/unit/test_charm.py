# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import patch

from charms.mysql.v0.mysql import (
    MySQLConfigureInstanceError,
    MySQLConfigureMySQLUsersError,
    MySQLCreateClusterError,
    MySQLInitializeJujuOperationsTableError,
)
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus
from ops.testing import Harness
from tenacity import Retrying, stop_after_attempt

from charm import MySQLOperatorCharm
from mysql_vm_helpers import (
    MySQLCreateCustomMySQLDConfigError,
    MySQLResetRootPasswordAndStartMySQLDError,
)

from .helpers import patch_network_get


class TestCharm(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(MySQLOperatorCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()
        self.peer_relation_id = self.harness.add_relation("database-peers", "database-peers")
        self.harness.add_relation_unit(self.peer_relation_id, "mysql/1")
        self.db_router_relation_id = self.harness.add_relation("db-router", "app")
        self.harness.add_relation_unit(self.db_router_relation_id, "app/0")
        self.charm = self.harness.charm

    @patch_network_get(private_address="1.1.1.1")
    @patch("socket.getfqdn", return_value="test-hostname")
    @patch("socket.gethostbyname", return_value="")
    @patch("subprocess.check_call")
    @patch("mysql_vm_helpers.is_volume_mounted", return_value=True)
    @patch("mysql_vm_helpers.MySQL.install_and_configure_mysql_dependencies")
    def test_on_install(self, _install_and_configure_mysql_dependencies, ____, ___, __, _):
        self.charm.on.install.emit()
        _install_and_configure_mysql_dependencies.assert_called_once()

        self.assertTrue(isinstance(self.harness.model.unit.status, WaitingStatus))

    @patch("charm.Retrying", return_value=Retrying(stop=stop_after_attempt(1)))
    @patch("subprocess.check_call")
    @patch("mysql_vm_helpers.is_volume_mounted", return_value=True)
    @patch(
        "mysql_vm_helpers.MySQL.install_and_configure_mysql_dependencies", side_effect=Exception()
    )
    def test_on_install_exception(
        self,
        _install_and_configure_mysql_dependencies,
        _is_volume_mounted,
        _check_call,
        _retrying,
    ):
        self.charm.on.install.emit()

        self.assertTrue(isinstance(self.harness.model.unit.status, BlockedStatus))

    def test_on_leader_elected_sets_mysql_passwords_in_peer_databag(self):
        # ensure that the peer relation databag is empty
        peer_relation_databag = self.harness.get_relation_data(
            self.peer_relation_id, self.harness.charm.app
        )
        self.assertEqual(peer_relation_databag, {})

        # trigger the leader_elected event
        self.harness.set_leader(True)

        # ensure passwords set in the peer relation databag
        peer_relation_databag = self.harness.get_relation_data(
            self.peer_relation_id, self.harness.charm.app
        )
        expected_peer_relation_databag_keys = [
            "root-password",
            "server-config-password",
            "cluster-admin-password",
            "monitoring-password",
        ]
        self.assertEqual(
            sorted(peer_relation_databag.keys()), sorted(expected_peer_relation_databag_keys)
        )

    @patch_network_get(private_address="1.1.1.1")
    def test_on_config_changed_sets_config_cluster_name_in_peer_databag(self):
        # ensure that the peer relation databag is empty
        peer_relation_databag = self.harness.get_relation_data(
            self.peer_relation_id, self.harness.charm.app
        )
        self.assertEqual(peer_relation_databag, {})

        # trigger the leader_elected and config_changed events
        self.harness.set_leader(True)
        self.harness.update_config({"cluster-name": "test-cluster"})

        # ensure that the peer relation has 'cluster_name' set to the config value
        peer_relation_databag = self.harness.get_relation_data(
            self.peer_relation_id, self.harness.charm.app
        )

        self.assertEqual(peer_relation_databag["cluster-name"], "test-cluster")

    @patch_network_get(private_address="1.1.1.1")
    def test_on_config_changed_sets_random_cluster_name_in_peer_databag(self):
        # ensure that the peer relation databag is empty
        peer_relation_databag = self.harness.get_relation_data(
            self.peer_relation_id, self.harness.charm.app
        )
        self.assertEqual(peer_relation_databag, {})

        # trigger the leader_elected and config_changed events
        self.harness.set_leader(True)
        self.charm.on.config_changed.emit()

        # ensure that the peer relation has a randomly generated 'cluster_name'
        peer_relation_databag = self.harness.get_relation_data(
            self.peer_relation_id, self.harness.charm.app
        )

        self.assertIsNotNone(peer_relation_databag["cluster-name"])

    @patch_network_get(private_address="1.1.1.1")
    @patch("subprocess.check_call")
    @patch("mysql_vm_helpers.is_volume_mounted", return_value=True)
    @patch("mysql_vm_helpers.MySQL.get_mysql_version", return_value="8.0.0")
    @patch("mysql_vm_helpers.MySQL.connect_mysql_exporter")
    @patch("mysql_vm_helpers.MySQL.wait_until_mysql_connection")
    @patch("mysql_vm_helpers.MySQL.configure_mysql_users")
    @patch("mysql_vm_helpers.MySQL.configure_instance")
    @patch("mysql_vm_helpers.MySQL.initialize_juju_units_operations_table")
    @patch("mysql_vm_helpers.MySQL.create_cluster")
    @patch("mysql_vm_helpers.MySQL.reset_root_password_and_start_mysqld")
    @patch("mysql_vm_helpers.MySQL.create_custom_mysqld_config")
    def test_on_start(
        self,
        _create_custom_mysqld_config,
        _reset_root_password_and_start_mysqld,
        _create_cluster,
        _initialize_juju_units_operations_table,
        _configure_instance,
        _configure_mysql_users,
        _wait_until_mysql_connection,
        _connect_mysql_exporter,
        _get_mysql_version,
        _is_volume_mounted,
        _check_call,
    ):
        # execute on_leader_elected and config_changed to populate the peer databag
        self.harness.set_leader(True)
        self.charm.on.config_changed.emit()

        self.charm.on.start.emit()

        self.assertTrue(isinstance(self.harness.model.unit.status, ActiveStatus))

    @patch_network_get(private_address="1.1.1.1")
    @patch("subprocess.check_call")
    @patch("mysql_vm_helpers.is_volume_mounted", return_value=True)
    @patch("mysql_vm_helpers.MySQL.configure_mysql_users")
    @patch("mysql_vm_helpers.MySQL.configure_instance")
    @patch("mysql_vm_helpers.MySQL.initialize_juju_units_operations_table")
    @patch("mysql_vm_helpers.MySQL.create_cluster")
    @patch("mysql_vm_helpers.MySQL.reset_root_password_and_start_mysqld")
    @patch("mysql_vm_helpers.MySQL.create_custom_mysqld_config")
    def test_on_start_exceptions(
        self,
        _create_custom_mysqld_config,
        _reset_root_password_and_start_mysqld,
        _create_cluster,
        _initialize_juju_units_operations_table,
        _configure_instance,
        _configure_mysql_users,
        _is_volume_mounted,
        _check_call,
    ):
        # execute on_leader_elected and config_changed to populate the peer databag
        self.harness.set_leader(True)
        self.charm.on.config_changed.emit()

        # test an exception while configuring mysql users
        _configure_mysql_users.side_effect = MySQLConfigureMySQLUsersError

        self.charm.on.start.emit()
        self.assertTrue(isinstance(self.harness.model.unit.status, BlockedStatus))

        _configure_mysql_users.reset_mock()

        # test an exception while configuring the instance
        _configure_instance.side_effect = MySQLConfigureInstanceError

        self.charm.on.start.emit()
        self.assertTrue(isinstance(self.harness.model.unit.status, BlockedStatus))

        _configure_instance.reset_mock()

        # test an exception initializing the mysql.juju_units_operations table
        _initialize_juju_units_operations_table.side_effect = (
            MySQLInitializeJujuOperationsTableError
        )

        self.charm.on.start.emit()
        self.assertTrue(isinstance(self.harness.model.unit.status, BlockedStatus))

        _initialize_juju_units_operations_table.reset_mock()

        # test an exception with creating a cluster
        _create_cluster.side_effect = MySQLCreateClusterError

        self.charm.on.start.emit()
        self.assertTrue(isinstance(self.harness.model.unit.status, BlockedStatus))

        # test an exception with resetting the root password and starting mysqld
        _reset_root_password_and_start_mysqld.side_effect = (
            MySQLResetRootPasswordAndStartMySQLDError
        )

        self.charm.on.start.emit()
        self.assertTrue(isinstance(self.harness.model.unit.status, BlockedStatus))

        # test an exception creating a custom mysqld config
        _create_custom_mysqld_config.side_effect = MySQLCreateCustomMySQLDConfigError

        self.charm.on.start.emit()
        self.assertTrue(isinstance(self.harness.model.unit.status, BlockedStatus))

    @patch_network_get(private_address="1.1.1.1")
    @patch("charm.MySQLOperatorCharm._on_leader_elected")
    def test_get_secret(self, _):
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

    @patch_network_get(private_address="1.1.1.1")
    @patch("charm.MySQLOperatorCharm._on_leader_elected")
    def test_set_secret(self, _):
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

    @patch_network_get(private_address="1.1.1.1")
    @patch("mysql_vm_helpers.MySQL.get_cluster_node_count", return_value=1)
    @patch("mysql_vm_helpers.MySQL.get_member_state")
    @patch("mysql_vm_helpers.MySQL.get_cluster_primary_address")
    @patch("mysql_vm_helpers.MySQL.rescan_cluster")
    @patch("charm.is_volume_mounted", return_value=True)
    @patch("mysql_vm_helpers.MySQL.reboot_from_complete_outage")
    @patch("charm.snap_service_operation")
    @patch("charm.MySQLOperatorCharm._workload_reset")
    def test_on_update(
        self,
        _workload_reset,
        _snap_service_operation,
        __reboot_from_complete_outage,
        _is_volume_mounted,
        _rescan_cluster,
        _get_cluster_primary_address,
        _get_member_state,
        _get_cluster_node_count,
    ):
        self.harness.remove_relation_unit(self.peer_relation_id, "mysql/1")
        self.harness.set_leader()
        self.charm.on.config_changed.emit()
        self.harness.update_relation_data(
            self.peer_relation_id, self.charm.app.name, {"units-added-to-cluster": "1"}
        )
        self.harness.update_relation_data(
            self.peer_relation_id,
            self.charm.unit.name,
            {
                "member-role": "primary",
                "member-state": "online",
                "unit-initialized": "true",
            },
        )
        _get_member_state.return_value = ("online", "primary")

        self.charm.on.update_status.emit()
        _get_member_state.assert_called_once()
        __reboot_from_complete_outage.assert_not_called()
        _snap_service_operation.assert_not_called()
        _workload_reset.assert_not_called()
        _is_volume_mounted.assert_called_once()
        _get_cluster_node_count.assert_called_once()
        _get_cluster_primary_address.assert_called_once()
        _rescan_cluster.assert_called_once()

        self.assertTrue(isinstance(self.harness.model.unit.status, ActiveStatus))

        # test instance state = offline
        _get_member_state.reset_mock()
        _get_cluster_primary_address.reset_mock()
        _rescan_cluster.reset_mock()

        _get_member_state.return_value = ("offline", "primary")
        self.harness.update_relation_data(
            self.peer_relation_id,
            self.charm.unit.name,
            {
                "member-state": "offline",
            },
        )

        self.charm.on.update_status.emit()
        _get_member_state.assert_called_once()
        __reboot_from_complete_outage.assert_called_once()
        _snap_service_operation.assert_not_called()
        _workload_reset.assert_not_called()
        _get_cluster_primary_address.assert_called_once()
        _rescan_cluster.assert_called_once()

        self.assertTrue(isinstance(self.harness.model.unit.status, MaintenanceStatus))
        # test instance state = unreachable
        _get_member_state.reset_mock()
        _get_cluster_primary_address.reset_mock()
        _rescan_cluster.reset_mock()

        __reboot_from_complete_outage.reset_mock()
        _snap_service_operation.return_value = False
        _workload_reset.return_value = ActiveStatus()
        _get_member_state.return_value = ("unreachable", "primary")

        self.charm.on.update_status.emit()
        _get_member_state.assert_called_once()
        __reboot_from_complete_outage.assert_not_called()
        _snap_service_operation.assert_called_once()
        _workload_reset.assert_called_once()
        _get_cluster_primary_address.assert_called_once()
        _rescan_cluster.assert_called_once()

        self.assertTrue(isinstance(self.harness.model.unit.status, ActiveStatus))
