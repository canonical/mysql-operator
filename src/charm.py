#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charmed Machine Operator for MySQL."""

import hashlib
import logging
import secrets
import string

from ops.charm import (
    ActionEvent,
    CharmBase,
    RelationChangedEvent,
    RelationJoinedEvent,
    StartEvent,
)
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus

from mysqlsh_helpers import (
    MySQL,
    MySQLConfigureInstanceError,
    MySQLConfigureMySQLUsersError,
    MySQLCreateClusterError,
    MySQLInitializeJujuOperationsTableError,
)

logger = logging.getLogger(__name__)

CLUSTER_ADMIN_USERNAME = "clusteradmin"
SERVER_CONFIG_USERNAME = "serverconfig"
PASSWORD_LENGTH = 24
PEER = "database-peers"


def generate_random_password(length: int) -> str:
    """Randomly generate a string intended to be used as a password.

    Args:
        length: length of the randomly generated string to be returned

    Returns:
        a string with random letters and digits of length specified
    """
    choices = string.ascii_letters + string.digits
    return "".join([secrets.choice(choices) for i in range(length)])


def generate_random_hash() -> str:
    """Generate a random hash.

    Returns:
        A random MD5 hash
    """
    random_characters = generate_random_password(20)
    return hashlib.md5(random_characters.encode("utf-8")).hexdigest()


class MySQLOperatorCharm(CharmBase):
    """Operator framework charm for MySQL."""

    def __init__(self, *args):
        super().__init__(*args)

        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.leader_elected, self._on_leader_elected)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.start, self._on_start)
        self.framework.observe(
            self.on.database_storage_detaching, self._on_database_storage_detaching
        )

        self.framework.observe(self.on[PEER].relation_joined, self._on_peer_relation_joined)
        self.framework.observe(self.on[PEER].relation_changed, self._on_peer_relation_changed)

        self.framework.observe(
            self.on.get_cluster_admin_credentials_action, self._on_get_cluster_admin_credentials
        )
        self.framework.observe(
            self.on.get_server_config_credentials_action, self._on_get_server_config_credentials
        )

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

        required_passwords = ["root-password", "server-config-password", "cluster-admin-password"]

        for required_password in required_passwords:
            if not peer_data.get(required_password):
                password = generate_random_password(PASSWORD_LENGTH)
                peer_data[required_password] = password

    def _on_config_changed(self, _) -> None:
        """Handle the config changed event."""
        # Only execute on leader unit
        if not self.unit.is_leader():
            return

        # Set the cluster name in the peer relation databag if it is not already set
        peer_data = self._peers.data[self.app]

        if not peer_data.get("cluster-name"):
            peer_data["cluster-name"] = (
                self.config.get("cluster-name") or f"cluster_{generate_random_hash()}"
            )

    def _on_start(self, event: StartEvent) -> None:
        """Handle the start event."""
        # Configure MySQL users and the instance for use in an InnoDB cluster
        # Safeguard unit starting before leader unit sets peer data
        if not self._is_peer_data_set:
            event.defer()
            return

        try:
            self._mysql.configure_mysql_users()
            self._mysql.configure_instance()
        except MySQLConfigureMySQLUsersError:
            self.unit.status = BlockedStatus("Failed to initialize MySQL users")
            return
        except MySQLConfigureInstanceError:
            self.unit.status = BlockedStatus("Failed to configure instance for InnoDB")
            return

        # Create the cluster on the juju leader unit
        if not self.unit.is_leader():
            self.unit.status = WaitingStatus("Waiting to join the cluster")
            return

        try:
            unit_label = self.unit.name.replace("/", "-")
            self._mysql.create_cluster(unit_label)
            self._mysql.initialize_juju_units_operations_table()
        except MySQLCreateClusterError:
            self.unit.status = BlockedStatus("Failed to create the InnoDB cluster")
            return
        except MySQLInitializeJujuOperationsTableError:
            self.unit.status = BlockedStatus("Failed to initialize juju units operations table")
            return

        self._peers.data[self.app]["units-added-to-cluster"] = "1"

        self.unit.status = ActiveStatus()

    def _on_peer_relation_joined(self, event: RelationJoinedEvent) -> None:
        """Handle the peer relation joined event."""
        # Only execute in the unit leader
        if not self.unit.is_leader():
            return

        # Defer if the instance is not configured for use in an InnoDB cluster
        # Every instance gets configured for use in an InnoDB cluster on start
        event_unit_address = event.relation.data[event.unit]["private-address"]
        event_unit_label = event.unit.name.replace("/", "-")

        if not self._mysql.is_instance_configured_for_innodb(event_unit_address, event_unit_label):
            event.defer()
            return

        # Add the instance to the cluster. This operation uses locks to ensure that
        # only one instance is added to the cluster at a time
        # (so only one instance is involved in a state transfer at a time)
        self._mysql.add_instance_to_cluster(event_unit_address, event_unit_label)

        # Update 'units-added-to-cluster' counter in the peer relation databag
        # in order to trigger a relation_changed event which will move the added unit
        # into ActiveStatus
        units_started = int(self._peers.data[self.app]["units-added-to-cluster"])
        self._peers.data[self.app]["units-added-to-cluster"] = str(units_started + 1)

    def _on_peer_relation_changed(self, event: RelationChangedEvent) -> None:
        """Handle the peer relation changed event."""
        # Only execute if peer relation data contains cluster config values
        if not self._is_peer_data_set:
            event.defer()
            return

        # Update the unit's status to ActiveStatus if it was added to the cluster
        unit_label = self.unit.name.replace("/", "-")
        if isinstance(self.unit.status, WaitingStatus) and self._mysql.is_instance_in_cluster(
            unit_label
        ):
            self.unit.status = ActiveStatus()

    def _on_database_storage_detaching(self, _) -> None:
        """Handle the database storage detaching event."""
        # The following operation uses locks to ensure that only one instance is removed
        # from the cluster at a time (to avoid split-brain or lack of majority issues)
        unit_label = self.unit.name.replace("/", "-")
        self._mysql.remove_instance(unit_label)

    # =======================
    #  Custom Action Handlers
    # =======================

    def _on_get_cluster_admin_credentials(self, event: ActionEvent) -> None:
        """Action used to retrieve the cluster admin credentials."""
        event.set_results(
            {
                "cluster-admin-username": CLUSTER_ADMIN_USERNAME,
                "cluster-admin-password": self._peers.data[self.app].get(
                    "cluster-admin-password", "<to_be_generated>"
                ),
            }
        )

    def _on_get_server_config_credentials(self, event: ActionEvent) -> None:
        """Action used to retrieve the server config credentials."""
        event.set_results(
            {
                "server-config-username": SERVER_CONFIG_USERNAME,
                "server-config-password": self._peers.data[self.app].get(
                    "server-config-password", "<to_be_generated>"
                ),
            }
        )

    # =======================
    #  Helpers
    # =======================

    @property
    def _mysql(self):
        """Returns an instance of the MySQL object from mysqlsh_helpers."""
        peer_data = self._peers.data[self.app]

        return MySQL(
            self.model.get_binding(PEER).network.bind_address,
            peer_data["cluster-name"],
            peer_data["root-password"],
            SERVER_CONFIG_USERNAME,
            peer_data["server-config-password"],
            CLUSTER_ADMIN_USERNAME,
            peer_data["cluster-admin-password"],
        )

    @property
    def _peers(self):
        """Retrieve the peer relation (`ops.model.Relation`)."""
        return self.model.get_relation(PEER)

    @property
    def _is_peer_data_set(self):
        peer_data = self._peers.data[self.app]

        return (
            peer_data.get("cluster-name")
            and peer_data.get("root-password")
            and peer_data.get("server-config-password")
            and peer_data.get("cluster-admin-password")
        )


if __name__ == "__main__":
    main(MySQLOperatorCharm)
