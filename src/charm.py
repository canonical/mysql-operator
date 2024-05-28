#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charmed Machine Operator for MySQL."""

import logging
import random
import socket
import subprocess
from time import sleep
from typing import Optional

import ops
from charms.data_platform_libs.v0.data_models import TypedCharmBase
from charms.data_platform_libs.v0.s3 import S3Requirer
from charms.grafana_agent.v0.cos_agent import COSAgentProvider
from charms.mysql.v0.async_replication import (
    MySQLAsyncReplicationPrimary,
    MySQLAsyncReplicationReplica,
)
from charms.mysql.v0.backups import MySQLBackups
from charms.mysql.v0.mysql import (
    BYTES_1MB,
    Error,
    MySQLAddInstanceToClusterError,
    MySQLCharmBase,
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
    MySQLSetClusterPrimaryError,
)
from charms.mysql.v0.tls import MySQLTLS
from charms.rolling_ops.v0.rollingops import RollingOpsManager
from charms.tempo_k8s.v1.charm_tracing import trace_charm
from charms.tempo_k8s.v2.tracing import TracingEndpointRequirer
from ops import (
    ActiveStatus,
    BlockedStatus,
    EventBase,
    InstallEvent,
    MaintenanceStatus,
    RelationBrokenEvent,
    RelationChangedEvent,
    RelationCreatedEvent,
    StartEvent,
    Unit,
    WaitingStatus,
)
from ops.main import main
from tenacity import (
    RetryError,
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    stop_after_delay,
    wait_exponential,
    wait_fixed,
)

from config import CharmConfig, MySQLConfig
from constants import (
    BACKUPS_PASSWORD_KEY,
    BACKUPS_USERNAME,
    CHARMED_MYSQL_COMMON_DIRECTORY,
    CHARMED_MYSQL_SNAP_NAME,
    CHARMED_MYSQLD_SERVICE,
    CLUSTER_ADMIN_PASSWORD_KEY,
    CLUSTER_ADMIN_USERNAME,
    COS_AGENT_RELATION_NAME,
    GR_MAX_MEMBERS,
    MONITORING_PASSWORD_KEY,
    MONITORING_USERNAME,
    MYSQL_EXPORTER_PORT,
    MYSQLD_CUSTOM_CONFIG_FILE,
    PASSWORD_LENGTH,
    PEER,
    ROOT_PASSWORD_KEY,
    S3_INTEGRATOR_RELATION_NAME,
    SERVER_CONFIG_PASSWORD_KEY,
    SERVER_CONFIG_USERNAME,
    TRACING_RELATION_NAME,
)
from flush_mysql_logs import FlushMySQLLogsCharmEvents, MySQLLogs
from hostname_resolution import MySQLMachineHostnameResolution
from mysql_vm_helpers import (
    MySQL,
    MySQLCreateCustomMySQLDConfigError,
    MySQLInstallError,
    SnapServiceOperationError,
    instance_hostname,
    is_volume_mounted,
    snap,
    snap_service_operation,
)
from relations.db_router import DBRouterRelation
from relations.mysql import MySQLRelation
from relations.mysql_provider import MySQLProvider
from relations.shared_db import SharedDBRelation
from upgrade import MySQLVMUpgrade, get_mysql_dependencies_model
from utils import compare_dictionaries, generate_random_password

logger = logging.getLogger(__name__)


class MySQLDNotRestartedError(Error):
    """Exception raised when MySQLD is not restarted after configuring instance."""


@trace_charm(
    tracing_endpoint="tracing_endpoint",
    extra_types=(
        MySQL,
        MySQLConfig,
        SharedDBRelation,
        DBRouterRelation,
        MySQLProvider,
        MySQLRelation,
        MySQLTLS,
        COSAgentProvider,
        S3Requirer,
        MySQLBackups,
        MySQLMachineHostnameResolution,
        MySQLVMUpgrade,
        RollingOpsManager,
        MySQLLogs,
        MySQLAsyncReplicationPrimary,
        MySQLAsyncReplicationReplica,
    ),
)
class MySQLOperatorCharm(MySQLCharmBase, TypedCharmBase[CharmConfig]):
    """Operator framework charm for MySQL."""

    config_type = CharmConfig
    # FlushMySQLLogsCharmEvents needs to be defined on the charm object for logrotate
    # (which runs juju-run/juju-exec to dispatch a custom event from cron)
    on = FlushMySQLLogsCharmEvents()  # pyright: ignore [reportAssignmentType]

    def __init__(self, *args):
        super().__init__(*args)

        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.leader_elected, self._on_leader_elected)
        self.framework.observe(self.on.leader_settings_changed, self._on_leader_settings_changed)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.start, self._on_start)
        self.framework.observe(self.on.update_status, self._on_update_status)
        self.framework.observe(
            self.on.database_storage_detaching, self._on_database_storage_detaching
        )

        self.framework.observe(self.on[PEER].relation_changed, self._on_peer_relation_changed)

        self.mysql_config = MySQLConfig(MYSQLD_CUSTOM_CONFIG_FILE)
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
        self.framework.observe(
            self.on[COS_AGENT_RELATION_NAME].relation_created, self._on_cos_agent_relation_created
        )
        self.framework.observe(
            self.on[COS_AGENT_RELATION_NAME].relation_broken, self._on_cos_agent_relation_broken
        )
        self.s3_integrator = S3Requirer(self, S3_INTEGRATOR_RELATION_NAME)
        self.backups = MySQLBackups(self, self.s3_integrator)
        self.hostname_resolution = MySQLMachineHostnameResolution(self)
        self.upgrade = MySQLVMUpgrade(
            self,
            dependency_model=get_mysql_dependencies_model(),
            relation_name="upgrade",
            substrate="vm",
        )

        self.restart = RollingOpsManager(self, relation="restart", callback=self._restart)

        self.mysql_logs = MySQLLogs(self)
        self.async_primary = MySQLAsyncReplicationPrimary(self)
        self.async_replica = MySQLAsyncReplicationReplica(self)

        self.tracing = TracingEndpointRequirer(self, relation_name=TRACING_RELATION_NAME)

    # =======================
    #  Charm Lifecycle Hooks
    # =======================

    def _on_install(self, event: InstallEvent) -> None:
        """Handle the install event."""
        self.unit.status = MaintenanceStatus("Installing MySQL")

        if not is_volume_mounted():
            # persistent data directory not mounted, reboot unit
            logger.warning("Data directory not attached. Will reboot unit.")
            self.unit.status = WaitingStatus("Data directory not attached. Rebooting...")
            # immediate reboot will make juju re-run the hook
            self.unit.reboot(now=True)

        if self.install_workload():
            cache = snap.SnapCache()
            mysql_snap = cache[CHARMED_MYSQL_SNAP_NAME]
            mysql_snap.alias("mysql")
            mysql_snap.alias("mysqlrouter")
            mysql_snap.alias("mysqlsh")
            mysql_snap.alias("xbcloud")
            mysql_snap.alias("xbstream")
            mysql_snap.alias("xtrabackup")
            self.unit.status = WaitingStatus("Waiting to start MySQL")
        else:
            self.unit.status = BlockedStatus("Failed to install and configure MySQL")

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
        self.unit_peer_data.update({"leader": "true"})

        # Create and set cluster and cluster-set names in the peer relation databag
        common_hash = self.generate_random_hash()
        self.app_peer_data.setdefault(
            "cluster-name", self.config.cluster_name or f"cluster-{common_hash}"
        )
        self.app_peer_data.setdefault(
            "cluster-set-domain-name", self.config.cluster_set_name or f"cluster-set-{common_hash}"
        )

    def _on_leader_settings_changed(self, _) -> None:
        """Handle the leader settings changed event."""
        self.unit_peer_data.update({"leader": "false"})

    def _on_config_changed(self, event: EventBase) -> None:
        """Handle the config changed event."""
        if not self._is_peer_data_set:
            # skip when not initialized
            return

        if not self.upgrade.idle:
            # skip when upgrade is in progress
            # the upgrade already restart the daemon
            return

        # restart not required if mysqld is not running
        restart = self._mysql.is_mysqld_running()

        previous_config = self.mysql_config.custom_config
        if not previous_config:
            # empty config means not initialized, skipping
            return

        # render the new config
        memory_limit_bytes = (self.config.profile_limit_memory or 0) * BYTES_1MB
        new_config_content, new_config_dict = self._mysql.render_mysqld_configuration(
            profile=self.config.profile,
            snap_common=CHARMED_MYSQL_COMMON_DIRECTORY,
            memory_limit=memory_limit_bytes,
        )

        changed_config = compare_dictionaries(previous_config, new_config_dict)

        if self.mysql_config.keys_requires_restart(changed_config):
            # there are static configurations in changed keys
            logger.info("Persisting configuration changes to file")
            # persist config to file
            self._mysql.write_content_to_file(
                path=MYSQLD_CUSTOM_CONFIG_FILE, content=new_config_content
            )
            if restart:
                logger.info("Configuration change requires restart")
                self.on[f"{self.restart.name}"].acquire_lock.emit()
                return

        if dynamic_config := self.mysql_config.filter_static_keys(changed_config):
            # if only dynamic config changed, apply it
            logger.info("Configuration does not requires restart")
            for config in dynamic_config:
                self._mysql.set_dynamic_variable(config, new_config_dict[config])

    def _on_start(self, event: StartEvent) -> None:
        """Handle the start event.

        Configure MySQL users and the instance for use in an InnoDB cluster.
        """
        if not self._can_start(event):
            return

        self.unit.status = MaintenanceStatus("Setting up cluster node")

        try:
            self.workload_initialise()
        except MySQLConfigureMySQLUsersError:
            self.unit.status = BlockedStatus("Failed to initialize MySQL users")
            return
        except MySQLConfigureInstanceError:
            self.unit.status = BlockedStatus("Failed to configure instance for InnoDB")
            return
        except MySQLCreateCustomMySQLDConfigError:
            self.unit.status = BlockedStatus("Failed to create custom mysqld config")
            return
        except MySQLDNotRestartedError:
            self.unit.status = BlockedStatus("Failed to restart mysqld after configuring instance")
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
            logger.info(f"Creating cluster {self.app_peer_data['cluster-name']}")
            self.create_cluster()
            self._open_ports()
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
            self.join_unit_to_cluster()
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

        # No need to remove the instance from the cluster if it is not a member of the cluster
        if not self._mysql.is_instance_in_cluster(self.unit_label):
            return

        def _get_leader_unit() -> Optional[Unit]:
            """Get the leader unit."""
            for unit in self.peers.units:
                if self.peers.data[unit]["leader"] == "true":
                    return unit

        if self._mysql.get_primary_label() == self.unit_label and not self.unit.is_leader():
            # Preemptively switch primary to unit leader
            logger.info("Switching primary to the leader unit")
            if leader_unit := _get_leader_unit():
                try:
                    self._mysql.set_cluster_primary(
                        new_primary_address=self.get_unit_ip(leader_unit)
                    )
                except MySQLSetClusterPrimaryError:
                    logger.warning("Failed to switch primary to leader unit")

        # If instance is part of a replica cluster, locks are managed by the
        # the primary cluster primary (i.e. cluster set global primary)
        lock_instance = None
        if self._mysql.is_cluster_replica():
            lock_instance = self._mysql.get_cluster_set_global_primary_address()

        # The following operation uses locks to ensure that only one instance is removed
        # from the cluster at a time (to avoid split-brain or lack of majority issues)
        self._mysql.remove_instance(self.unit_label, lock_instance=lock_instance)

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

        if state == "unreachable":
            try:
                if not snap_service_operation(
                    CHARMED_MYSQL_SNAP_NAME, CHARMED_MYSQLD_SERVICE, "restart"
                ):
                    # mysqld access not possible and daemon restart fails
                    # force reset necessary
                    self.unit.status = BlockedStatus("Unable to recover from an unreachable state")
            except SnapServiceOperationError as e:
                self.unit.status = BlockedStatus(e.message)

    def _on_update_status(self, _) -> None:  # noqa: C901
        """Handle update status.

        Takes care of workload health checks.
        """
        if (
            not self.cluster_initialized
            or not self.unit_peer_data.get("member-role")
            or not is_volume_mounted()
        ):
            # health checks only after cluster and member are initialised
            logger.debug("skip status update when not initialized")
            return
        if (
            self.unit_peer_data.get("member-state") == "waiting"
            and not self.unit_peer_data.get("unit-configured")
            and not self.unit_peer_data.get("unit-initialized")
            and not self.unit.is_leader()
        ):
            # avoid changing status while in initialising
            logger.debug("skip status update while initialising")
            return

        if not self.upgrade.idle:
            # avoid changing status while in upgrade
            logger.debug("skip status update while upgrading")
            return

        if not (self.async_primary.idle and self.async_replica.idle):
            # avoid changing status while in async replication
            logger.debug("skip status update while setting up async replication")
            return

        # unset restart control flag
        del self.restart_peers.data[self.unit]["state"]

        if self._is_unit_waiting_to_join_cluster():
            self.join_unit_to_cluster()
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

        self._handle_non_online_instance_status(state)

        if self.unit.is_leader():
            nodes = self._mysql.get_cluster_node_count()
            if nodes > 0:
                self.app_peer_data["units-added-to-cluster"] = str(nodes)
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

    def _on_cos_agent_relation_created(self, event: RelationCreatedEvent) -> None:
        """Handle the cos_agent relation created event.

        Enable the mysqld-exporter snap service.
        """
        if not self._is_peer_data_set:
            logger.debug("Charm not yet set up. Deferring")
            event.defer()
            return

        self._mysql.connect_mysql_exporter()

    def _on_cos_agent_relation_broken(self, event: RelationBrokenEvent) -> None:
        """Handle the cos_agent relation broken event.

        Disable the mysqld-exporter snap service.
        """
        if not self._is_peer_data_set:
            return

        self._mysql.stop_mysql_exporter()

    # =======================
    #  Helpers
    # =======================

    @property
    def tracing_endpoint(self) -> Optional[str]:
        """Otlp http endpoint for charm instrumentation."""
        if self.tracing.is_ready():
            return self.tracing.otlp_http_endpoint()
        return None

    @property
    def _mysql(self):
        """Returns an instance of the MySQL object."""
        return MySQL(
            self.unit_fqdn,
            self.app_peer_data["cluster-name"],
            self.app_peer_data["cluster-set-domain-name"],
            self.get_secret("app", ROOT_PASSWORD_KEY),  # pyright: ignore [reportArgumentType]
            SERVER_CONFIG_USERNAME,
            self.get_secret(
                "app", SERVER_CONFIG_PASSWORD_KEY
            ),  # pyright: ignore [reportArgumentType]
            CLUSTER_ADMIN_USERNAME,
            self.get_secret(
                "app", CLUSTER_ADMIN_PASSWORD_KEY
            ),  # pyright: ignore [reportArgumentType]
            MONITORING_USERNAME,
            self.get_secret(
                "app", MONITORING_PASSWORD_KEY
            ),  # pyright: ignore [reportArgumentType]
            BACKUPS_USERNAME,
            self.get_secret("app", BACKUPS_PASSWORD_KEY),  # pyright: ignore [reportArgumentType]
            self,
        )

    @property
    def _has_blocked_status(self) -> bool:
        """Returns whether the unit is in a blocked state."""
        return isinstance(self.unit.status, BlockedStatus)

    @property
    def s3_integrator_relation_exists(self) -> bool:
        """Returns whether a relation with the s3 integrator exists."""
        return bool(self.model.get_relation(S3_INTEGRATOR_RELATION_NAME))

    @property
    def unit_fqdn(self) -> str:
        """Returns the unit's FQDN."""
        return socket.getfqdn()

    @property
    def restart_peers(self) -> Optional[ops.model.Relation]:
        """Retrieve the peer relation."""
        return self.model.get_relation("restart")

    def is_unit_busy(self) -> bool:
        """Returns whether the unit is in blocked state and should not run any operations."""
        return self.unit_peer_data.get("member-state") == "waiting"

    def get_unit_hostname(self, unit_name: Optional[str] = None) -> str:
        """Get the hostname of the unit."""
        if unit_name:
            unit = self.model.get_unit(unit_name)
            return self.peers.data[unit]["instance-hostname"].split(":")[0]
        return self.unit_peer_data["instance-hostname"].split(":")[0]

    @property
    def unit_address(self) -> str:
        """Returns the unit's address."""
        return self.get_unit_ip(self.unit)

    def install_workload(self) -> bool:
        """Exponential backoff retry to install and configure MySQL.

        Returns: True if successful, False otherwise.
        """

        def set_retry_status(_):
            self.unit.status = MaintenanceStatus(
                "Failed to install and configure MySQL. Retrying..."
            )

        try:
            for attempt in Retrying(
                wait=wait_exponential(multiplier=10),
                stop=stop_after_delay(60 * 5),
                retry=retry_if_exception_type(snap.SnapError),
                after=set_retry_status,
            ):
                with attempt:
                    MySQL.install_and_configure_mysql_dependencies()
        except (RetryError, MySQLInstallError):
            return False
        return True

    def workload_initialise(self) -> None:
        """Workload initialisation commands.

        Create users and configuration to setup instance as an Group Replication node.
        Raised errors must be treated on handlers.
        """
        self._mysql.write_mysqld_config(
            profile=self.config.profile, memory_limit=self.config.profile_limit_memory
        )
        self._mysql.setup_logrotate_and_cron()
        self._mysql.reset_root_password_and_start_mysqld()
        self._mysql.configure_mysql_users()

        # ensure hostname can be resolved
        self.hostname_resolution.update_etc_hosts(None)

        current_mysqld_pid = self._mysql.get_pid_of_port_3306()
        self._mysql.configure_instance()

        for attempt in Retrying(wait=wait_fixed(30), stop=stop_after_attempt(20), reraise=True):
            with attempt:
                new_mysqld_pid = self._mysql.get_pid_of_port_3306()
                if not new_mysqld_pid:
                    raise MySQLDNotRestartedError("mysqld process not yet up after restart")

                if current_mysqld_pid == new_mysqld_pid:
                    raise MySQLDNotRestartedError("mysqld not yet shutdown")

        self._mysql.wait_until_mysql_connection()

        self.unit_peer_data["unit-configured"] = "True"
        self.unit_peer_data["instance-hostname"] = f"{instance_hostname()}:3306"
        if workload_version := self._mysql.get_mysql_version():
            self.unit.set_workload_version(workload_version)

    def get_unit_ip(self, unit: Unit) -> str:
        """Get the IP address of a specific unit."""
        if unit == self.unit:
            return str(self.model.get_binding(PEER).network.bind_address)

        return str(self.peers.data[unit].get("private-address"))

    def _open_ports(self) -> None:
        """Open ports.

        Used if `juju expose` ran on application
        """
        try:
            self.unit.set_ports(3306, 33060)
        except ops.ModelError:
            logger.exception("failed to open port")

    def _can_start(self, event: StartEvent) -> bool:
        """Check if the unit can start.

        Args:
            event: StartEvent
        """
        # Safeguard unit starting before leader unit sets peer data
        if not self._is_peer_data_set:
            logger.debug("Peer data not yet set. Deferring")
            event.defer()
            return False

        # Safeguard against starting while upgrading
        if not self.upgrade.idle:
            event.defer()
            return False

        # Safeguard against error on install hook
        if self._has_blocked_status:
            return False

        # Safeguard against storage not attached
        if not is_volume_mounted():
            logger.error("Data directory not attached. Will reboot unit.")
            self.unit.status = WaitingStatus("Data directory not attached. Rebooting...")
            # immediate reboot will make juju re-run the hook
            self.unit.reboot(now=True)

        # Safeguard if receiving on start after unit initialization
        if self.unit_peer_data.get("unit-initialized") == "True":
            logger.debug("Delegate status update for start handler on initialized unit.")
            self._on_update_status(None)
            return False

        return True

    def _is_unit_waiting_to_join_cluster(self) -> bool:
        """Return if the unit is waiting to join the cluster."""
        # alternatively, we could check if the instance is configured
        # and have an empty performance_schema.replication_group_members table
        return (
            self.unit_peer_data.get("member-state") == "waiting"
            and self.unit_peer_data.get("unit-configured") == "True"
            and not self.unit_peer_data.get("unit-initialized")
            and int(self.app_peer_data.get("units-added-to-cluster", 0)) > 0
        )

    def _get_primary_from_online_peer(self) -> Optional[str]:
        """Get the primary address from an online peer."""
        for unit in self.peers.units:
            if self.peers.data[unit].get("member-state") == "online":
                try:
                    return self._mysql.get_cluster_primary_address(
                        connect_instance_address=self.get_unit_ip(unit)
                    )
                except MySQLGetClusterPrimaryAddressError:
                    # try next unit
                    continue

    def join_unit_to_cluster(self) -> None:
        """Join the unit to the cluster.

        Try to join the unit from the primary unit.
        """
        instance_label = self.unit.name.replace("/", "-")
        instance_address = self.get_unit_ip(self.unit)

        if not self._mysql.is_instance_in_cluster(instance_label):
            # Add new instance to the cluster
            try:
                cluster_primary = self._get_primary_from_online_peer()
                if not cluster_primary:
                    self.unit.status = WaitingStatus("waiting to get cluster primary from peers")
                    logger.debug(
                        "waiting: unable to retrieve the cluster primary from online peer"
                    )
                    return

                if (
                    self._mysql.get_cluster_node_count(from_instance=cluster_primary)
                    == GR_MAX_MEMBERS
                ):
                    self.unit.status = WaitingStatus(
                        f"Cluster reached max size of {GR_MAX_MEMBERS} units. Standby."
                    )
                    logger.warning(
                        f"Cluster reached max size of {GR_MAX_MEMBERS} units. This unit will stay as standby."
                    )
                    return

                # If instance is part of a replica cluster, locks are managed by the
                # the primary cluster primary (i.e. cluster set global primary)
                lock_instance = None
                if self._mysql.is_cluster_replica(from_instance=cluster_primary):
                    lock_instance = self._mysql.get_cluster_set_global_primary_address(
                        connect_instance_address=cluster_primary
                    )

                # add random delay to mitigate collisions when multiple units are joining
                # due the difference between the time we test for locks and acquire them
                sleep(random.uniform(0, 1.5))

                if self._mysql.are_locks_acquired(from_instance=lock_instance or cluster_primary):
                    self.unit.status = WaitingStatus("waiting to join the cluster.")
                    logger.debug("waiting: cluster lock is held")
                    return

                self.unit.status = MaintenanceStatus("joining the cluster")

                # Stop GR for cases where the instance was previously part of the cluster
                # harmless otherwise
                self._mysql.stop_group_replication()
                # Add the instance to the cluster. This operation uses locks to ensure that
                # only one instance is added to the cluster at a time
                # (so only one instance is involved in a state transfer at a time)
                self._mysql.add_instance_to_cluster(
                    instance_address=instance_address,
                    instance_unit_label=instance_label,
                    from_instance=cluster_primary,
                    lock_instance=lock_instance,
                )
                logger.debug(f"Added instance {instance_address} to cluster")
            except MySQLAddInstanceToClusterError:
                logger.debug(f"Unable to add instance {instance_address} to cluster.")
                return
            except MySQLLockAcquisitionError:
                self.unit.status = WaitingStatus("waiting to join the cluster")
                logger.debug("Waiting to joing the cluster, failed to acquire lock.")
                return
        # Update 'units-added-to-cluster' counter in the peer relation databag
        self.unit_peer_data["unit-initialized"] = "True"
        self.unit_peer_data["member-state"] = "online"
        self.unit.status = ActiveStatus(self.active_status_message)
        logger.debug(f"Instance {instance_label} is cluster member")

    def _restart(self, event: EventBase) -> None:
        """Restart the MySQL service."""
        if self.peers.units != self.restart_peers.units:
            # defer restart until all units are in the relation
            logger.debug("Deferring restart until all units are in the relation")
            event.defer()
            return
        if self._mysql.is_unit_primary(self.unit_label):
            restart_states = {
                self.restart_peers.data[unit].get("state", "unset") for unit in self.peers.units
            }
            if restart_states != {"release"}:
                # Wait other units restart first to minimize primary switchover
                logger.debug("Primary is waiting for other units to restart")
                event.defer()
                return

        self.unit.status = MaintenanceStatus("restarting MySQL")
        self._mysql.restart_mysqld()
        self.unit.status = ActiveStatus(self.active_status_message)


if __name__ == "__main__":
    main(MySQLOperatorCharm)
