# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Library containing the implementation of the legacy shared-db relation."""


import logging
from ops.framework import Object

from ops.charm import CharmBase, RelationChangedEvent, RelationBrokenEvent, RelationDepartedEvent

from ops.model import MaintenanceStatus, ActiveStatus, WaitingStatus, BlockedStatus

from constants import PEER, PASSWORD_LENGTH, LEGACY_DB_SHARED
from charms.mysql.v0.mysql import (
    MySQLCreateApplicationDatabaseAndScopedUserError,
    MySQLRemoveUserError,
    MySQLRemoveDatabaseError,
)
from utils import generate_random_password

logger = logging.getLogger(__name__)


class SharedDBRelation(Object):
    def __init__(self, charm: CharmBase):
        super().__init__(charm)

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
        if password := self._peers.data[self.app].get(f"{app}_{username}_password"):
            return password
        password = generate_random_password(PASSWORD_LENGTH)
        self._peers.data[self.app][f"{app}_{username}_password"] = password
        return password

    def _on_shared_db_relation_changed(self, event: RelationChangedEvent) -> None:
        """Handle the legacy shared_db relation changed event.

        Generate password and handle user and database creation for the related application.
        """
        if not self.unit.is_leader():
            return

        self.unit.status = MaintenanceStatus("Setting up shared-db relation")
        logger.warning("DEPRECATION WARNING - `shared-db` is a legacy interface")

        unit_relation_databag = event.relation.data[self.unit]
        app_relation_databag = event.relation.data[self.app]

        if unit_relation_databag.get("password"):
            # Test if relation data is already set
            # and avoid overwriting it
            logger.warning("Data for shared-db already set.")
            self.unit.status = ActiveStatus()
            return

        # retrieve data from the relation databag
        # Abstracted is the fact that it is received from the leader unit of the related app
        requires_relation_databag = event.relation.data[event.unit]
        database_name = requires_relation_databag.get("database")
        database_user = requires_relation_databag.get("username")

        if not database_name or not database_user:
            # Cannot create scoped database without credentials
            logger.warning(
                "Missing information for shared-db relation to create a database and scoped user"
            )
            self.unit.status = WaitingStatus("Missing information for shared-db relation")
            return

        password = self.get_and_set_password(event.unit.app, database_user)
        hostname = self.model.get_binding(event.relation).network.bind_address

        try:
            self._mysql.create_application_database_and_scoped_user(
                database_name, database_user, password, hostname
            )

            # set the relation data for consumption
            cluster_primary = self._mysql.get_cluster_primary_address()

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
            self.unit.status = BlockedStatus("Failed to initialize shared_db relation")
            return

        self.unit.status = ActiveStatus()

    def _on_shared_db_broken(self, event: RelationBrokenEvent) -> None:
        """Handle the departure of legacy shared_db relation.

        Remove user created for the relation.
        Remove database created for the relation if `auto-delete` is set.
        """
        if not self.unit.is_leader():
            return

        app_relation_databag = event.relation.data[self.app]
        username = app_relation_databag.get(f"relation_id_{event.relation.id}_db_user")

        if not username:
            # Can't do much if we don't have the username
            logger.warning(f"Missing username for shared-db relation id {event.relation.id}.")
            return

        try:
            # remove user and pop relation data from app databag
            self._mysql.remove_user(username)
            app_relation_databag.pop(f"relation_id_{event.relation.id}_db_user")
            logger.info(f"Removed user {username} from database.")
        except MySQLRemoveUserError:
            logger.warning(f"Failed to remove user {username} from database.")

        if self.config.get("auto-delete", False):
            # remove database and pop relation data from app databag
            database_name = app_relation_databag.get(f"relation_id_{event.relation.id}_db_name")
            if not database_name:
                logger.warning(
                    f"Missing database name for shared-db relation id {event.relation.id}."
                )
                return

            try:
                self._mysql.remove_database(database_name)
                app_relation_databag.pop(f"relation_id_{event.relation.id}_db_name")
                logger.info(f"Removed database {database_name}.")
            except MySQLRemoveDatabaseError:
                logger.warning(f"Failed to remove database {database_name}.")

    def _on_shared_db_departed(self, event: RelationDepartedEvent) -> None:
        """Handle the departure of legacy shared_db relation.

        Remove unit name from allowed_units key.
        """
        if not self.unit.is_leader():
            return

        departing_unit = event.departing_unit.name
        unit_relation_databag = event.relation.data[self.unit]

        current_allowed_units = unit_relation_databag.get("allowed_units", "")

        unit_relation_databag["allowed_units"] = " ".join(
            [unit for unit in current_allowed_units.split() if unit != departing_unit]
        )
