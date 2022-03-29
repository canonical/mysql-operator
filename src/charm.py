#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charmed Machine Operator for MySQL."""

import logging
import subprocess

from charms.operator_libs_linux.v0 import apt
from charms.operator_libs_linux.v1 import snap
from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus

logger = logging.getLogger(__name__)


class MySQLOperatorCharm(CharmBase):
    """Operator framework charm for MySQL."""

    def __init__(self, *args):
        super().__init__(*args)

        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.start, self._on_start)

    # =======================
    #  Charm Lifecycle Hooks
    # =======================

    def _on_install(self, _) -> None:
        """Initial setup operations like installing dependencies, and creating users and groups."""
        self.unit.status = MaintenanceStatus("Installing MySQL")

        # Install 'mysql-server-8.0' apt package
        # Note: installing mysql-server will create the 'mysql' user and 'mysql' group,
        # and run mysql with the 'mysql' user
        try:
            logger.debug("Updating apt cache")
            apt.update()
        except subprocess.CalledProcessError as e:
            logger.exception("Failed to update apt cache", exc_info=e)
            self.unit.status = BlockedStatus("Failed to update apt")
            return

        try:
            logger.debug("Installing 'mysql-server-8.0' apt package")
            apt.add_package("mysql-server-8.0")
        except apt.PackageNotFoundError as e:
            logger.exception(
                "'mysql-server-8.0' apt package not found in package cache or on system",
                exc_info=e,
            )
            self.unit.status = BlockedStatus("Failed to install 'mysql-server-8.0'")
            return

        # Install 'mysql-shell' snap
        try:
            cache = snap.SnapCache()
            mysql_shell = cache["mysql-shell"]

            if not mysql_shell.present:
                logger.debug("Installing 'mysql-shell' snap")
                mysql_shell.ensure(snap.SnapState.Latest, channel="stable")
        except snap.SnapError as e:
            logger.exception("Failed to install the 'mysql-shell' snap", exc_info=e)
            self.unit.status = BlockedStatus("Failed to install 'mysql-shell'")
            return

        self.unit.status = WaitingStatus("Waiting to start MySQL")

    def _on_start(self, _) -> None:
        """Ensure that required software is running."""
        self.unit.status = ActiveStatus()


if __name__ == "__main__":
    main(MySQLOperatorCharm)
