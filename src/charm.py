#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charmed Machine Operator for MySQL."""

import logging
import subprocess
from typing import Dict, Optional

from charms.data_platform_libs.v0.s3 import S3Requirer
from charms.grafana_agent.v0.cos_agent import COSAgentProvider
from charms.mysql.v0.backups import MySQLBackups
from charms.mysql.v0.mysql import (
    MySQLAddInstanceToClusterError,
    MySQLConfigureInstanceError,
    MySQLConfigureMySQLUsersError,
    MySQLCreateClusterError,
    MySQLCreateClusterSetError,
    MySQLGetClusterPrimaryAddressError,
    MySQLGetMemberStateError,
    MySQLGetMySQLVersionError,
    MySQLInitializeJujuOperationsTableError,
    MySQLLockAcquisitionError,
    MySQLRebootFromCompleteOutageError,
    MySQLRescanClusterError,
)
from charms.mysql.v0.tls import MySQLTLS
from ops.charm import (
    ActionEvent,
    CharmBase,
    InstallEvent,
    RelationChangedEvent,
    StartEvent,
)
from ops.main import main
from ops.model import (
    ActiveStatus,
    BlockedStatus,
    MaintenanceStatus,
    StatusBase,
    Unit,
    WaitingStatus,
)
from tenacity import RetryError, Retrying, stop_after_delay, wait_exponential

from constants import (
    BACKUPS_PASSWORD_KEY,
    BACKUPS_USERNAME,
    CHARMED_MYSQL_SNAP_NAME,
    CHARMED_MYSQLD_SERVICE,
    CLUSTER_ADMIN_PASSWORD_KEY,
    CLUSTER_ADMIN_USERNAME,
    GR_MAX_MEMBERS,
    MONITORING_PASSWORD_KEY,
    MONITORING_USERNAME,
    MYSQL_EXPORTER_PORT,
    PASSWORD_LENGTH,
    PEER,
    REQUIRED_USERNAMES,
    ROOT_PASSWORD_KEY,
    ROOT_USERNAME,
    S3_INTEGRATOR_RELATION_NAME,
    SERVER_CONFIG_PASSWORD_KEY,
    SERVER_CONFIG_USERNAME,
)
from hostname_resolution import MySQLMachineHostnameResolution
from mysql_vm_helpers import (
    MySQL,
    MySQLCreateCustomMySQLDConfigError,
    MySQLDataPurgeError,
    MySQLExporterConnectError,
    MySQLReconfigureError,
    MySQLResetRootPasswordAndStartMySQLDError,
    SnapServiceOperationError,
    instance_hostname,
    is_volume_mounted,
    reboot_system,
    snap_service_operation,
)
from relations.db_router import DBRouterRelation
from relations.mysql import MySQLRelation
from relations.mysql_provider import MySQLProvider
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

        self.framework.observe(self.on[PEER].relation_changed, self._on_peer_relation_changed)
        self.framework.observe(self.on.get_cluster_status_action, self._get_cluster_status)
        self.framework.observe(self.on.get_password_action, self._on_get_password)
        self.framework.observe(self.on.set_password_action, self._on_set_password)

        self.shared_db_relation = SharedDBRelation(self)
        self.db_router_relation = DBRouterRelation(self)
        self.database_relation = MySQLProvider(self)
        self.mysql_relation = MySQLRelation(self)
        self.tls = MySQLTLS(self)
        self._grafana_agent = COSAgentProvider(
            self,
            metrics_endpoints=[
                {"path": "/metrics", "port": MYSQL_EXPORTER_PORT},
            ],
            metrics_rules_dir="./src/alert_rules/prometheus",
            logs_rules_dir="./src/alert_rules/loki",
            log_slots=[f"{CHARMED_MYSQL_SNAP_NAME}:logs"],
        )
        self.s3_integrator = S3Requirer(self, S3_INTEGRATOR_RELATION_NAME)
        self.backups = MySQLBackups(self, self.s3_integrator)
        self.hostname_resolution = MySQLMachineHostnameResolution(self)

    # =======================
    #  Charm Lifecycle Hooks
    # =======================

    def _on_install(self, event: InstallEvent) -> None:
        """Handle the install event."""
        self.unit.status = MaintenanceStatus("Installing MySQL")

        if not is_volume_mounted():
            self._reboot_on_detached_storage(event)
            return

        # Initial setup operations like installing dependencies, and creating users and groups.
        def set_retry_status(_):
            self.unit.status = MaintenanceStatus(
                "Failed to install and configure MySQL. Retrying..."
            )

        try:
            for attempt in Retrying(
                wait=wait_exponential(multiplier=10),
                stop=stop_after_delay(60 * 5),
                after=set_retry_status,
            ):
                with attempt:
                    MySQL.install_and_configure_mysql_dependencies()
        except RetryError:
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
            MONITORING_PASSWORD_KEY,
            BACKUPS_PASSWORD_KEY,
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

        # Create and set cluster and cluster-set names in the peer relation databag
        common_hash = generate_random_hash()
        self.app_peer_data.setdefault(
            "cluster-name", self.config.get("cluster-name", f"cluster-{common_hash}")
        )
        self.app_peer_data.setdefault("cluster-set-domain-name", f"cluster-set-{common_hash}")

    def _on_start(self, event: StartEvent) -> None:
        """Handle the start event.

        Configure MySQL users and the instance for use in an InnoDB cluster.
        """
        if not self._can_start(event):
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
        except MySQLCreateCustomMySQLDConfigError:
            self.unit.status = BlockedStatus("Failed to create custom mysqld config")
            return
        except MySQLExporterConnectError:
            self.unit.status = BlockedStatus("Failed to connect to MySQL exporter")
            return
        except MySQLGetMySQLVersionError:
            logger.debug("Fail to get MySQL version")

        if not self.unit.is_leader():
            # Wait to be joined and set flags
            self.unit.status = WaitingStatus("Waiting to join the cluster")
            self.unit_peer_data["member-role"] = "secondary"
            self.unit_peer_data["member-state"] = "waiting"
            return

        try:
            # Create the cluster and cluster set from the leader unit
            self._create_cluster()
            self._create_cluter_set()
            self.unit.status = ActiveStatus(self.active_status_message)
        except (
            MySQLCreateClusterError,
            MySQLCreateClusterSetError,
            MySQLInitializeJujuOperationsTableError,
        ) as e:
            logger.exception("Failed to create cluster")
            raise e

    def _on_peer_relation_changed(self, event: RelationChangedEvent) -> None:
        """Handle the peer relation changed event."""
        # Only execute if peer relation data contains cluster config values
        if not self._is_peer_data_set:
            event.defer()
            return

        if self._is_unit_waiting_to_join_cluster():
            self._join_unit_to_cluster()
            for port in ["3306", "33060"]:
                try:
                    subprocess.check_call(["open-port", f"{port}/tcp"])
                except subprocess.CalledProcessError:
                    logger.exception(f"failed to open port {port}")

    def _on_database_storage_detaching(self, _) -> None:
        """Handle the database storage detaching event."""
        # Only executes if the unit was initialised
        if not self.unit_peer_data.get("unit-initialized"):
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

    def _handle_non_online_instance_status(self, state) -> None:
        """Helper method to handle non-online instance statuses.

        Invoked from the update status event handler.
        """
        if state == "recovering":
            # server is in the process of becoming an active member
            logger.info("Instance is being recovered")
            return

        if state == "offline":
            # Group Replication is active but the member does not belong to any group
            all_states = {
                self.peers.data[unit].get("member-state", "unknown") for unit in self.peers.units
            }
            all_states.add("offline")

            if all_states == {"offline"} and self.unit.is_leader():
                # All instance are off or its a single unit cluster
                # reboot cluster from outage from the leader unit
                logger.debug("Attempting reboot from complete outage.")
                try:
                    # reboot from outage forcing it when it a single unit
                    self._mysql.reboot_from_complete_outage()
                except MySQLRebootFromCompleteOutageError:
                    logger.error("Failed to reboot cluster from complete outage.")
                    self.unit.status = BlockedStatus("failed to recover cluster.")
            primary = self._get_primary_from_online_peer()
            if (
                primary
                and self._mysql.get_cluster_node_count(from_instance=primary) == GR_MAX_MEMBERS
            ):
                # Reset variables to allow unit join the cluster
                self.unit_peer_data["member-state"] = "waiting"
                del self.unit_peer_data["unit-initialized"]

        if state == "unreachable":
            try:
                if not snap_service_operation(
                    CHARMED_MYSQL_SNAP_NAME, CHARMED_MYSQLD_SERVICE, "restart"
                ):
                    # mysqld access not possible and daemon restart fails
                    # force reset necessary
                    self.unit.status = MaintenanceStatus("Workload reset")
                    self.unit.status = self._workload_reset()
            except SnapServiceOperationError as e:
                self.unit.status = BlockedStatus(e.message)

    def _on_update_status(self, _) -> None:
        """Handle update status.

        Takes care of workload health checks.
        """
        if (
            not self.cluster_initialized
            or not self.unit_peer_data.get("member-role")
            or not is_volume_mounted()
        ):
            # health checks only after cluster and member are initialised
            return
        if (
            self.unit_peer_data.get("member-state") == "waiting"
            and not self.unit_peer_data.get("unit-configured")
            and not self.unit_peer_data.get("unit-initialized")
            and not self.unit.is_leader()
        ):
            # avoid changing status while in initialisation
            return

        if self._is_unit_waiting_to_join_cluster():
            self._join_unit_to_cluster()
            return

        nodes = self._mysql.get_cluster_node_count()
        if nodes > 0 and self.unit.is_leader():
            self.app_peer_data["units-added-to-cluster"] = str(nodes)

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

        self._handle_non_online_instance_status(state)

        if self.unit.is_leader():
            try:
                primary_address = self._mysql.get_cluster_primary_address()
            except MySQLGetClusterPrimaryAddressError:
                self.unit.status = MaintenanceStatus("Unable to query cluster primary")
                return

            if not primary_address:
                self.unit.status = MaintenanceStatus("Unable to find cluster primary")
                return

            # Set active status when primary is known
            self.app.status = ActiveStatus()

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
            event.fail(
                f"The action can be run only for users used by the charm: {', '.join(REQUIRED_USERNAMES)} not {username}"
            )
            return

        if username == ROOT_USERNAME:
            secret_key = ROOT_PASSWORD_KEY
        elif username == SERVER_CONFIG_USERNAME:
            secret_key = SERVER_CONFIG_PASSWORD_KEY
        elif username == CLUSTER_ADMIN_USERNAME:
            secret_key = CLUSTER_ADMIN_PASSWORD_KEY
        elif username == MONITORING_USERNAME:
            secret_key = MONITORING_PASSWORD_KEY
        elif username == BACKUPS_USERNAME:
            secret_key = BACKUPS_PASSWORD_KEY
        else:
            raise RuntimeError("Invalid username.")

        event.set_results({"username": username, "password": self.get_secret("app", secret_key)})

    def _on_set_password(self, event: ActionEvent) -> None:
        """Action used to update/rotate the system user's password."""
        if not self.unit.is_leader():
            event.fail("set-password action can only be run on the leader unit.")
            return

        username = event.params.get("username") or ROOT_USERNAME

        if username not in REQUIRED_USERNAMES:
            event.fail(
                f"The action can be run only for users used by the charm: {', '.join(REQUIRED_USERNAMES)} not {username}"
            )
            return

        if username == ROOT_USERNAME:
            secret_key = ROOT_PASSWORD_KEY
        elif username == SERVER_CONFIG_USERNAME:
            secret_key = SERVER_CONFIG_PASSWORD_KEY
        elif username == CLUSTER_ADMIN_USERNAME:
            secret_key = CLUSTER_ADMIN_PASSWORD_KEY
        elif username == MONITORING_USERNAME:
            secret_key = MONITORING_PASSWORD_KEY
        elif username == BACKUPS_USERNAME:
            secret_key = BACKUPS_PASSWORD_KEY
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
            self._get_unit_ip(self.unit),
            self.app_peer_data["cluster-name"],
            self.app_peer_data["cluster-set-domain-name"],
            self.get_secret("app", ROOT_PASSWORD_KEY),
            SERVER_CONFIG_USERNAME,
            self.get_secret("app", SERVER_CONFIG_PASSWORD_KEY),
            CLUSTER_ADMIN_USERNAME,
            self.get_secret("app", CLUSTER_ADMIN_PASSWORD_KEY),
            MONITORING_USERNAME,
            self.get_secret("app", MONITORING_PASSWORD_KEY),
            BACKUPS_USERNAME,
            self.get_secret("app", BACKUPS_PASSWORD_KEY),
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

    @property
    def _has_blocked_status(self) -> bool:
        """Returns whether the unit is in a blocked state."""
        return isinstance(self.unit.status, BlockedStatus)

    @property
    def s3_integrator_relation_exists(self) -> bool:
        """Returns whether a relation with the s3 integrator exists."""
        return bool(self.model.get_relation(S3_INTEGRATOR_RELATION_NAME))

    def is_unit_busy(self) -> bool:
        """Returns whether the unit is in blocked state and should not run any operations."""
        return self.unit_peer_data.get("member-state") == "waiting"

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

    def get_unit_hostname(self, unit_name: Optional[str] = None) -> str:
        """Get the hostname of the unit."""
        if unit_name:
            unit = self.model.get_unit(unit_name)
            return self.peers.data[unit]["instance-hostname"].split(":")[0]
        return self.unit_peer_data["instance-hostname"].split(":")[0]

    @property
    def active_status_message(self) -> str:
        """Active status message."""
        if self.unit_peer_data.get("member-role") == "primary":
            return "Primary"
        return ""

    def _workload_initialise(self) -> None:
        """Workload initialisation commands.

        Create users and configuration to setup instance as an Group Replication node.
        Raised errors must be treated on handlers.
        """
        self._mysql.create_custom_mysqld_config(profile=self.config["profile"])
        self._mysql.reset_root_password_and_start_mysqld()
        self._mysql.configure_mysql_users()
        self._mysql.configure_instance()
        self._mysql.wait_until_mysql_connection()
        self._mysql.connect_mysql_exporter()
        self.unit_peer_data["unit-configured"] = "True"
        self.unit_peer_data["instance-hostname"] = f"{instance_hostname()}:3306"
        if workload_version := self._mysql.get_mysql_version():
            self.unit.set_workload_version(workload_version)

    def _get_unit_ip(self, unit: Unit) -> Optional[str]:
        """Get the IP address of a specific unit."""
        if unit == self.unit:
            return str(self.model.get_binding(PEER).network.bind_address)

        return str(self.peers.data[unit].get("private-address"))

    def _create_cluster(self) -> None:
        """Create cluster commands.

        Create a cluster from the current unit and initialise operations database.
        """
        unit_label = self.unit.name.replace("/", "-")
        self._mysql.create_cluster(unit_label)
        self._mysql.initialize_juju_units_operations_table()

        self.app_peer_data["units-added-to-cluster"] = "1"
        self.unit_peer_data["unit-initialized"] = "True"
        self.unit_peer_data["member-role"] = "primary"
        self.unit_peer_data["member-state"] = "online"

        try:
            subprocess.check_call(["open-port", "3306/tcp"])
            subprocess.check_call(["open-port", "33060/tcp"])
        except subprocess.CalledProcessError:
            logger.exception("failed to open port")

    def _create_cluter_set(self) -> None:
        """Create cluster set from initialized cluster."""
        self._mysql.create_cluster_set()

    def _can_start(self, event: StartEvent) -> bool:
        """Check if the unit can start.

        Args:
            event: StartEvent
        """
        # Safeguard unit starting before leader unit sets peer data
        if not self._is_peer_data_set:
            event.defer()
            return False

        # Safeguard against error on install hook
        if self._has_blocked_status:
            return False

        # Safeguard against storage not attached
        if not is_volume_mounted():
            self._reboot_on_detached_storage(event)
            return False

        # Safeguard if receiving on start after unit initialization
        if self.unit_peer_data.get("unit-initialized") == "True":
            logger.debug("Delegate status update for start handler on initialized unit.")
            self._on_update_status(None)
            return False

        return True

    def _workload_reset(self) -> StatusBase:
        """Reset an errored workload.

        Purge all files and re-initialise the workload.

        Returns:
            A `StatusBase` to be set by the caller
        """
        try:
            primary_address = self._get_primary_address_from_peers()
            if not primary_address:
                logger.debug("Primary not yet defined on peers. Waiting new primary.")
                return MaintenanceStatus("Workload reset: waiting new primary")

            snap_service_operation(CHARMED_MYSQL_SNAP_NAME, CHARMED_MYSQLD_SERVICE, "stop")
            self._mysql.reset_data_dir()
            self._mysql.reconfigure_mysqld()
            self._workload_initialise()

            # On a full reset, member must firstly be removed from cluster metadata
            self._mysql.rescan_cluster(from_instance=primary_address, remove_instances=True)
            # Re-add the member as if it's the first time

            unit_label = self.unit.name.replace("/", "-")
            self._mysql.add_instance_to_cluster(
                self._get_unit_ip(self.unit), unit_label, from_instance=primary_address
            )
        except MySQLReconfigureError:
            return MaintenanceStatus("Failed to re-initialize MySQL data-dir")
        except MySQLConfigureMySQLUsersError:
            return MaintenanceStatus("Failed to re-initialize MySQL users")
        except MySQLConfigureInstanceError:
            return MaintenanceStatus("Failed to re-configure instance for InnoDB")
        except MySQLDataPurgeError:
            return MaintenanceStatus("Failed to purge data dir")
        except MySQLResetRootPasswordAndStartMySQLDError:
            return MaintenanceStatus("Failed to reset root password")
        except MySQLCreateCustomMySQLDConfigError:
            return MaintenanceStatus("Failed to create custom mysqld config")
        except MySQLRescanClusterError:
            return MaintenanceStatus("Failed to rescan cluster and remove obsolete instances")
        except SnapServiceOperationError as e:
            return MaintenanceStatus(e.message)

        return ActiveStatus(self.active_status_message)

    def _reboot_on_detached_storage(self, event) -> None:
        """Reboot on detached storage.

        Workaround for lxd containers not getting storage attached on startups.

        Args:
            event: the event that triggered this handler
        """
        event.defer()
        logger.error("Data directory not attached. Reboot unit.")
        self.unit.status = WaitingStatus("Data directory not attached")
        reboot_system()

    def _is_unit_waiting_to_join_cluster(self) -> bool:
        """Return if the unit is waiting to join the cluster."""
        # alternatively, we could check if the instance is configured
        # and have an empty performance_schema.replication_group_members table
        return (
            self.unit_peer_data.get("member-state") == "waiting"
            and self.unit_peer_data.get("unit-configured") == "True"
            and not self.unit_peer_data.get("unit-initialized")
        )

    def _get_primary_from_online_peer(self) -> Optional[str]:
        """Get the primary address from an online peer."""
        for unit in self.peers.units:
            if self.peers.data[unit].get("member-state") == "online":
                try:
                    return self._mysql.get_cluster_primary_address(
                        connect_instance_address=self._get_unit_ip(unit)
                    )
                except MySQLGetClusterPrimaryAddressError:
                    # try next unit
                    continue

    def _join_unit_to_cluster(self) -> None:
        """Join the unit to the cluster.

        Try to join the unit from the primary unit.
        """
        instance_label = self.unit.name.replace("/", "-")
        instance_address = self._get_unit_ip(self.unit)

        if self._mysql.is_instance_in_cluster(instance_label):
            logger.debug("instance already in cluster")
            self.unit_peer_data["unit-initialized"] = "True"
            return

        # Add new instance to the cluster
        try:
            cluster_primary = self._get_primary_from_online_peer()
            if not cluster_primary:
                self.unit.status = WaitingStatus("waiting to get cluster primary from peers")
                logger.debug("waiting: unable to retrieve the cluster primary from online peer")
                return

            if self._mysql.get_cluster_node_count(from_instance=cluster_primary) == GR_MAX_MEMBERS:
                self.unit.status = BlockedStatus(
                    f"Cluster reached max size of {GR_MAX_MEMBERS} units. Standby."
                )
                logger.info(
                    f"Cluster reached max size of {GR_MAX_MEMBERS} units. This unit will stay as standby."
                )
                return

            if self._mysql.are_locks_acquired(from_instance=cluster_primary):
                self.unit.status = WaitingStatus("waiting to join in queue.")
                logger.debug("waiting: cluster locks are acquired")
                return

            self.unit.status = MaintenanceStatus("joining the cluster")

            # Add the instance to the cluster. This operation uses locks to ensure that
            # only one instance is added to the cluster at a time
            # (so only one instance is involved in a state transfer at a time)
            self._mysql.add_instance_to_cluster(
                instance_address, instance_label, from_instance=cluster_primary
            )
            logger.debug(f"Added instance {instance_address} to cluster")

            # Update 'units-added-to-cluster' counter in the peer relation databag
            self.unit_peer_data["unit-initialized"] = "True"
            self.unit_peer_data["member-state"] = "online"
            self.unit.status = ActiveStatus(self.active_status_message)
            logger.debug(f"Instance {instance_label} is cluster member")

        except MySQLAddInstanceToClusterError:
            logger.debug(f"Unable to add instance {instance_address} to cluster.")
        except MySQLLockAcquisitionError:
            self.unit.status = WaitingStatus("waiting to join the cluster")
            logger.debug("Waiting to joing the cluster, failed to acquire lock.")


if __name__ == "__main__":
    main(MySQLOperatorCharm)
