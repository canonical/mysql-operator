# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Library containing the implementation of the legacy shared-db relation."""


import logging
from typing import Set

from charms.mysql.v0.mysql import (
    MySQLCreateApplicationDatabaseAndScopedUserError,
    MySQLListClusterUsersError,
    MySQLRemoveUserError,
)
from ops.charm import (
    CharmBase,
    RelationBrokenEvent,
    RelationChangedEvent,
    RelationDepartedEvent,
)
from ops.framework import Object
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus

from constants import LEGACY_DB_ROUTER, LEGACY_DB_SHARED, PASSWORD_LENGTH, PEER
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

    def _get_or_set_password(self, relation_id: int) -> str:
        """Retrieve password from cache or generate a new one.

        Args:
            app (str): The application name.
            username (str): The username.
        Returns:
            str: The password.
        """
        if password := self._get_cached_key(relation_id, "password"):
            return password
        password = generate_random_password(PASSWORD_LENGTH)
        self._set_cached_key(relation_id, "password", password)
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

        """
        databag = self._peers.data[self._charm.app]
        databag[f"{str(relation_id)}_{key}"] = value

    def _generate_user_diff(self) -> Set[str]:
        """Generate a set of users to be removed.

        Iterate units of relations to generate valid user list and compare with
        user list from the cluster.

        Returns:
            Set[str]: The set of users to be removed.
        """
        valid_relation_users = set()

        # list all units by `shared-db` relation name
        shared_db_units = [
            unit
            for relation in self.model.relations.get(LEGACY_DB_SHARED, [])
            for unit in relation.units
        ]
        shared_db_relation_data = (
            self.model.get_relation(LEGACY_DB_SHARED).data
            if self.model.get_relation(LEGACY_DB_SHARED)
            else {}
        )
        # generate valid users for `shared-db`
        valid_relation_users |= set(
            [
                f"{shared_db_relation_data[unit].get('username')}@{shared_db_relation_data[unit].get('hostname')}"
                for unit in shared_db_units
            ]
        )

        # list all units by `db-router` relation name
        db_router_units = [
            unit
            for relation in self.model.relations.get(LEGACY_DB_ROUTER, [])
            for unit in relation.units
        ]
        db_router_relation_data = (
            self.model.get_relation(LEGACY_DB_ROUTER).data
            if self.model.get_relation(LEGACY_DB_ROUTER)
            else {}
        )
        # generate valid users for `db-router`
        for unit in db_router_units:
            for key in db_router_relation_data[unit]:
                if "_username" in key:
                    application_name = key.split("_")[0]
                    hostname_key = f"{application_name}_hostname"
                    valid_relation_users.add(
                        f"{db_router_relation_data[unit].get(key)}@{db_router_relation_data.get(hostname_key)}"
                    )

        # valid usernames for relations
        valid_usernames = set([user.split("@")[0] for user in valid_relation_users])

        try:
            # retrieve cluster users list
            database_users = self._charm._mysql.list_cluster_users()
        except MySQLListClusterUsersError:
            return

        # filter out non related users
        valid_database_users = set(
            [user for user in database_users if user.split("@")[0] in valid_usernames]
        )

        return valid_relation_users - valid_database_users

    def _remove_stale_users(self) -> None:
        """Remove stale users from the cluster, if any."""
        for user in self._generate_user_diff():
            try:
                self._charm._mysql.remove_user(user)
            except MySQLRemoveUserError:
                return

    def _on_leader_elected(self, _) -> None:
        # Ensure that the leader unit contains the latest data.
        # Legacy apps will consume data from leader unit.
        peer_data = self._peers.data

        for relation in self.model.relations.get(LEGACY_DB_SHARED, []):
            relation_id = relation.relation_id

            for key, value in peer_data[self._charm.app].items():
                if key.startswith(str(relation_id)):
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

        if event.unit.name in app_unit_data.get("allowed_units", ""):
            # Test if relation data is already set for the unit
            # and avoid re-running it
            logger.warning(f"Unit {event.unit.name} already added to relation")
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
                f"Missing information for shared-db relation to create a database and scoped user for unit {event.unit.name}."
            )
            event.defer()
            return

        # cache relation data
        self._set_cached_key(relation_id, "database", database_name)
        self._set_cached_key(relation_id, "username", database_user)

        password = self._get_or_set_password(relation_id)
        remote_host = event.relation.data[event.unit].get("private-address")

        try:
            self._charm._mysql.create_application_database_and_scoped_user(
                database_name, database_user, password, remote_host
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
            ] = f"{app_unit_data.get('allowed_units','')} {event.unit.name}"
            self._set_cached_key(relation_id, "allowed_units", app_unit_data["allowed_units"])

        except MySQLCreateApplicationDatabaseAndScopedUserError:
            self._charm.unit.status = BlockedStatus("Failed to initialize shared_db relation")
            return

        self._charm.unit.status = ActiveStatus()

    def _on_shared_db_broken(self, event: RelationBrokenEvent) -> None:
        """Handle the departure of legacy shared_db relation."""
        if not self._charm.unit.is_leader():
            return

        # remove stale users, if any
        self._remove_stale_users()

    def _on_shared_db_departed(self, event: RelationDepartedEvent) -> None:
        """Handle the departure of legacy shared_db relation.

        Remove unit name from allowed_units key.
        """
        if not self._charm.unit.is_leader():
            return

        departing_unit = event.departing_unit.name
        app_unit_data = event.relation.data[self._charm.unit]

        current_allowed_units = app_unit_data.get("allowed_units", "")

        app_unit_data["allowed_units"] = " ".join(
            [unit for unit in current_allowed_units.split() if unit != departing_unit]
        )
        # sync with peer data
        self._set_cached_key(event.relation.id, "allowed_units", app_unit_data["allowed_units"])

        # remove stale users, if any
        self._remove_stale_users()
