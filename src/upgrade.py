# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Dependency model for MySQL."""

import bisect
import json
import logging
from typing import TYPE_CHECKING

from charms.data_platform_libs.v0.upgrade import (
    ClusterNotReadyError,
    DataUpgrade,
    DependencyModel,
    UpgradeGrantedEvent,
    VersionError,
)
from charms.mysql.v0.mysql import (
    MySQLServerNotUpgradableError,
    MySQLSetClusterPrimaryError,
    MySQLSetVariableError,
    MySQLStartMySQLDError,
)
from ops.model import BlockedStatus, MaintenanceStatus, Unit
from pydantic import BaseModel
from tenacity import RetryError, Retrying, stop_after_attempt, wait_fixed
from typing_extensions import override

if TYPE_CHECKING:
    from charm import MySQLOperatorCharm

logger = logging.getLogger(__name__)


class MySQLVMDependenciesModel(BaseModel):
    """MySQL dependencies model."""

    charm: DependencyModel
    snap: DependencyModel


def get_mysql_dependencies_model() -> MySQLVMDependenciesModel:
    """Return the MySQL dependencies model."""
    with open("src/dependency.json") as dependency_file:
        _deps = json.load(dependency_file)
    return MySQLVMDependenciesModel(**_deps)


class MySQLVMUpgrade(DataUpgrade):
    """MySQL upgrade class."""

    def __init__(self, charm: "MySQLOperatorCharm", **kwargs) -> None:
        """Initialize the class."""
        super().__init__(charm, **kwargs)
        self.charm = charm
        self.framework.observe(self.charm.on["upgrade"].relation_changed, self._on_upgrade_changed)

    @override
    def build_upgrade_stack(self) -> list[int]:
        """Build the upgrade stack.

        This/leader/primary will be the last and others ordered by unit number.
        Higher unit number will be upgraded first.
        """

        def unit_number(unit: Unit) -> int:
            """Return the unit number."""
            return int(unit.name.split("/")[1])

        upgrade_stack = []
        for unit in self.peer_relation.units:
            bisect.insort(upgrade_stack, unit_number(unit))

        upgrade_stack.insert(0, unit_number(self.charm.unit))
        return upgrade_stack

    @override
    def pre_upgrade_check(self) -> None:
        """Run pre-upgrade checks."""
        fail_message = "Pre-upgrade check failed. Cannot upgrade."

        def _online_instances(status_dict: dict) -> int:
            """Return the number of online instances from status dict."""
            return [
                item["status"]
                for item in status_dict["defaultreplicaset"]["topology"].values()
                if not item.get("instanceerrors", [])
            ].count("online")

        if cluster_status := self.charm._mysql.get_cluster_status(extended=True):
            if _online_instances(cluster_status) < self.charm.app.planned_units():
                # case any not fully online unit is found
                raise ClusterNotReadyError(
                    message=fail_message,
                    cause="Not all units are online",
                    resolution="Ensure all units are online in the cluster",
                )
        else:
            # case cluster status is not available
            # it may be due to the refresh being ran before
            # the pre-upgrade-check action
            raise ClusterNotReadyError(
                message=fail_message,
                cause="Failed to retrieve cluster status",
                resolution="Ensure that mysqld is running for this unit",
            )

        try:
            self._pre_upgrade_prepare()
        except MySQLSetClusterPrimaryError:
            raise ClusterNotReadyError(
                message=fail_message,
                cause="Failed to set primary",
                resolution="Check the cluster status",
            )
        except MySQLSetVariableError:
            raise ClusterNotReadyError(
                message=fail_message,
                cause="Failed to set slow shutdown",
                resolution="Check the cluster status",
            )

    @override
    def _on_upgrade_granted(self, event: UpgradeGrantedEvent) -> None:
        """Handle the upgrade granted event."""
        self.charm._mysql.stop_mysqld()

        self.charm.unit.status = MaintenanceStatus("upgrading snap...")

        if not self.charm.install_workload():
            logger.error("Failed to install workload snap")
            self.set_unit_failed()
            return
        try:
            self.charm.unit.status = MaintenanceStatus("check if upgrade is possible")
            self._check_server_upgradeability()
            self.charm._mysql.start_mysqld()
        except VersionError:
            logger.exception("Failed to upgrade MySQL dependencies")
            self.set_unit_failed()
            return
        except MySQLStartMySQLDError:
            logger.exception("Failed to start MySQL after upgrade")
            self.set_unit_failed()
            return

        self.charm.unit.status = MaintenanceStatus("recovering unit after upgrade")

        try:
            for attempt in Retrying(stop=stop_after_attempt(6), wait=wait_fixed(10)):
                with attempt:
                    if not self.charm._mysql.is_instance_in_cluster(self.charm.unit_label):
                        logger.debug(
                            "Instance not yet back in the cluster."
                            f" Retry {attempt.retry_state.attempt_number}/6"
                        )
                        raise Exception
                    logger.debug("Upgraded unit is healthy. Set upgrade state to `completed`")
                    self.set_unit_completed()
                    # ensures leader gets it's own relation-changed when it upgrades
                    if self.charm.unit.is_leader():
                        logger.debug("Re-emitting upgrade-changed on leader...")
                        self.on_upgrade_changed(event)
        except RetryError:
            logger.debug("Upgraded unit is not healthy")
            self.set_unit_failed()
            self.charm.unit.status = BlockedStatus(
                "upgrade failed. Check logs for rollback instruction"
            )

    def _on_upgrade_changed(self, _) -> None:
        """Handle the upgrade changed event.

        Run update status for every unit when the upgrade is completed.
        """
        if not self.upgrade_stack and self.idle:
            self.charm._on_update_status(None)

    @override
    def log_rollback_instructions(self) -> None:
        """Log rollback instructions."""
        logger.critical(
            "\n".join(
                (
                    "Upgrade failed, follow the instructions below to rollback:",
                    "    1. Re-run `pre-upgrade-check` action on the leader unit to enter 'recovery' state",
                    "    2. Run `juju refresh` to the previously deployed charm revision",
                )
            )
        )

    def _pre_upgrade_prepare(self) -> None:
        """Pre upgrade routine for MySQL.

        Set primary to the leader (this) unit to mitigate switchover during upgrade,
        and set slow shutdown to all instances.
        """
        if self.charm._mysql.get_primary_label() != self.charm.unit_label:
            # set the primary to the leader unit for switchover mitigation
            self.charm._mysql.set_cluster_primary(self.charm.get_unit_ip(self.charm.unit))

        # set slow shutdown on all instances
        for unit in self.app_units:
            unit_address = self.charm.get_unit_ip(unit)
            self.charm._mysql.set_dynamic_variable(
                variable="innodb_fast_shutdown", value="0", instance_address=unit_address
            )

    def _check_server_upgradeability(self) -> None:
        """Check if the server can be upgraded.

        Use mysql-shell upgrade checker utility to ensure server upgradeability.

        Raises:
            VersionError: If the server is not upgradeable.
        """

        def leader_unit_address() -> str:
            """Return the leader unit."""
            leader_unit_ordinal = self.upgrade_stack[0]
            for unit in self.peer_relation.units:
                if unit.name == f"{self.app.name}/{leader_unit_ordinal}":
                    return self.charm.get_unit_ip(unit)

        try:
            if len(self.upgrade_stack) < self.charm.app.planned_units():
                # only check in the first unit being upgraded
                return
            self.charm._mysql.verify_server_upgradable(instance=leader_unit_address())
            logger.debug("MySQL server is upgradeable")
        except IndexError:
            pass
        except MySQLServerNotUpgradableError as e:
            logger.error("MySQL server is not upgradeable")
            raise VersionError(
                message="Cannot upgrade MySQL server",
                cause=e.message,
                resolution="Check mysql-shell upgrade utility output",
            )
