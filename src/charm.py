#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charmed Machine Operator for MySQL."""

import logging
from typing import Dict, Optional

from charms.mysql.v0.mysql import (
    MySQLAddInstanceToClusterError,
    MySQLConfigureInstanceError,
    MySQLConfigureMySQLUsersError,
    MySQLCreateClusterError,
    MySQLGetMemberStateError,
    MySQLGetMySQLVersionError,
    MySQLInitializeJujuOperationsTableError,
    MySQLRebootFromCompleteOutageError,
)
from charms.operator_libs_linux.v0.systemd import (
    service_restart,
    service_running,
    service_start,
    service_stop,
)
from charms.rolling_ops.v0.rollingops import RollingOpsManager
from ops.charm import (
    ActionEvent,
    CharmBase,
    RelationChangedEvent,
    RelationJoinedEvent,
    StartEvent,
)
from ops.main import main
from ops.model import (
    ActiveStatus,
    BlockedStatus,
    MaintenanceStatus,
    StatusBase,
    WaitingStatus,
)
from tenacity import RetryError, Retrying, stop_after_attempt, wait_fixed

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
    SERVICE_NAME,
)
from mysql_vm_helpers import (
    MySQL,
    MySQLDataPurgeError,
    MySQLReconfigureError,
    instance_hostname,
)
from relations.db_router import DBRouterRelation
from relations.mysql import MySQLRelation
from relations.mysql_provider import MySQLProvider
from relations.mysql_tls import MySQLTLS
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
        self.framework.observe(self.on.update_status, self._on_update_status)
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
        self.database_relation = MySQLProvider(self)
        self.mysql_relation = MySQLRelation(self)
        self.tls = MySQLTLS(self)
        self.restart_manager = RollingOpsManager(
            charm=self, relation="restart", callback=self._restart
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
        required_passwords = [
            ROOT_PASSWORD_KEY,
            SERVER_CONFIG_PASSWORD_KEY,
            CLUSTER_ADMIN_PASSWORD_KEY,
        ]

        for required_password in required_passwords:
            if not self.get_secret("app", required_password):
                self.set_secret(
                    "app", required_password, generate_random_password(PASSWORD_LENGTH)
                )

    def _on_config_changed(self, _) -> None:
        """Handle the config changed event."""
        # Only execute on leader unit
        if not self.unit.is_leader():
            return

        # Set the cluster name in the peer relation databag if it is not already set
        if not self.app_peer_data.get("cluster-name"):
            self.app_peer_data["cluster-name"] = (
                self.config.get("cluster-name") or f"cluster_{generate_random_hash()}"
            )

    def _on_start(self, event: StartEvent) -> None:
        """Handle the start event."""
        # Configure MySQL users and the instance for use in an InnoDB cluster
        # Safeguard unit starting before leader unit sets peer data
        if not self._is_peer_data_set:
            event.defer()
            return

        if self.unit_peer_data.get("unit-initialized") == "True":
            # if receiving on start after unit initialization
            logger.debug("Delegate status update for start handler on initialized unit.")
            self._on_update_status(None)
            return

        self.unit.status = MaintenanceStatus("Setting up cluster node")

        try:
            self._workload_initialise()
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
            self.unit_peer_data["member-role"] = "secondary"
            self.unit_peer_data["member-state"] = "waiting"
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

        self.app_peer_data["units-added-to-cluster"] = "1"
        self.unit_peer_data["unit-initialized"] = "True"
        self.unit_peer_data["member-role"] = "primary"
        self.unit.status = ActiveStatus(self.active_status_message)

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

        # Safeguard against event deferral
        if self._mysql.is_instance_in_cluster(event_unit_label):
            logger.debug(
                f"Unit {event_unit_label} is already part of the cluster, skipping add to cluster."
            )
            return

        # Add the instance to the cluster. This operation uses locks to ensure that
        # only one instance is added to the cluster at a time
        # (so only one instance is involved in a state transfer at a time)
        try:
            self._mysql.add_instance_to_cluster(event_unit_address, event_unit_label)
        except MySQLAddInstanceToClusterError:
            # won't fail leader due to issues in instance
            return

        # Update 'units-added-to-cluster' counter in the peer relation databag
        # in order to trigger a relation_changed event which will move the added unit
        # into ActiveStatus
        units_started = int(self.app_peer_data["units-added-to-cluster"])
        self.app_peer_data["units-added-to-cluster"] = str(units_started + 1)

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
            self.unit_peer_data["unit-initialized"] = "True"
            self.unit.status = ActiveStatus(self.active_status_message)

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
        self.unit_peer_data["unit-status"] = "removing"

    def _on_update_status(self, _) -> None:
        """Handle update status.

        Takes care of workload health checks.
        """
        if not self.cluster_initialized or not self.unit_peer_data.get("member-role"):
            # health checks only after cluster and member are initialised
            return
        if (
            self.unit_peer_data.get("member-state") == "waiting"
            and not self.unit_peer_data.get("unit-initialized")
            and not self.unit.is_leader()
        ):
            # avoid changing status while in initialisation
            return

        # retrieve and persist state for every unit
        try:
            state, role = self._mysql.get_member_state()
            self.unit_peer_data["member-role"] = role
            self.unit_peer_data["member-state"] = state
        except MySQLGetMemberStateError:
            role = self.unit_peer_data["member-role"] = "unknown"
            state = self.unit_peer_data["member-state"] = "unreachable"
        logger.info(f"Unit workload member-state is {state} with member-role {role}")

        # set unit status based on member-{state,role}
        self.unit.status = (
            ActiveStatus(self.active_status_message)
            if state == "online"
            else MaintenanceStatus(state)
        )

        if state == "recovering":
            # server is in the process of becoming an active member
            logger.info("Instance is being recovered")
            return

        if state == "offline":
            # Group Replication is active but the member does not belong to any group
            all_states = {
                self.peers.data[unit].get("member-state", "unknown") for unit in self.peers.units
            }

            if all_states in [{"offline"}, set()] and self.unit.is_leader():
                # All instance are off or its a single unit cluster
                # reboot cluster from outage from the leader unit
                logger.debug("Attempting reboot from complete outage.")
                try:
                    # reboot from outage forcing it when it a single unit
                    self._mysql.reboot_from_complete_outage(force=all_states == set())
                except MySQLRebootFromCompleteOutageError:
                    logger.error("Failed to reboot cluster from complete outage.")
                    self.unit.status = BlockedStatus("failed to recover cluster.")

        if state == "unreachable" and (
            service_running(SERVICE_NAME) or not service_start(SERVICE_NAME)
        ):
            # mysqld access not possible with daemon running or start fails
            # force reset necessary
            self.unit.status = MaintenanceStatus("Workload reset")
            self.unit.status = self._workload_reset()

    # =======================
    #  Custom Action Handlers
    # =======================
    def _get_cluster_status(self, event: ActionEvent) -> None:
        """Action used to retrieve the cluster status."""
        status = self._mysql.get_cluster_status()
        if status:
            event.set_results(
                {
                    "success": True,
                    "status": status,
                }
            )
        else:
            event.set_results(
                {
                    "success": False,
                    "message": "Failed to read cluster status.  See logs for more information.",
                }
            )

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

        event.set_results({"username": username, "password": self.get_secret("app", secret_key)})

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

        self.set_secret("app", secret_key, new_password)

    # =======================
    #  Helpers
    # =======================

    @property
    def _mysql(self):
        """Returns an instance of the MySQL object."""
        return MySQL(
            self.model.get_binding(PEER).network.bind_address,
            self.app_peer_data["cluster-name"],
            self.get_secret("app", ROOT_PASSWORD_KEY),
            SERVER_CONFIG_USERNAME,
            self.get_secret("app", SERVER_CONFIG_PASSWORD_KEY),
            CLUSTER_ADMIN_USERNAME,
            self.get_secret("app", CLUSTER_ADMIN_PASSWORD_KEY),
        )

    @property
    def peers(self):
        """Retrieve the peer relation (`ops.model.Relation`)."""
        return self.model.get_relation(PEER)

    @property
    def _is_peer_data_set(self):
        """Returns True if the peer relation data is set."""
        return (
            self.app_peer_data.get("cluster-name")
            and self.get_secret("app", ROOT_PASSWORD_KEY)
            and self.get_secret("app", SERVER_CONFIG_PASSWORD_KEY)
            and self.get_secret("app", CLUSTER_ADMIN_PASSWORD_KEY)
        )

    @property
    def cluster_initialized(self):
        """Returns True if the cluster is initialized."""
        return self.app_peer_data.get("units-added-to-cluster", "0") >= "1"

    @property
    def app_peer_data(self) -> Dict:
        """Application peer relation data object."""
        if self.peers is None:
            return {}

        return self.peers.data[self.app]

    @property
    def unit_peer_data(self) -> Dict:
        """Unit peer relation data object."""
        if self.peers is None:
            return {}

        return self.peers.data[self.unit]

    def get_secret(self, scope: str, key: str) -> Optional[str]:
        """Get secret from the secret storage."""
        if scope == "unit":
            return self.unit_peer_data.get(key, None)
        elif scope == "app":
            return self.app_peer_data.get(key, None)
        else:
            raise RuntimeError("Unknown secret scope.")

    def set_secret(self, scope: str, key: str, value: Optional[str]) -> None:
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

    @property
    def active_status_message(self):
        """Active status message."""
        role = self.unit_peer_data.get("member-role")
        return f"Unit is ready: Mode: {'RW' if role == 'primary' else 'RO'}"

    def _workload_initialise(self):
        """Workload initialisation commands.

        Create users and configuration to setup instance as an Group Replication node.
        Raised errors must be treated on handlers.
        """
        self._mysql.configure_mysql_users()
        self._mysql.configure_instance()
        self._mysql.wait_until_mysql_connection()
        workload_version = self._mysql.get_mysql_version()
        self.unit.set_workload_version(workload_version)
        self.unit_peer_data["instance-hostname"] = f"{instance_hostname()}:3306"

    def _workload_reset(self) -> StatusBase:
        """Reset an errored workload.

        Purge all files and re-initialise the workload.

        Returns:
            A `StatusBase` to be set by the caller
        """
        try:
            primary_address = self._get_primary_address_from_peers()
            if not primary_address:
                logger.debug("Primary not defined on peers. skipping workload reset")
                return WaitingStatus("waiting for update status")
            service_stop(SERVICE_NAME)
            self._mysql.reset_data_dir()
            self._mysql.reconfigure_mysqld()
            self._workload_initialise()
            unit_label = self.unit.name.replace("/", "-")
            # On a full reset, member must firstly be removed from cluster metadata
            self._mysql.remove_obsoletes_instance(from_instance=primary_address)
            # Re-add the member as if it's the first time
            self._mysql.add_instance_to_cluster(
                self._mysql.instance_address, unit_label, from_instance=primary_address
            )
        except MySQLReconfigureError:
            return BlockedStatus("Failed to re-initialize MySQL data-dir")
        except MySQLConfigureMySQLUsersError:
            return BlockedStatus("Failed to re-initialize MySQL users")
        except MySQLConfigureInstanceError:
            return BlockedStatus("Failed to re-configure instance for InnoDB")
        except MySQLDataPurgeError:
            return BlockedStatus("Failed to purge data dir")

        return ActiveStatus(self.active_status_message)

    def _get_primary_address_from_peers(self) -> str:
        """Retrieve primary address based on peer data."""
        for unit in self.peers.units:
            if self.peers.data[unit]["member-role"] == "primary":
                return self.peers.data[unit]["instance-hostname"]

    def _restart(self, _) -> None:
        """Restart server rolling ops callback function.

        Hold execution until server is back in the cluster.
        Used exclusively for rolling restarts.
        """
        logger.debug("Restarting mysqld daemon")
        if service_restart(SERVICE_NAME):

            # when restart done right after cluster creation (e.g bundles)
            # or for single unit deployments, it's necessary reboot the
            # cluster from outage to restore unit as primary
            if self.app_peer_data["units-added-to-cluster"] == "1":
                try:
                    self._mysql.reboot_from_complete_outage()
                except MySQLRebootFromCompleteOutageError:
                    logger.error("Failed to restart single node cluster")
                    self.unit.status = BlockedStatus("Failed to restart primary")
                    return

            unit_label = self.unit.name.replace("/", "-")

            try:
                for attempt in Retrying(stop=stop_after_attempt(24), wait=wait_fixed(5)):
                    with attempt:
                        if self._mysql.is_instance_in_cluster(unit_label):
                            self.unit.status = ActiveStatus(self.active_status_message)
                            return
                        raise Exception
            except RetryError:
                logger.error("Unable to rejoin mysqld instance to the cluster.")
                self.unit.status = BlockedStatus("Restarted node unable to rejoin the cluster")
        else:
            logger.error("Failed to restart mysqld on rolling restart")
            self.unit.status = BlockedStatus("Failed to restart mysqld")


if __name__ == "__main__":
    main(MySQLOperatorCharm)
