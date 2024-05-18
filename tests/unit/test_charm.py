# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import patch

import pytest
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
from constants import CHARMED_MYSQL_SNAP_NAME
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
        self.charm = self.harness.charm
        self.peer_relation_id = self.harness.add_relation("database-peers", "database-peers")
        upgrade_relation_id = self.harness.add_relation("upgrade", "upgrade")
        self.harness.update_relation_data(
            upgrade_relation_id, self.charm.unit.name, {"state": "idle"}
        )
        self.harness.add_relation_unit(self.peer_relation_id, "mysql/1")
        self.db_router_relation_id = self.harness.add_relation("db-router", "app")
        self.harness.add_relation_unit(self.db_router_relation_id, "app/0")
        self.harness.add_relation("restart", "restart")

    @patch_network_get(private_address="1.1.1.1")
    @patch("upgrade.MySQLVMUpgrade.cluster_state", return_value="idle")
    @patch("socket.getfqdn", return_value="test-hostname")
    @patch("socket.gethostbyname", return_value="")
    @patch("subprocess.check_call")
    @patch("mysql_vm_helpers.is_volume_mounted", return_value=True)
    @patch("charm.snap.SnapCache")
    @patch("mysql_vm_helpers.MySQL.install_and_configure_mysql_dependencies")
    def test_on_install(
        self, _install_and_configure_mysql_dependencies, _snap_cache, ___, __, _, _____, ____
    ):
        self.charm.on.install.emit()
        _install_and_configure_mysql_dependencies.assert_called_once()

        mysql_snap = _snap_cache.return_value[CHARMED_MYSQL_SNAP_NAME]
        assert mysql_snap.alias.call_count == 6
        mysql_snap.alias.assert_any_call("mysql")
        mysql_snap.alias.assert_any_call("mysqlrouter")
        mysql_snap.alias.assert_any_call("mysqlsh")
        mysql_snap.alias.assert_any_call("xbcloud")
        mysql_snap.alias.assert_any_call("xbstream")
        mysql_snap.alias.assert_any_call("xtrabackup")

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

    @pytest.mark.usefixtures("without_juju_secrets")
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
            "backups-password",
            "cluster-name",
            "cluster-set-domain-name",
        ]
        self.assertEqual(
            sorted(peer_relation_databag.keys()), sorted(expected_peer_relation_databag_keys)
        )

    def test_on_leader_elected_sets_mysql_passwords_secret(self):
        # ensure that the peer relation databag is empty
        peer_relation_databag = self.harness.get_relation_data(
            self.peer_relation_id, self.harness.charm.app
        )
        self.assertEqual(peer_relation_databag, {})

        # trigger the leader_elected event
        self.harness.set_leader(True)

        expected_peer_relation_databag_keys = [
            "root-password",
            "server-config-password",
            "cluster-admin-password",
            "monitoring-password",
            "backups-password",
        ]

        for key in expected_peer_relation_databag_keys:
            self.assertTrue(self.harness.charm.get_secret("app", key).isalnum())

    @patch_network_get(private_address="1.1.1.1")
    def test_on_leader_elected_sets_config_cluster_name_in_peer_databag(self):
        # ensure that the peer relation databag is empty
        peer_relation_databag = self.harness.get_relation_data(
            self.peer_relation_id, self.harness.charm.app
        )
        self.assertEqual(peer_relation_databag, {})

        # trigger the leader_elected and config_changed events
        self.harness.update_config({"cluster-name": "test-cluster"})
        self.harness.set_leader(True)

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

    @patch("subprocess.check_call")
    @patch("charm.MySQLOperatorCharm.create_cluster")
    @patch("charm.MySQLOperatorCharm.workload_initialise")
    def test_on_start(
        self,
        _workload_initialise,
        _create_cluster,
        _check_call,
    ):
        # execute on_leader_elected and config_changed to populate the peer databag
        self.harness.set_leader(True)
        self.charm.on.config_changed.emit()

        self.charm.on.start.emit()
        _workload_initialise.assert_called_once()
        _create_cluster.assert_called_once()
        _check_call.assert_called_once()

        self.assertTrue(isinstance(self.harness.model.unit.status, ActiveStatus))

        self.harness.set_leader(False)
        self.charm.on.start.emit()
        self.assertTrue(isinstance(self.harness.model.unit.status, WaitingStatus))
        self.assertEqual(self.charm.unit_peer_data["member-role"], "secondary")
        self.assertEqual(self.charm.unit_peer_data["member-state"], "waiting")

    @patch_network_get(private_address="1.1.1.1")
    @patch("mysql_vm_helpers.MySQL.stop_mysqld")
    @patch("subprocess.check_call")
    @patch("mysql_vm_helpers.is_volume_mounted", return_value=True)
    @patch("mysql_vm_helpers.MySQL.configure_mysql_users")
    @patch("mysql_vm_helpers.MySQL.configure_instance")
    @patch("mysql_vm_helpers.MySQL.initialize_juju_units_operations_table")
    @patch("mysql_vm_helpers.MySQL.create_cluster")
    @patch("mysql_vm_helpers.MySQL.reset_root_password_and_start_mysqld")
    @patch("mysql_vm_helpers.MySQL.get_pid_of_port_3306")
    @patch("mysql_vm_helpers.MySQL.write_mysqld_config")
    @patch("mysql_vm_helpers.MySQL.setup_logrotate_and_cron")
    def test_on_start_exceptions(
        self,
        _setup_logrotate_and_cron,
        _write_mysqld_config,
        _get_pid_of_port_3306,
        _reset_root_password_and_start_mysqld,
        _create_cluster,
        _initialize_juju_units_operations_table,
        _configure_instance,
        _configure_mysql_users,
        _is_volume_mounted,
        _check_call,
        _stop_mysqld,
    ):
        patch("tenacity.BaseRetrying.wait", side_effect=lambda *args, **kwargs: 0)

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

        # test mysqld not restarting after configure instance
        _get_pid_of_port_3306.side_effect = ["1234", "1234"]

        self.charm.on.start.emit()
        self.assertTrue(isinstance(self.harness.model.unit.status, BlockedStatus))

        _get_pid_of_port_3306.reset_mock()

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
        _write_mysqld_config.side_effect = MySQLCreateCustomMySQLDConfigError

        self.charm.on.start.emit()
        self.assertTrue(isinstance(self.harness.model.unit.status, BlockedStatus))

    @patch_network_get(private_address="1.1.1.1")
    @patch("charms.mysql.v0.mysql.MySQLCharmBase.active_status_message", return_value="")
    @patch("mysql_vm_helpers.MySQL.get_cluster_node_count", return_value=1)
    @patch("mysql_vm_helpers.MySQL.get_member_state")
    @patch("mysql_vm_helpers.MySQL.get_cluster_primary_address")
    @patch("charm.is_volume_mounted", return_value=True)
    @patch("mysql_vm_helpers.MySQL.reboot_from_complete_outage")
    @patch("charm.snap_service_operation")
    @patch("python_hosts.Hosts.write")
    def test_on_update(
        self,
        _,
        _snap_service_operation,
        _reboot_from_complete_outage,
        _is_volume_mounted,
        _get_cluster_primary_address,
        _get_member_state,
        _get_cluster_node_count,
        _active_status_message,
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
        _reboot_from_complete_outage.assert_not_called()
        _snap_service_operation.assert_not_called()
        _is_volume_mounted.assert_called_once()
        _get_cluster_node_count.assert_called_once()
        _get_cluster_primary_address.assert_called_once()

        self.assertTrue(isinstance(self.harness.model.unit.status, ActiveStatus))

        # test instance state = offline
        _get_member_state.reset_mock()
        _get_cluster_primary_address.reset_mock()

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
        _reboot_from_complete_outage.assert_called_once()
        _snap_service_operation.assert_not_called()
        _get_cluster_primary_address.assert_called_once()

        self.assertTrue(isinstance(self.harness.model.unit.status, MaintenanceStatus))
        # test instance state = unreachable
        _get_member_state.reset_mock()
        _get_cluster_primary_address.reset_mock()

        _reboot_from_complete_outage.reset_mock()
        _snap_service_operation.return_value = False
        _get_member_state.return_value = ("unreachable", "primary")

        self.charm.on.update_status.emit()
        _get_member_state.assert_called_once()
        _reboot_from_complete_outage.assert_not_called()
        _snap_service_operation.assert_called_once()
        _get_cluster_primary_address.assert_called_once()

        self.assertTrue(isinstance(self.harness.model.unit.status, BlockedStatus))
