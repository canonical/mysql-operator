# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import unittest

from ops.testing import Harness

from charm import MySQLOperatorCharm
from constants import HOSTNAME_DETAILS, PEER

APP_NAME = "mysql"


class TestHostnameResolution(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(MySQLOperatorCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()
        self.charm = self.harness.charm
        self.hostname_resolution = self.charm.hostname_resolution

    def test_get_peer_host_details(self):
        """Test get_peer_host_details method."""
        host_entries = self.hostname_resolution._get_peer_host_details()

        # before relation
        self.assertEqual(host_entries, [])

        # Add relation
        id = self.harness.add_relation(PEER, APP_NAME)

        host_entries = self.hostname_resolution._get_peer_host_details()
        self.assertEqual(host_entries, [])

        # Add unit
        self.harness.add_relation_unit(id, f"{APP_NAME}/0")
        self.harness.update_relation_data(
            id,
            f"{APP_NAME}/0",
            {
                HOSTNAME_DETAILS: json.dumps(
                    {"address": "1.1.1.1", "names": ["name1", "name2", "name3"]}
                )
            },
        )

        host_entries = self.hostname_resolution._get_peer_host_details()
        self.assertEqual(len(host_entries), 1)
        self.assertEqual(host_entries[0].address, "1.1.1.1")

    def test_update_host_details_in_databag(self):
        """Test update_host_details_in_databag method."""
        # Add relation
        self.harness.add_relation(PEER, APP_NAME)
        self.assertEqual(self.charm.unit_peer_data.get(HOSTNAME_DETAILS), None)
        self.hostname_resolution._update_host_details_in_databag(None)

        self.assertTrue("mysql-0" in self.charm.unit_peer_data[HOSTNAME_DETAILS])

    def test_unit_in_hosts(self):
        """Test _unit_in_hosts method."""
        self.assertFalse(self.hostname_resolution.is_unit_in_hosts)
