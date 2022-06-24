# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Library containing the implementation of the legacy shared-db relation."""


import logging

from charms.mysql.v0.mysql import MySQLCreateApplicationDatabaseAndScopedUserError
from ops.charm import (
    CharmBase,
    RelationBrokenEvent,
    RelationChangedEvent,
    RelationDepartedEvent,
)
from ops.framework import Object
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus

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
            self._charm.on[LEGACY_DB_SHARED].relation_broken, self._on_shared_db_broken
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

    def _get_cached_key(self, relation_id: int, key: str) -> str:
        """Retrieve cached key from the peer databag.

        Args:
            relation_id (int): The relation id.
            key (str): The key to retrieve.

        Returns:
            str: The value (str) of the key.
        """
        databag = self._peers.data[self._charm.app]
        return databag.get(f"{relation_id}_{key}")

    def _set_cached_key(self, relation_id: int, key: str, value: str) -> None:
        """Set cached key in the peer databag.

        Args:
            relation_id (int): The relation id.
            key (str): The key to set a value to.
            value (str): The value to set.
        """
        databag = self._peers.data[self._charm.app]
        databag[f"{str(relation_id)}_{key}"] = value

    def _on_leader_elected(self, _) -> None:
        # Ensure that the leader unit contains the latest data.
        # Legacy apps will consume data from leader unit.
        peer_data = self._peers.data

        logger.debug("Syncing data from leader unit")
        for relation in self.model.relations.get(LEGACY_DB_SHARED, []):
            for key, value in peer_data[self._charm.app].items():
                if key.startswith(str(relation.id)):
                    unit_key = key.split("_")[1]
                    relation.data[self._charm.unit][unit_key] = value

    def _on_shared_db_relation_changed(self, event: RelationChangedEvent) -> None:
        """Handle the legacy shared_db relation changed event.

        Generate password and handle user and database creation for the related application.
        """
        if not self._charm.unit.is_leader():
            return

        self._charm.unit.status = MaintenanceStatus("Setting up shared-db relation")
        logger.warning("DEPRECATION WARNING - `shared-db` is a legacy interface")

        # get relation data
        remote_unit_data = event.relation.data[event.unit]
        app_unit_data = event.relation.data[self._charm.unit]

        joined_unit = event.unit.name

        if joined_unit in app_unit_data.get("allowed_units", ""):
            # Test if relation data is already set for the unit
            # and avoid re-running it
            logger.warning(f"Unit {joined_unit} already added to relation")
            self._charm.unit.status = ActiveStatus()
            return

        relation_id = event.relation.id
        # retrieve data from the relation databag
        # Abstracted is the fact that it is received from the leader unit of the related app
        # fallback to peer data if data is not set for the unit (non leader unit)
        database_name = remote_unit_data.get(
            "database", self._get_cached_key(relation_id, "database")
        )
        database_user = remote_unit_data.get(
            "username", self._get_cached_key(relation_id, "username")
        )

        if not database_name or not database_user:
            # Cannot create scoped database without credentials
            # Defer the unit configuration until the relation is complete
            logger.warning(
                f"Missing information for shared-db relation to create a database and scoped user for unit {joined_unit}."
            )
            event.defer()
            return

        # cache relation data
        self._set_cached_key(relation_id, "database", database_name)
        self._set_cached_key(relation_id, "username", database_user)

        password = self._get_or_set_password(database_user)
        remote_host = event.relation.data[event.unit].get("private-address")

        try:
            self._charm._mysql.create_application_database_and_scoped_user(
                database_name, database_user, password, remote_host, joined_unit
            )

            # set the relation data for consumption
            cluster_primary = self._charm._mysql.get_cluster_primary_address()

            app_unit_data["db_host"] = cluster_primary.split(":")[0]
            self._set_cached_key(relation_id, "db_host", app_unit_data["db_host"])
            # Database port is static in legacy charm
            app_unit_data["db_port"] = "3306"
            self._set_cached_key(relation_id, "db_port", app_unit_data["db_port"])
            # Wait timeout is a config option in legacy charm
            # defaulted to 3600 seconds
            app_unit_data["wait_timeout"] = "3600"
            self._set_cached_key(relation_id, "wait_timeout", app_unit_data["wait_timeout"])

            # password already cached
            app_unit_data["password"] = password

            app_unit_data[
                "allowed_units"
            ] = f"{app_unit_data.get('allowed_units','')} {joined_unit}"
            self._set_cached_key(relation_id, "allowed_units", app_unit_data["allowed_units"])

        except MySQLCreateApplicationDatabaseAndScopedUserError:
            self._charm.unit.status = BlockedStatus("Failed to initialize shared_db relation")
            return

        self._charm.unit.status = ActiveStatus()

    def _on_shared_db_broken(self, event: RelationBrokenEvent) -> None:
        """Handle the departure of legacy shared_db relation."""
        if not self._charm.unit.is_leader():
            return

        # Remove cached data
        relation_keys = [
            k
            for k in self._peers.data[self._charm.app].keys()
            if k.startswith(str(event.relation.id))
        ]

        # if event.relation.data:
        #     # TODO: safeguard for relation_broken being emitted on scale in
        #     #       to be confirmed juju bug
        #     # FIXME: this test wont do!!!
        #     logger.debug("Refuse to remove cached data from active relation.")
        #     return

        logger.debug(f"Removing cached keys for relation {event.relation.id}")

        for key in relation_keys:
            self._peers.data[self._charm.app].pop(key)

    def _on_shared_db_departed(self, event: RelationDepartedEvent) -> None:
        """Handle the departure of legacy shared_db relation.

        Remove unit name from allowed_units key.
        """
        if not self._charm.unit.is_leader():
            return

        departing_unit = event.departing_unit.name
        app_unit_data = event.relation.data[self._charm.unit]

        current_allowed_units = app_unit_data.get("allowed_units", "")

        logger.debug(f"Removing unit {departing_unit} from allowed_units")
        app_unit_data["allowed_units"] = " ".join(
            {unit for unit in current_allowed_units.split() if unit != departing_unit}
        )
        # sync with peer data
        try:
            self._set_cached_key(
                event.relation.id, "allowed_units", app_unit_data["allowed_units"]
            )
        except KeyError:
            # ignore error when the relation is no longer present
            pass

        # remove unit users
        self._charm._mysql.delete_users_for_unit(departing_unit)
