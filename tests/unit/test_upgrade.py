# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import call, patch

from charms.data_platform_libs.v0.upgrade import ClusterNotReadyError, VersionError
from charms.mysql.v0.mysql import (
    MySQLServerNotUpgradableError,
    MySQLSetClusterPrimaryError,
    MySQLSetVariableError,
    MySQLStartMySQLDError,
    MySQLStopMySQLDError,
)
from ops.testing import Harness
from tenacity import RetryError

from charm import MySQLOperatorCharm

MOCK_STATUS_ONLINE = {
    "defaultreplicaset": {
        "topology": {
            "0": {"status": "online"},
            "1": {"status": "online"},
        },
    }
}
MOCK_STATUS_OFFLINE = {
    "defaultreplicaset": {
        "topology": {
            "0": {"status": "online"},
            "1": {"status": "online", "instanceerrors": ["some error"]},
        },
    }
}


class TestUpgrade(unittest.TestCase):
    """Test the upgrade class."""

    def setUp(self):
        """Set up the test."""
        self.harness = Harness(MySQLOperatorCharm)
        self.harness.begin()
        self.upgrade_relation_id = self.harness.add_relation("upgrade", "mysql")
        self.peer_relation_id = self.harness.add_relation("database-peers", "mysql")
        for rel_id in (self.upgrade_relation_id, self.peer_relation_id):
            self.harness.add_relation_unit(rel_id, "mysql/1")
        self.harness.update_relation_data(self.upgrade_relation_id, "mysql/1", {"state": "idle"})
        self.harness.update_relation_data(
            self.peer_relation_id,
            "mysql",
            {"cluster-name": "test_cluster", "cluster-set-domain-name": "test_cluster_set"},
        )
        self.charm = self.harness.charm

    def test_build_upgrade_stack(self):
        """Test building the upgrade stack."""
        self.harness.add_relation_unit(self.upgrade_relation_id, "mysql/2")
        us = self.charm.upgrade.build_upgrade_stack()
        self.assertTrue(len(us) == 3)
        self.assertEqual(us, [0, 1, 2])

    @patch("charms.rolling_ops.v0.rollingops.RollingOpsManager._on_process_locks")
    @patch("charm.MySQLOperatorCharm.get_unit_address", return_value="10.0.1.1")
    @patch("upgrade.MySQLVMUpgrade._pre_upgrade_prepare")
    @patch("mysql_vm_helpers.MySQL.get_cluster_status", return_value=MOCK_STATUS_ONLINE)
    def test_pre_upgrade_check(
        self, mock_get_cluster_status, mock_pre_upgrade_prepare, mock_get_unit_address, _
    ):
        """Test the pre upgrade check."""
        self.harness.set_leader(True)
        self.charm.on.config_changed.emit()

        self.charm.upgrade.pre_upgrade_check()
        mock_pre_upgrade_prepare.assert_called_once()
        mock_get_cluster_status.assert_called_once()

        self.assertEqual(
            self.harness.get_relation_data(self.upgrade_relation_id, "mysql/0")["state"],
            "idle",
        )

        mock_get_cluster_status.return_value = MOCK_STATUS_OFFLINE

        with self.assertRaises(ClusterNotReadyError):
            self.charm.upgrade.pre_upgrade_check()

        mock_get_cluster_status.return_value = MOCK_STATUS_ONLINE

        mock_pre_upgrade_prepare.side_effect = MySQLSetClusterPrimaryError
        with self.assertRaises(ClusterNotReadyError):
            self.charm.upgrade.pre_upgrade_check()

        mock_pre_upgrade_prepare.side_effect = MySQLSetVariableError
        with self.assertRaises(ClusterNotReadyError):
            self.charm.upgrade.pre_upgrade_check()

    @patch("upgrade.logger.critical")
    def test_log_rollback(self, mock_logging):
        """Test roolback logging."""
        self.charm.upgrade.log_rollback_instructions()
        calls = [
            call(
                "Upgrade failed, follow the instructions below to rollback:\n"
                "    1. Re-run `pre-upgrade-check` action on the leader unit to enter 'recovery' state\n"
                "    2. Run `juju refresh` to the previously deployed charm revision or local charm file"
            )
        ]
        mock_logging.assert_has_calls(calls)

    @patch("charms.rolling_ops.v0.rollingops.RollingOpsManager._on_process_locks")
    @patch("charm.MySQLOperatorCharm.get_unit_address", return_value="10.0.1.1")
    @patch("mysql_vm_helpers.MySQL.set_dynamic_variable")
    @patch("mysql_vm_helpers.MySQL.get_primary_label", return_value="mysql-1")
    @patch("mysql_vm_helpers.MySQL.set_cluster_primary")
    def test_pre_upgrade_prepare(
        self,
        mock_set_cluster_primary,
        mock_get_primary_label,
        mock_set_dynamic_variable,
        mock_get_unit_address,
        _,
    ):
        """Test the pre upgrade prepare."""
        self.harness.set_leader(True)
        self.charm.on.config_changed.emit()

        self.charm.upgrade._pre_upgrade_prepare()

        mock_set_cluster_primary.assert_called_once()
        mock_get_primary_label.assert_called_once()
        assert mock_set_dynamic_variable.call_count == 2

    @patch("charm.MySQLOperatorCharm.recover_unit_after_restart")
    @patch("mysql_vm_helpers.MySQL.install_plugins")
    @patch("upgrade.set_cron_daemon")
    @patch("mysql_vm_helpers.MySQL.write_mysqld_config")
    @patch("upgrade.MySQLVMUpgrade._check_server_unsupported_downgrade")
    @patch("upgrade.MySQLVMUpgrade._reset_on_unsupported_downgrade")
    @patch("mysql_vm_helpers.MySQL.hold_if_recovering")
    @patch("pathlib.Path.exists", return_value=True)
    @patch("mysql_vm_helpers.MySQL.get_mysql_version", return_value="8.0.33")
    @patch("charm.MySQLOperatorCharm.install_workload", return_value=True)
    @patch("charm.MySQLOperatorCharm.unit_fqdn", return_value="10.0.1.1")
    @patch("mysql_vm_helpers.MySQL.stop_mysqld")
    @patch("mysql_vm_helpers.MySQL.start_mysqld")
    @patch("upgrade.MySQLVMUpgrade._check_server_upgradeability")
    @patch("mysql_vm_helpers.MySQL.setup_logrotate_and_cron", return_value=True)
    def test_upgrade_granted(
        self,
        mock_setup_logrotate_and_cron,
        mock_check_server_upgradeability,
        mock_start_mysqld,
        mock_stop_mysqld,
        mock_unit_fqdn,
        mock_install_workload,
        mock_get_mysql_version,
        mock_path_exists,
        mock_hold_if_recovering,
        mock_reset_on_unsupported_downgrade,
        mock_check_server_unsupported_downgrade,
        mock_write_mysqld_config,
        mock_set_cron_daemon,
        mock_install_plugins,
        mock_recover_unit_after_restart,
    ):
        """Test upgrade-granted hook."""
        self.charm.on.config_changed.emit()
        self.harness.update_relation_data(
            self.upgrade_relation_id, "mysql/0", {"state": "upgrading"}
        )
        self.charm.upgrade._on_upgrade_granted(None)
        self.assertEqual(
            self.harness.get_relation_data(self.upgrade_relation_id, "mysql/1")["state"],
            "idle",  # change to `completed` - behavior not yet set in the lib
        )
        mock_check_server_upgradeability.assert_called_once()
        mock_start_mysqld.assert_called_once()
        mock_stop_mysqld.assert_called_once()
        mock_install_workload.assert_called_once()
        mock_get_mysql_version.assert_called_once()
        mock_setup_logrotate_and_cron.assert_called_once()
        mock_write_mysqld_config.assert_called_once()

        self.harness.update_relation_data(
            self.upgrade_relation_id, "mysql/0", {"state": "upgrading"}
        )
        # setup for exception
        mock_recover_unit_after_restart.side_effect = RetryError

        self.charm.upgrade._on_upgrade_granted(None)
        self.assertEqual(
            self.harness.get_relation_data(self.upgrade_relation_id, "mysql/0")["state"], "failed"
        )

        # Failed to check server upgradeability
        self.harness.update_relation_data(
            self.upgrade_relation_id, "mysql/0", {"state": "upgrading"}
        )
        mock_check_server_upgradeability.side_effect = VersionError(message="foo", cause="bar")
        self.charm.upgrade._on_upgrade_granted(None)
        self.assertEqual(
            self.harness.get_relation_data(self.upgrade_relation_id, "mysql/0")["state"], "failed"
        )
        mock_check_server_upgradeability.side_effect = None

        # Failed to stop mysqld
        self.harness.update_relation_data(
            self.upgrade_relation_id, "mysql/0", {"state": "upgrading"}
        )
        mock_stop_mysqld.side_effect = MySQLStopMySQLDError
        self.charm.upgrade._on_upgrade_granted(None)
        self.assertEqual(
            self.harness.get_relation_data(self.upgrade_relation_id, "mysql/0")["state"], "failed"
        )
        mock_stop_mysqld.side_effect = None

        # Failed to start
        self.harness.update_relation_data(
            self.upgrade_relation_id, "mysql/0", {"state": "upgrading"}
        )
        mock_check_server_unsupported_downgrade.return_value = True
        mock_start_mysqld.side_effect = MySQLStartMySQLDError
        self.charm.upgrade._on_upgrade_granted(None)
        mock_reset_on_unsupported_downgrade.assert_called_once()

    @patch("charm.MySQLOperatorCharm.unit_fqdn")
    @patch("mysql_vm_helpers.MySQL.verify_server_upgradable")
    def test_check_server_upgradeability(self, mock_is_server_upgradeable, mock_unit_fqdn):
        """Test the server upgradeability check."""
        self.charm.upgrade.upgrade_stack = [0, 1]
        self.charm.upgrade._check_server_upgradeability()
        mock_is_server_upgradeable.assert_called_once()

        mock_is_server_upgradeable.side_effect = MySQLServerNotUpgradableError
        with self.assertRaises(VersionError):
            self.charm.upgrade._check_server_upgradeability()

        self.charm.upgrade.upgrade_stack = [0]
        mock_is_server_upgradeable.reset_mock()
        self.charm.upgrade._check_server_upgradeability()
        mock_is_server_upgradeable.assert_not_called()

    @patch("mysql_vm_helpers.MySQL.fetch_error_log")
    def test_check_server_unsupported_downgrade(self, mock_fetch_error_log):
        mock_fetch_error_log.return_value = "MY-013171"
        self.assertTrue(self.charm.upgrade._check_server_unsupported_downgrade())
        mock_fetch_error_log.return_value = "MY-013sdasa"
        self.assertTrue(not self.charm.upgrade._check_server_unsupported_downgrade())

    @patch("charm.MySQLOperatorCharm.join_unit_to_cluster")
    @patch("mysql_vm_helpers.MySQL.rescan_cluster")
    @patch("charm.MySQLOperatorCharm._get_primary_from_online_peer")
    @patch("charm.MySQLOperatorCharm.workload_initialise")
    @patch("mysql_vm_helpers.MySQL.install_and_configure_mysql_dependencies")
    @patch("mysql_vm_helpers.MySQL.uninstall_mysql")
    @patch("mysql_vm_helpers.MySQL.reset_data_dir")
    def test_reset_on_unsupported_downgrade(
        self,
        mock_reset_data_dir,
        mock_uninstall_workload,
        mock_install_workload,
        mock_init_workload,
        mock_get_primary,
        mock_rescan_cluster,
        mock_join_unit,
    ):
        self.charm.upgrade._reset_on_unsupported_downgrade()
        self.assertEqual(self.charm.unit_peer_data["member-role"], "secondary")
        self.assertEqual(self.charm.unit_peer_data["member-state"], "waiting")

    @patch("charms.rolling_ops.v0.rollingops.RollingOpsManager._on_process_locks")
    @patch("upgrade.MySQLVMUpgrade._prepare_upgrade_from_legacy")
    def test_upgrade_charm_legacy(self, mock_prepare_upgrade_from_legacy, _):
        self.harness.update_relation_data(self.upgrade_relation_id, "mysql/0", {"state": ""})

        # non leader
        self.charm.on.upgrade_charm.emit()
        self.assertEqual(
            self.harness.get_relation_data(self.upgrade_relation_id, "mysql/0")["state"], "ready"
        )

        # leader / deferred
        self.harness.update_relation_data(self.upgrade_relation_id, "mysql/0", {"state": ""})
        self.harness.set_leader(True)
        self.charm.on.upgrade_charm.emit()
        mock_prepare_upgrade_from_legacy.assert_not_called()

        # leader / not deferred
        mock_prepare_upgrade_from_legacy.reset_mock()
        self.harness.update_relation_data(self.upgrade_relation_id, "mysql/0", {"state": ""})
        self.harness.update_relation_data(self.upgrade_relation_id, "mysql/1", {"state": "ready"})
        self.harness.set_leader(True)
        self.charm.on.upgrade_charm.emit()
        self.assertEqual(
            self.harness.get_relation_data(self.upgrade_relation_id, "mysql/0")["state"], "ready"
        )
        mock_prepare_upgrade_from_legacy.assert_called_once()

    def test_prepare_upgrade_from_legacy(self):
        self.charm.upgrade._prepare_upgrade_from_legacy()
        self.assertEqual(
            self.harness.get_relation_data(self.upgrade_relation_id, "mysql")["upgrade-stack"],
            "[0, 1]",
        )
