# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import patch

from ops.model import ActiveStatus, BlockedStatus
from ops.testing import Harness

from charm import MySQLOperatorCharm


class TestCharm(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(MySQLOperatorCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()
        self.charm = self.harness.charm

    @patch("mysqlsh_helpers.MySQL.install_and_configure_mysql_dependencies")
    def test_on_install(self, _install_and_configure_mysql_dependencies):
        self.charm.on.install.emit()

        self.assertTrue(isinstance(self.harness.model.unit.status, ActiveStatus))

    @patch(
        "mysqlsh_helpers.MySQL.install_and_configure_mysql_dependencies", side_effect=Exception()
    )
    def test_on_install_exception(self, _install_and_configure_mysql_dependencies):
        self.charm.on.install.emit()

        self.assertTrue(isinstance(self.harness.model.unit.status, BlockedStatus))
