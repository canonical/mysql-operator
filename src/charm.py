#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charmed Machine Operator for MySQL."""

import logging
from typing import Dict, Optional

from charms.mysql.v0.mysql import (
    MySQLConfigureInstanceError,
    MySQLConfigureMySQLUsersError,
    MySQLCreateClusterError,
    MySQLGetMySQLVersionError,
    MySQLInitializeJujuOperationsTableError,
)
from ops.charm import (
    ActionEvent,
    CharmBase,
    RelationChangedEvent,
    RelationJoinedEvent,
    StartEvent,
)
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus

from constants import (
    CLUSTER_ADMIN_USERNAME,
    PASSWORD_LENGTH,
    PEER,
    SERVER_CONFIG_USERNAME,
)
from mysqlsh_helpers import MySQL
from relations.database import DatabaseRelation
from relations.db_router import DBRouterRelation
from relations.mysql import MySQLRelation
from relations.shared_db import SharedDBRelation
from utils import generate_random_hash, generate_random_password

logger = logging.getLogger(__name__)


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
        self.framework.observe(self.on.get_root_credentials_action, self._on_get_root_credentials)
        self.framework.observe(self.on.get_cluster_status_action, self._get_cluster_status)

        self.shared_db_relation = SharedDBRelation(self)
        self.db_router_relation = DBRouterRelation(self)
        self.database_relation = DatabaseRelation(self)
        self.mysql_relation = MySQLRelation(self)

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

        self.unit.status = MaintenanceStatus("Setting up database cluster")

        try:
            self._mysql.configure_mysql_users()
            self._mysql.configure_instance()
            self._mysql.wait_until_mysql_connection()
            workload_version = self._mysql.get_mysql_version()
            self.unit.set_workload_version(workload_version)
        except MySQLConfigureMySQLUsersError:
            self.unit.status = BlockedStatus("Failed to initialize MySQL users")
            return
        except MySQLConfigureInstanceError:
            self.unit.status = BlockedStatus("Failed to configure instance for InnoDB")
            return
        except MySQLGetMySQLVersionError:
            logger.debug("Fail to get MySQL version")

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
        # Only execute if peer relation data contains cluster config values
        if not self._is_peer_data_set:
            return

        unit_label = self.unit.name.replace("/", "-")

        # No need to remove the instance from the cluster if it is not a member of the cluster
        if not self._mysql.is_instance_in_cluster(unit_label):
            return

        # The following operation uses locks to ensure that only one instance is removed
        # from the cluster at a time (to avoid split-brain or lack of majority issues)
        self._mysql.remove_instance(unit_label)

    # =======================
    #  Custom Action Handlers
    # =======================

    def _on_get_cluster_admin_credentials(self, event: ActionEvent) -> None:
        """Action used to retrieve the cluster admin credentials."""
        event.set_results(
            {
                "cluster-admin-username": CLUSTER_ADMIN_USERNAME,
                "cluster-admin-password": self._get_secret("app", "cluster-admin-password"),
            }
        )

    def _on_get_server_config_credentials(self, event: ActionEvent) -> None:
        """Action used to retrieve the server config credentials."""
        event.set_results(
            {
                "server-config-username": SERVER_CONFIG_USERNAME,
                "server-config-password": self._get_secret("app", "server-config-password"),
            }
        )

    def _on_get_root_credentials(self, event: ActionEvent) -> None:
        """Action used to retrieve the root credentials."""
        event.set_results(
            {
                "root-username": "root",
                "root-password": self._get_secret("app", "root-password"),
            }
        )

    def _get_cluster_status(self, event: ActionEvent) -> None:
        """Action used to retrieve the cluster status."""
        event.set_results(self._mysql.get_cluster_status())

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
            self._get_secret("app", "root-password"),
            SERVER_CONFIG_USERNAME,
            self._get_secret("app", "server-config-password"),
            CLUSTER_ADMIN_USERNAME,
            self._get_secret("app", "cluster-admin-password"),
        )

    @property
    def _peers(self):
        """Retrieve the peer relation (`ops.model.Relation`)."""
        return self.model.get_relation(PEER)

    @property
    def _is_peer_data_set(self):
        """Returns True if the peer relation data is set."""
        peer_data = self._peers.data[self.app]

        return (
            peer_data.get("cluster-name")
            and self._get_secret("app", "root-password")
            and self._get_secret("app", "server-config-password")
            and self._get_secret("app", "cluster-admin-password")
        )

    @property
    def cluster_initialized(self):
        """Returns True if the cluster is initialized."""
        return self._peers.data[self.app].get("units-added-to-cluster", "0") >= "1"

    @property
    def unit_data(self) -> Dict:
        """Peer relation data object."""
        if self._peers is None:
            return {}

        return self._peers.data[self.unit]

    @property
    def app_data(self) -> Dict:
        """Peer relation data object."""
        if self._peers is None:
            return {}

        return self._peers.data[self.app]

    def _get_secret(self, scope: str, key: str) -> Optional[str]:
        """Get TLS secret from the secret storage."""
        if scope == "unit":
            return self.unit_data.get(key, None)
        elif scope == "app":
            return self.app_data.get(key, None)
        else:
            raise RuntimeError("Unknown secret scope.")

    def _set_secret(self, scope: str, key: str, value: Optional[str]) -> None:
        """Get TLS secret from the secret storage."""
        if scope == "unit":
            if not value:
                del self.unit_data[key]
                return
            self.unit_data.update({key: value})
        elif scope == "app":
            if not value:
                del self.app_data[key]
                return
            self.app_data.update({key: value})
        else:
            raise RuntimeError("Unknown secret scope.")


if __name__ == "__main__":
    main(MySQLOperatorCharm)
