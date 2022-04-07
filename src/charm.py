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

from mysqlsh_helpers import (
    MySQL,
    MySQLInitializationError,
    MySQLUpdateConfigurationError,
)

logger = logging.getLogger(__name__)

# TODO: determine if version locking is needed for both mysql-shell and mysql-server
MYSQL_SHELL_SNAP_NAME = "mysql-shell"
MYSQL_APT_PACKAGE_NAME = "mysql-server-8.0"


class MySQLOperatorCharm(CharmBase):
    """Operator framework charm for MySQL."""

    def __init__(self, *args):
        super().__init__(*args)

        # Please do not reference this variable directly. Instead use _get_mysql_helpers().
        self._mysql_helpers = None

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
            logger.debug(f"Installing '{MYSQL_APT_PACKAGE_NAME}' apt package")
            apt.add_package(MYSQL_APT_PACKAGE_NAME)
        except (apt.PackageNotFoundError, apt.PackageError) as e:
            logger.exception(
                f"Failed to install '{MYSQL_APT_PACKAGE_NAME}' apt package",
                exc_info=e,
            )
            self.unit.status = BlockedStatus(f"Failed to install '{MYSQL_APT_PACKAGE_NAME}'")
            return

        # Install 'mysql-shell' snap
        try:
            cache = snap.SnapCache()
            mysql_shell = cache[MYSQL_SHELL_SNAP_NAME]

            if not mysql_shell.present:
                logger.debug(f"Installing '{MYSQL_SHELL_SNAP_NAME}' snap")
                mysql_shell.ensure(snap.SnapState.Latest, channel="stable")
        except (snap.SnapNotFoundError, snap.SnapError) as e:
            logger.exception(f"Failed to install the '{MYSQL_SHELL_SNAP_NAME}' snap", exc_info=e)
            self.unit.status = BlockedStatus(f"Failed to install '{MYSQL_SHELL_SNAP_NAME}'")
            return

        # Update the mysql configuration - from templates/mysqld.cnf
        try:
            mysql_helpers = self._get_mysql_helpers()
            mysql_helpers.update_mysql_configuration()
        except (MySQLInitializationError, MySQLUpdateConfigurationError):
            self.unit.status = BlockedStatus("Failed to update the mysql configuration")
            return

        # TODO: Set status to WaitingStatus once _on_start is implemented
        # Temporarily set the unit status to ActiveStatus
        # self.unit.status = WaitingStatus("Waiting to start MySQL")
        self.unit.status = ActiveStatus()

    def _on_start(self, _) -> None:
        """Ensure that required software is running."""
        pass

    # =======================
    #  Helpers
    # =======================

    def _get_mysql_helpers(self):
        """Returns an instance of the MySQL object from mysqlsh_helpers."""
        if not self._mysql_helpers:
            # TODO: replace stubbed arguments once mechanisms to generate them exist
            # Mechanisms = generating user/pass and storing+retrieving them from peer databag.
            self._mysql_helpers = MySQL(
                "clusteradminpassword",
                "clusteradmin",
                "test_cluster",
                "127.0.0.1",
                "password",
                "serverconfigpassword",
                "serverconfig",
            )

        return self._mysql_helpers


if __name__ == "__main__":
    main(MySQLOperatorCharm)
