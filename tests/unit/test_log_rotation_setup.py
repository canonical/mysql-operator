# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import MagicMock, patch

from ops.testing import Harness

from charm import MySQLOperatorCharm
from constants import COS_AGENT_RELATION_NAME, PEER


class TestLogRotationSetup(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(MySQLOperatorCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()
        self.peer_relation_id = self.harness.add_relation(PEER, "mysql")
        self.harness.update_relation_data(
            self.peer_relation_id,
            "mysql",
            {"cluster-name": "test_cluster", "cluster-set-domain-name": "test_cluster_set"},
        )
        self.charm = self.harness.charm

    @patch("subprocess.Popen")
    def test_cos_relation_created(self, mock_popen):
        self.harness.add_relation(COS_AGENT_RELATION_NAME, "grafana-agent")
        mock_popen.assert_called_once()

    @patch("mysql_vm_helpers.MySQL.setup_logrotate_and_cron")
    def test_log_syncing(self, mock_setup):
        self.harness.update_config({"logs_retention_period": "auto"})
        self.harness.add_relation(COS_AGENT_RELATION_NAME, "grafana-agent")
        event = MagicMock()
        self.charm.log_rotation_setup._update_logs_rotation(event)
        self.assertEqual(self.harness.charm.unit_peer_data["logs_synced"], "true")
        mock_setup.assert_called_once()

    @patch("mysql_vm_helpers.MySQL.setup_logrotate_and_cron")
    def test_cos_relation_broken(self, mock_setup):
        self.harness.update_config({"logs_retention_period": "auto"})
        event = MagicMock()
        self.charm.log_rotation_setup._cos_relation_broken(event)
        self.assertNotIn("logs_synced", self.harness.charm.unit_peer_data)
        mock_setup.assert_called_once()


if __name__ == "__main__":
    unittest.main()
