#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charmed Machine Operator for MySQL."""

import logging
import subprocess

from charms.operator_libs_linux.v0 import apt
from charms.operator_libs_linux.v1 import snap
from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus

logger = logging.getLogger(__name__)


class MySQLOperatorCharm(CharmBase):
    """Operator framework charm for MySQL."""

    def __init__(self, *args):
        super().__init__(*args)

        self.mysqlsh_snap_name = "mysql-shell"
        self.mysql_apt_package_name = "mysql-server-8.0"

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
            logger.debug(f"Installing '{self.mysql_apt_package_name}' apt package")
            apt.add_package(self.mysql_apt_package_name)
        except apt.PackageNotFoundError as e:
            logger.exception(
                f"'{self.mysql_apt_package_name}' apt package not found in package cache or on system",
                exc_info=e,
            )
            self.unit.status = BlockedStatus(f"Failed to find '{self.mysql_apt_package_name}'")
            return
        except apt.PackageError as e:
            logger.exception(
                f"could not install package '{self.mysql_apt_package_name}'",
                exc_info=e,
            )
            self.unit.status = BlockedStatus(f"Failed to install '{self.mysql_apt_package_name}'")
            return

        # Install 'mysql-shell' snap
        try:
            cache = snap.SnapCache()
            mysql_shell = cache[self.mysqlsh_snap_name]

            if not mysql_shell.present:
                logger.debug(f"Installing '{self.mysqlsh_snap_name}' snap")
                mysql_shell.ensure(snap.SnapState.Latest, channel="stable")
        except snap.SnapNotFoundError as e:
            logger.exception(f"Failed to find the '{self.mysqlsh_snap_name}' snap", exc_info=e)
            self.unit.status = BlockedStatus(f"Failed to find '{self.mysqlsh_snap_name}'")
            return
        except snap.SnapError as e:
            logger.exception(f"Failed to install the '{self.mysqlsh_snap_name}' snap", exc_info=e)
            self.unit.status = BlockedStatus(f"Failed to install '{self.mysqlsh_snap_name}'")
            return

        # TODO: Set status to WaitingStatus once _on_start is implemented
        # Temporarily set the unit status to ActiveStatus
        # self.unit.status = WaitingStatus("Waiting to start MySQL")
        self.unit.status = ActiveStatus()

    def _on_start(self, _) -> None:
        """Ensure that required software is running."""
        pass


if __name__ == "__main__":
    main(MySQLOperatorCharm)
