# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import subprocess
import unittest
from unittest.mock import MagicMock, patch

from charms.operator_libs_linux.v0 import apt
from charms.operator_libs_linux.v1 import snap
from ops.model import ActiveStatus, BlockedStatus
from ops.testing import Harness

from charm import MySQLOperatorCharm


class TestCharm(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(MySQLOperatorCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()
        self.charm = self.harness.charm

    @patch("charms.operator_libs_linux.v0.apt.update")
    @patch("charms.operator_libs_linux.v0.apt.add_package")
    @patch("charms.operator_libs_linux.v1.snap.SnapCache")
    def test_on_install(self, _snap_cache, _apt_add_package, _apt_update):
        """Test the successful installation of packages."""
        mock_cache = MagicMock()
        _snap_cache.return_value = mock_cache

        mock_mysql_shell = MagicMock()
        mock_cache.__getitem__.return_value = mock_mysql_shell

        mock_mysql_shell.present = False

        mock_ensure = MagicMock()
        mock_mysql_shell.ensure = mock_ensure

        self.charm.on.install.emit()

        _apt_update.assert_called_once()
        _apt_add_package.assert_called_once_with("mysql-server-8.0")

        mock_ensure.assert_called_once_with(snap.SnapState.Latest, channel="stable")

        self.assertEqual(self.harness.model.unit.status, ActiveStatus())

    @patch("charms.operator_libs_linux.v0.apt.update")
    def test_on_install_apt_update_error(self, _apt_update):
        """Test an issue with apt.update."""
        _apt_update.side_effect = subprocess.CalledProcessError(cmd="apt update", returncode=127)

        self.charm.on.install.emit()

        _apt_update.assert_called_once()
        self.assertEqual(self.harness.model.unit.status, BlockedStatus("Failed to update apt"))

    @patch("charms.operator_libs_linux.v0.apt.update")
    @patch("charms.operator_libs_linux.v0.apt.add_package")
    def test_on_install_apt_add_package_error(self, _apt_add_package, _apt_update):
        """Test an issue with apt.add_package."""
        # Test PackageNotFoundError
        _apt_add_package.side_effect = apt.PackageNotFoundError

        self.charm.on.install.emit()

        _apt_update.assert_called_once()
        _apt_add_package.assert_called_once_with("mysql-server-8.0")

        self.assertEqual(
            self.harness.model.unit.status, BlockedStatus("Failed to find 'mysql-server-8.0'")
        )

        # Reset the mocks
        _apt_update.reset_mock()
        _apt_add_package.reset_mock()

        # Test PackageError
        _apt_add_package.side_effect = apt.PackageError

        self.charm.on.install.emit()

        _apt_update.assert_called_once()
        _apt_add_package.assert_called_once_with("mysql-server-8.0")

        self.assertEqual(
            self.harness.model.unit.status, BlockedStatus("Failed to install 'mysql-server-8.0'")
        )

    @patch("charms.operator_libs_linux.v0.apt.update")
    @patch("charms.operator_libs_linux.v0.apt.add_package")
    @patch("charms.operator_libs_linux.v1.snap.SnapCache")
    def test_on_install_snap_error(self, _snap_cache, _apt_add_package, _apt_update):
        """Test an issue with snap installations."""
        # Test SnapNotFoundError
        _snap_cache.side_effect = snap.SnapNotFoundError

        self.charm.on.install.emit()

        _apt_update.assert_called_once()
        _apt_add_package.assert_called_once_with("mysql-server-8.0")

        self.assertEqual(
            self.harness.model.unit.status, BlockedStatus("Failed to find 'mysql-shell'")
        )

        # Reset the mocks
        _apt_update.reset_mock()
        _apt_add_package.reset_mock()
        _snap_cache.reset_mock()

        # Test SnapError
        _snap_cache.side_effect = snap.SnapError

        self.charm.on.install.emit()

        _apt_update.assert_called_once()
        _apt_add_package.assert_called_once_with("mysql-server-8.0")

        self.assertEqual(
            self.harness.model.unit.status, BlockedStatus("Failed to install 'mysql-shell'")
        )
