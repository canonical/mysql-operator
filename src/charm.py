#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charmed Machine Operator for MySQL."""

import hashlib
import logging
import secrets
import string

from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus

from mysqlsh_helpers import (
    MySQL,
    MySQLConfigureInstanceError,
    MySQLConfigureMySQLUsersError,
)

logger = logging.getLogger(__name__)

PASSWORD_LENGTH = 24
PEER = "mysql-replicas"


def generate_random_password(length: int) -> str:
    """Randomly generate a string intended to be used as a password.

    Args:
        length: length of the randomly generated string to be returned
    """
    choices = string.ascii_letters + string.digits
    return "".join([secrets.choice(choices) for i in range(length)])


def generate_random_hash() -> str:
    """Generate a hash based on a random string."""
    random_characters = generate_random_password(10)
    return hashlib.md5(random_characters.encode("utf-8")).hexdigest()


class MySQLOperatorCharm(CharmBase):
    """Operator framework charm for MySQL."""

    def __init__(self, *args):
        super().__init__(*args)

        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.leader_elected, self._on_leader_elected)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.start, self._on_start)

    # =======================
    #  Charm Lifecycle Hooks
    # =======================

    def _on_install(self, _) -> None:
        """Handle the install event."""
        self.unit.status = MaintenanceStatus("Installing MySQL")

        # Initial setup operations like installing dependencies, and creating users and groups.
        try:
            MySQL.install_and_configure_mysql_dependencies()
        except Exception:
            self.unit.status = BlockedStatus("Failed to install and configure MySQL")
            return

        self.unit.status = WaitingStatus("Waiting to start MySQL")

    def _on_leader_elected(self, _) -> None:
        """Handle the leader elected event."""
        # Set MySQL config values in the peer relation databag
        peer_data = self._peers.data[self.app]

        required_passwords = ["root_password", "server_config_password", "cluster_admin_password"]

        for required_password in required_passwords:
            if not peer_data.get(required_password):
                password = generate_random_password(PASSWORD_LENGTH)
                peer_data[required_password] = password

    def _on_config_changed(self, _) -> None:
        """Handle the config changed event."""
        # Only execute on unit leader
        if not self.unit.is_leader():
            return

        # Set the cluster name in the peer relation databag if it is not already set
        peer_data = self._peers.data[self.app]

        if not peer_data.get("cluster_name"):
            peer_data["cluster_name"] = self.config.get("cluster_name") or generate_random_hash()

    def _on_start(self, _) -> None:
        """Handle the start event."""
        try:
            # TODO: add logic to determine how to add non-leader instances to the cluster
            if self.unit.is_leader():
                self._mysql.configure_mysql_users()
                self._mysql.configure_instance()
        except MySQLConfigureMySQLUsersError:
            self.unit.status = BlockedStatus("Failed to initialize MySQL users")
            return
        except MySQLConfigureInstanceError:
            self.unit.status = BlockedStatus("Failed to configure instance for InnoDB")
            return

        self.unit.status = ActiveStatus()

    # =======================
    #  Helpers
    # =======================

    @property
    def _mysql(self):
        """Returns an instance of the MySQL object from mysqlsh_helpers."""
        peer_data = self._peers.data[self.app]

        return MySQL(
            self.model.get_binding(PEER).network.bind_address,
            peer_data["cluster_name"],
            peer_data["root_password"],
            "serverconfig",
            peer_data["server_config_password"],
            "clusteradmin",
            peer_data["cluster_admin_password"],
        )

    @property
    def _peers(self):
        """Retrieve the peer relation (`ops.model.Relation`)."""
        return self.model.get_relation(PEER)


if __name__ == "__main__":
    main(MySQLOperatorCharm)
