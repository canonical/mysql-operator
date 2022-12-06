# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Library containing the implementation of the legacy shared-db relation."""


import logging

from charms.mysql.v0.mysql import (
    MySQLCreateApplicationDatabaseAndScopedUserError,
    MySQLGetClusterPrimaryAddressError,
)
from ops.charm import (
    CharmBase,
    LeaderElectedEvent,
    RelationChangedEvent,
    RelationDepartedEvent,
)
from ops.framework import Object
from ops.model import BlockedStatus

from constants import LEGACY_DB_SHARED, PASSWORD_LENGTH, PEER
from utils import generate_random_password

logger = logging.getLogger(__name__)


class SharedDBRelation(Object):
    """Legacy `shared-db` relation implementation."""

    def __init__(self, charm: CharmBase):
        super().__init__(charm, "shared-db-handler")

        self._charm = charm

        self.framework.observe(
            self._charm.on[LEGACY_DB_SHARED].relation_changed, self._on_shared_db_relation_changed
        )
        self.framework.observe(
            self._charm.on[LEGACY_DB_SHARED].relation_departed, self._on_shared_db_departed
        )

        self.framework.observe(self._charm.on.leader_elected, self._on_leader_elected)

    @property
    def _peers(self):
        return self.model.get_relation(PEER)

    def _get_or_set_password(self, username: str) -> str:
        """Retrieve password from cache or generate a new one.

        Args:
            username (str): The username.

        Returns:
            str: The password.
        """
        if password := self._peers.data[self._charm.app].get(f"{username}_password"):
            return password
        password = generate_random_password(PASSWORD_LENGTH)
        self._peers.data[self._charm.app][f"{username}_password"] = password
        return password

    def _on_leader_elected(self, event: LeaderElectedEvent) -> None:
        # Ensure that the leader unit contains the latest data.
        # Legacy apps will consume data from leader unit.

        if not self._charm._is_peer_data_set:
            # Bypass run on initial deployment leader elected event.
            return

        relations = self.model.relations.get(LEGACY_DB_SHARED, [])

        if not relations:
            # Bypass run if no relation
            return

        try:
            db_host = self._charm._mysql.get_cluster_primary_address().split(":")[0]
        except MySQLGetClusterPrimaryAddressError:
            logger.error("Can't get primary address. Deferring")
            event.defer()
            return

        for relation in relations:
            logger.debug(f"Syncing data from leader unit for relation {relation.id}")
            for key, value in relation.data[self._charm.app].items():
                if key == "db_host":
                    relation.data[self._charm.unit][key] = db_host
                    continue

                if relation.data[self._charm.unit].get(key) != value:
                    relation.data[self._charm.unit][key] = value

    def _on_shared_db_relation_changed(self, event: RelationChangedEvent) -> None:
        """Handle the legacy shared_db relation changed event.

        Generate password and handle user and database creation for the related application.
        """
        if not self._charm.unit.is_leader():
            return

        logger.warning("DEPRECATION WARNING - `shared-db` is a legacy interface")

        # get relation data
        remote_unit_data = event.relation.data.get(event.unit)
        if not remote_unit_data:
            # This can happen if the relation is undone before
            # the related app become ready
            logger.warning("No data for remote unit. Did the relation was removed?")
            return

        local_unit_data = event.relation.data[self._charm.unit]
        local_app_data = event.relation.data[self._charm.app]

        joined_unit = event.unit.name

        if joined_unit in local_unit_data.get("allowed_units", ""):
            # Test if relation data is already set for the unit
            # and avoid re-running it
            logger.warning(f"Unit {joined_unit} already added to relation")
            return

        # retrieve data from the relation databag
        # Abstracted is the fact that it is received from the leader unit of the related app
        # fallback to relation app data if data is not set for the unit (non leader unit)
        database_name = remote_unit_data.get("database", local_app_data.get("database"))
        database_user = remote_unit_data.get("username", local_app_data.get("username"))

        if not database_name or not database_user:
            # Cannot create scoped database without credentials
            # Defer the unit configuration until the relation is complete
            logger.warning(
                f"Missing information for shared-db relation to create a database and scoped user for unit {joined_unit}."
            )
            event.defer()
            return

        # cache relation data if not cached already
        if not local_app_data.get("database"):
            local_app_data["database"] = database_name
            local_app_data["username"] = database_user

        password = self._get_or_set_password(database_user)
        remote_host = event.relation.data[event.unit].get("private-address")

        try:
            self._charm._mysql.create_application_database_and_scoped_user(
                database_name, database_user, password, remote_host, joined_unit
            )

            # set the relation data for consumption
            cluster_primary = self._charm._mysql.get_cluster_primary_address()

            local_app_data["db_host"] = local_unit_data["db_host"] = cluster_primary.split(":")[0]

            # Database port is static in legacy charm
            local_app_data["db_port"] = local_unit_data["db_port"] = "3306"
            # Wait timeout is a config option in legacy charm
            # defaulted to 3600 seconds
            local_app_data["wait_timeout"] = local_unit_data["wait_timeout"] = "3600"

            # password already cached
            local_app_data["password"] = local_unit_data["password"] = password

            allowed_units_set = set(local_unit_data.get("allowed_units", "").split())
            allowed_units_set.add(joined_unit)
            local_app_data["allowed_units"] = local_unit_data["allowed_units"] = " ".join(
                allowed_units_set
            )

        except MySQLCreateApplicationDatabaseAndScopedUserError:
            self._charm.unit.status = BlockedStatus("Failed to initialize shared_db relation")
            return

    def _on_shared_db_departed(self, event: RelationDepartedEvent) -> None:
        """Handle the departure of legacy shared_db relation.

        Remove unit name from allowed_units key.
        """
        if not self._charm.unit.is_leader():
            return

        if event.departing_unit.app == self._charm.app:
            # Just run for departing of remote units
            return

        departing_unit = event.departing_unit.name
        local_unit_data = event.relation.data[self._charm.unit]
        local_app_data = event.relation.data[self._charm.app]

        current_allowed_units = local_unit_data.get("allowed_units", "")

        logger.debug(f"Removing unit {departing_unit} from allowed_units")
        local_app_data["allowed_units"] = local_unit_data["allowed_units"] = " ".join(
            {unit for unit in current_allowed_units.split() if unit != departing_unit}
        )

        # remove unit users
        logger.debug(f"Removing user for unit {departing_unit}")
        self._charm._mysql.delete_users_for_unit(departing_unit)
