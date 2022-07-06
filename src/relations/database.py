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
    MySQLDeleteUserForRelationError,
)
from ops.charm import RelationDepartedEvent
from ops.framework import Object
from ops.model import BlockedStatus

from constants import PASSWORD_LENGTH
from utils import generate_random_password

logger = logging.getLogger(__name__)


class DatabaseRelation(Object):
    """Standard database relation class."""

    def __init__(self, charm):
        super().__init__(charm, "database")

        self._charm = charm

        self.database = DatabaseProvides(self._charm, relation_name="database")
        self.framework.observe(self.database.on.database_requested, self._on_database_requested)

        self.framework.observe(
            self._charm.on["database"].relation_broken, self._on_database_broken
        )

    def _get_or_set_password(self, relation) -> str:
        """Retrieve password from cache or generate a new one.

        Args:
            relation (str): The relation for each the password is cached.

        Returns:
            str: The password.
        """
        if password := relation.data[self._charm.app].get("password"):
            return password
        password = generate_random_password(PASSWORD_LENGTH)
        relation.data[self._charm.app]["password"] = password
        return password

    def _on_database_requested(self, event: DatabaseRequestedEvent):
        """Handle the `database-requested` event."""
        if not self._charm.unit.is_leader():
            return

        # get base relation data
        db_name = event.database
        db_user = f"relation-{event.relation.id}"
        db_pass = self._get_or_set_password(event.relation)
        db_version = self._charm._mysql.get_mysql_version()

        remote_app = event.app.name

        try:
            self._charm._mysql.create_application_database_and_scoped_user(
                db_name, db_user, db_pass, "%", remote_app
            )
            primary_endpoint = self._charm._mysql.get_cluster_primary_address()
            self.database.set_credentials(event.relation.id, db_user, db_pass)
            self.database.set_endpoints(event.relation.id, primary_endpoint)
            self.database.set_version(event.relation.id, db_version)
            secondaries_endpoints = self._charm._mysql.get_cluster_members_addresses() - set(
                primary_endpoint
            )
            self.database.set_secondaries_endpoints(event.relation.id, secondaries_endpoints)
            # TODO:
            # add setup of tls, tls_ca and status

            logger.info(f"Created user for app {remote_app}")
        except MySQLCreateApplicationDatabaseAndScopedUserError:
            logger.error(f"Failed to create scoped user for app {remote_app}")
            self._charm.unit.status = BlockedStatus("Failed to create scoped user")
            return
        except MySQLClientError:
            logger.error("Failed to find MySQL cluster primary")
            self._charm.unit.status = BlockedStatus("Failed to retrieve endpoint")
            return

    def _on_database_broken(self, event: RelationDepartedEvent) -> None:
        """Handle the removal of database relation.

        Remove user, keeping database intact.
        """
        if not self._charm.unit.is_leader():
            # run once by the leader
            return

        if event.departing_unit.app == self._charm.app:
            # Just run for departing of remote units
            return

        try:
            relation_id = event.relation.id
            self._charm._mysql.delete_user_for_relation(relation_id)
            logger.info(f"Removed user for relation {relation_id}")
        except MySQLDeleteUserForRelationError:
            logger.error(f"Failed to delete user for relation {relation_id}")
            return
