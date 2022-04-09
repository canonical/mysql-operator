#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charmed Machine Operator for MySQL."""

import logging

from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus

from mysqlsh_helpers import MySQL

logger = logging.getLogger(__name__)


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

        try:
            MySQL.install_and_configure_mysql_dependencies()
        except Exception:
            self.unit.status = BlockedStatus("Failed to install and configure MySQL")
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

    @property
    def _mysql(self):
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
