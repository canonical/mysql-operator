# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Library containing the implementation of the standard relation."""


import logging

from charms.data_platform_libs.v0.database_provides import (
    DatabaseProvides,
    DatabaseRequestedEvent,
)
from charms.mysql.v0.mysql import (
    MySQLClientError,
    MySQLCreateApplicationDatabaseAndScopedUserError,
    MySQLDeleteUsersForUnitError,
)
from ops.charm import RelationDepartedEvent
from ops.framework import Object
from ops.model import BlockedStatus

from constants import PASSWORD_LENGTH
from utils import generate_random_password

logger = logging.getLogger(__name__)


class DatabaseRelation(Object):
    def __init__(self, charm):
        super().__init__(charm, "database")

        self._charm = charm

        self.database = DatabaseProvides(self._charm, relation_name="database")
        self.framework.observe(self.database.on.database_requested, self._on_database_requested)

        self.framework.observe(
            self._charm.on["database"].relation_departed, self._on_database_departed
        )

    def _get_or_set_password(self, relation) -> str:
        """Retrieve password from cache or generate a new one.

        Args:
            relation (str): The relation for each the password is cached.

        Returns:
            str: The password.
        """
        if password := relation.data[self._charm.app].get(f"password"):
            return password
        password = generate_random_password(PASSWORD_LENGTH)
        relation.data[self._charm.app][f"password"] = password
        return password

    def _on_database_requested(self, event: DatabaseRequestedEvent):
        """Handle the `database-requested` event."""

        if not self._charm.unit.is_leader():
            return

        db_name = event.database
        db_user = event.app.name
        db_pass = self._get_or_set_password(event.relation)

        remote_host = event.relation.data[event.unit].get("private-address")
        remote_unit = event.unit.name

        try:
            self._charm._mysql.create_application_database_and_scoped_user(
                db_name, db_user, db_pass, remote_host, remote_unit
            )
            uri = self._charm._mysql.get_cluster_primary_address()
            self.database.set_credentials(event.relation.id, db_user, db_pass)
            self.database.set_endpoints(event.relation.id, uri)
            logger.info(f"Created user for unit {remote_unit}")
        except MySQLCreateApplicationDatabaseAndScopedUserError:
            logger.error(f"Failed to create scoped user for unit {remote_unit}")
            self._charm.unit.status = BlockedStatus("Failed to create scoped user")
            return
        except MySQLClientError:
            logger.error("Failed to find MySQL cluster primary")
            self._charm.unit.status = BlockedStatus("Failed to retrieve endpoint")
            return

    def _on_database_departed(self, event: RelationDepartedEvent) -> None:
        """Handle the departure of legacy shared_db relation.

        Remove unit name from allowed_units key.
        """
        if not self._charm.unit.is_leader():
            return

        if event.departing_unit.app == self._charm.app:
            # Just run for departing of remote units
            return

        departing_unit = event.departing_unit.name

        # remove unit users
        try:
            self._charm._mysql.delete_users_for_unit(departing_unit)
            logger.info(f"Removed user for unit {departing_unit}")
        except MySQLDeleteUsersForUnitError:
            logger.error(f"Failed to delete users for unit {departing_unit}")
            return
