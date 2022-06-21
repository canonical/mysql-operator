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

    @property
    def _peers(self):
        return self.model.get_relation(PEER)

    def get_and_set_password(self, app: str, username: str) -> str:
        """Retrieve password from cache or generate a new one.

        Args:
            app (str): The application name.
            username (str): The username.

        """
        if password := self._peers.data[self._charm.app].get(f"{app}_{username}_password"):
            return password
        password = generate_random_password(PASSWORD_LENGTH)
        self._peers.data[self._charm.app][f"{app}_{username}_password"] = password
        return password

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

    def _on_shared_db_relation_changed(self, event: RelationChangedEvent) -> None:
        """Handle the legacy shared_db relation changed event.

        Generate password and handle user and database creation for the related application.
        """
        if not self._charm.unit.is_leader():
            return

        self._charm.unit.status = MaintenanceStatus("Setting up shared-db relation")
        logger.warning("DEPRECATION WARNING - `shared-db` is a legacy interface")

        unit_relation_databag = event.relation.data[self._charm.unit]

        if unit_relation_databag.get("password"):
            # Test if relation data is already set
            # and avoid overwriting it
            logger.warning("Data for shared-db already set.")
            self._charm.unit.status = ActiveStatus()
            return

        # retrieve data from the relation databag
        # Abstracted is the fact that it is received from the leader unit of the related app
        requires_relation_databag = event.relation.data[event.unit]
        database_name = requires_relation_databag.get("database")
        database_user = requires_relation_databag.get("username")
        hostname = requires_relation_databag.get("hostname")

        if not database_name or not database_user:
            # Cannot create scoped database without credentials
            logger.warning(
                "Missing information for shared-db relation to create a database and scoped user"
            )
            self._charm.unit.status = WaitingStatus("Missing information for shared-db relation")
            return

        password = self.get_and_set_password(event.unit.app, database_user)

        try:
            self._charm._mysql.create_application_database_and_scoped_user(
                database_name, database_user, password, hostname
            )

            # set the relation data for consumption
            cluster_primary = self._charm._mysql.get_cluster_primary_address()

            unit_relation_databag["db_host"] = cluster_primary.split(":")[0]
            # Database port is static in legacy charm
            unit_relation_databag["db_port"] = "3306"
            # Wait timeout is a config option in legacy charm
            # defaulted to 3600 seconds
            unit_relation_databag["wait_timeout"] = "3600"
            unit_relation_databag["password"] = password

            unit_relation_databag[
                "allowed_units"
            ] = f"{unit_relation_databag.get('allowed_units','')} {event.unit.name}"

        except MySQLCreateApplicationDatabaseAndScopedUserError:
            self._charm.unit.status = BlockedStatus("Failed to initialize shared_db relation")
            return

        self._charm.unit.status = ActiveStatus()

    def _on_shared_db_broken(self, event: RelationBrokenEvent) -> None:
        """Handle the departure of legacy shared_db relation."""
        if not self._charm.unit.is_leader():
            return

        # TODO: pop the password from the relation data

        # remove stale users, if any
        self._remove_stale_users()

    def _on_shared_db_departed(self, event: RelationDepartedEvent) -> None:
        """Handle the departure of legacy shared_db relation.

        Remove unit name from allowed_units key.
        """
        if not self._charm.unit.is_leader():
            return

        departing_unit = event.departing_unit.name
        unit_relation_databag = event.relation.data[self._charm.unit]

        current_allowed_units = unit_relation_databag.get("allowed_units", "")

        unit_relation_databag["allowed_units"] = " ".join(
            [unit for unit in current_allowed_units.split() if unit != departing_unit]
        )

        # remove stale users, if any
        self._remove_stale_users()
