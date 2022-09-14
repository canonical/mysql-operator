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
    CLUSTER_ADMIN_PASSWORD_KEY,
    CLUSTER_ADMIN_USERNAME,
    PASSWORD_LENGTH,
    PEER,
    REQUIRED_USERNAMES,
    ROOT_PASSWORD_KEY,
    ROOT_USERNAME,
    SERVER_CONFIG_PASSWORD_KEY,
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
        self.framework.observe(self.on.get_cluster_status_action, self._get_cluster_status)
        self.framework.observe(self.on.get_password_action, self._on_get_password)
        self.framework.observe(self.on.set_password_action, self._on_set_password)

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
        required_passwords = [
            ROOT_PASSWORD_KEY,
            SERVER_CONFIG_PASSWORD_KEY,
            CLUSTER_ADMIN_PASSWORD_KEY,
        ]

        for required_password in required_passwords:
            if not self._get_secret("app", required_password):
                self._set_secret(
                    "app", required_password, generate_random_password(PASSWORD_LENGTH)
                )

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

        # Safeguard against event deferall
        if self._mysql.is_instance_in_cluster(event_unit_label):
            logger.debug(
                f"Unit {event_unit_label} is already part of the cluster, don't try to add it again."
            )
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

        # Inform other hooks of current status
        self._peers.data[self.unit]["unit-status"] = "removing"

    # =======================
    #  Custom Action Handlers
    # =======================
    def _get_cluster_status(self, event: ActionEvent) -> None:
        """Action used to retrieve the cluster status."""
        event.set_results(self._mysql.get_cluster_status())

    def _on_get_password(self, event: ActionEvent) -> None:
        """Action used to retrieve the system user's password."""
        username = event.params.get("username") or ROOT_USERNAME

        if username not in REQUIRED_USERNAMES:
            raise RuntimeError("Invalid username.")

        if username == ROOT_USERNAME:
            secret_key = ROOT_PASSWORD_KEY
        elif username == SERVER_CONFIG_USERNAME:
            secret_key = SERVER_CONFIG_PASSWORD_KEY
        elif username == CLUSTER_ADMIN_USERNAME:
            secret_key = CLUSTER_ADMIN_PASSWORD_KEY
        else:
            raise RuntimeError("Invalid username.")

        event.set_results({"username": username, "password": self._get_secret("app", secret_key)})

    def _on_set_password(self, event: ActionEvent) -> None:
        """Action used to update/rotate the system user's password."""
        if not self.unit.is_leader():
            raise RuntimeError("set-password action can only be run on the leader unit.")

        username = event.params.get("username") or ROOT_USERNAME

        if username not in REQUIRED_USERNAMES:
            raise RuntimeError("Invalid username.")

        if username == ROOT_USERNAME:
            secret_key = ROOT_PASSWORD_KEY
        elif username == SERVER_CONFIG_USERNAME:
            secret_key = SERVER_CONFIG_PASSWORD_KEY
        elif username == CLUSTER_ADMIN_USERNAME:
            secret_key = CLUSTER_ADMIN_PASSWORD_KEY
        else:
            raise RuntimeError("Invalid username.")

        new_password = event.params.get("password") or generate_random_password(PASSWORD_LENGTH)

        self._mysql.update_user_password(username, new_password)

        self._set_secret("app", secret_key, new_password)

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
            self._get_secret("app", ROOT_PASSWORD_KEY),
            SERVER_CONFIG_USERNAME,
            self._get_secret("app", SERVER_CONFIG_PASSWORD_KEY),
            CLUSTER_ADMIN_USERNAME,
            self._get_secret("app", CLUSTER_ADMIN_PASSWORD_KEY),
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
            and self._get_secret("app", ROOT_PASSWORD_KEY)
            and self._get_secret("app", SERVER_CONFIG_PASSWORD_KEY)
            and self._get_secret("app", CLUSTER_ADMIN_PASSWORD_KEY)
        )

    @property
    def cluster_initialized(self):
        """Returns True if the cluster is initialized."""
        return self._peers.data[self.app].get("units-added-to-cluster", "0") >= "1"

    @property
    def app_peer_data(self) -> Dict:
        """Application peer relation data object."""
        if self._peers is None:
            return {}

        return self._peers.data[self.app]

    @property
    def unit_peer_data(self) -> Dict:
        """Unit peer relation data object."""
        if self._peers is None:
            return {}

        return self._peers.data[self.unit]

    def _get_secret(self, scope: str, key: str) -> Optional[str]:
        """Get secret from the secret storage."""
        if scope == "unit":
            return self.unit_peer_data.get(key, None)
        elif scope == "app":
            return self.app_peer_data.get(key, None)
        else:
            raise RuntimeError("Unknown secret scope.")

    def _set_secret(self, scope: str, key: str, value: Optional[str]) -> None:
        """Set secret in the secret storage."""
        if scope == "unit":
            if not value:
                del self.unit_peer_data[key]
                return
            self.unit_peer_data.update({key: value})
        elif scope == "app":
            if not value:
                del self.app_peer_data[key]
                return
            self.app_peer_data.update({key: value})
        else:
            raise RuntimeError("Unknown secret scope.")


if __name__ == "__main__":
    main(MySQLOperatorCharm)
