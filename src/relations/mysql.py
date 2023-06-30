# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Library containing the implementation of the legacy mysql relation."""

import json
import logging

from charms.mysql.v0.mysql import (
    MySQLCreateApplicationDatabaseAndScopedUserError,
    MySQLDeleteUsersForUnitError,
    MySQLGetClusterPrimaryAddressError,
)
from ops.charm import RelationBrokenEvent, RelationCreatedEvent
from ops.framework import Object
from ops.model import BlockedStatus

from constants import LEGACY_MYSQL, PASSWORD_LENGTH
from utils import generate_random_password

logger = logging.getLogger(__name__)


class MySQLRelation(Object):
    """Encapsulation of the legacy mysql relation."""

    def __init__(self, charm):
        super().__init__(charm, LEGACY_MYSQL)

        self.charm = charm

        self.framework.observe(self.charm.on.leader_elected, self._on_leader_elected)
        self.framework.observe(self.charm.on.config_changed, self._on_config_changed)
        self.framework.observe(
            self.charm.on[LEGACY_MYSQL].relation_created, self._on_mysql_relation_created
        )

        self.framework.observe(
            self.charm.on[LEGACY_MYSQL].relation_broken, self._on_mysql_relation_broken
        )

    def _get_or_set_password_in_peer_databag(self, username: str) -> str:
        """Get a user's password from the peer databag if it exists, else populate a password.

        Args:
            username: The mysql username

        Returns:
            a string representing the password for the mysql user
        """
        peer_databag = self.charm.app_peer_data

        if peer_databag.get(f"{username}_password"):
            return peer_databag.get(f"{username}_password")

        password = generate_random_password(PASSWORD_LENGTH)
        peer_databag[f"{username}_password"] = password

        return password

    def _get_or_generate_username(self, event_relation_id: int) -> str:
        """Retrieve username from databag or config or generate a new one.

        Assumes that the caller is the leader unit.
        """
        username = (
            self.charm.app_peer_data.get("mysql-interface-user")
            or self.charm.config.get("mysql-interface-user")
            or f"relation-{event_relation_id}"
        )
        self.charm.app_peer_data["mysql-interface-user"] = username
        return username

    def _get_or_generate_database(self, event_relation_id: int) -> str:
        """Retrieve database from databag or config or generate a new one.

        Assumes that the caller is the leader unit.
        """
        database_name = (
            self.charm.app_peer_data.get("mysql-interface-database")
            or self.charm.config.get("mysql-interface-database")
            or f"database-{event_relation_id}"
        )
        self.charm.app_peer_data["mysql-interface-database"] = database_name
        return database_name

    def _on_leader_elected(self, _) -> None:
        """Handle the leader elected event.

        Retrieves relation data from the peer relation databag and copies
        the relation data into the new leader unit's databag.
        """
        # Skip if the charm is not past the setup phase (config-changed event not executed yet)
        if not self.charm._is_peer_data_set:
            return

        relation_data = json.loads(self.charm.app_peer_data.get("mysql_relation_data", "{}"))

        for relation in self.charm.model.relations.get(LEGACY_MYSQL, []):
            relation_databag = relation.data

            # Copy relation data into the new leader unit's databag
            for key, value in relation_data.items():
                if relation_databag[self.charm.unit].get(key) != value:
                    relation_databag[self.charm.unit][key] = value

            # Assign the cluster primary's address as the database host
            primary_address = self.charm._mysql.get_cluster_primary_address().split(":")[0]
            relation_databag[self.charm.unit]["host"] = primary_address

    def _on_config_changed(self, _) -> None:
        """Handle the change of the username/database in config."""
        if not self.charm.unit.is_leader():
            return

        # the mysql-relation-created event has not yet fired
        if not self.charm.app_peer_data.get("mysql-interface-user"):
            return

        username = self.charm.config.get("mysql-interface-user")
        database = self.charm.config.get("mysql-interface-database")

        if not username or not database:
            return

        if self.charm._mysql.does_mysql_user_exist(username, "%"):
            logger.info(f"User '{username}'@'%' already exists")
            return

        if (
            username == self.charm.app_peer_data["mysql-interface-user"]
            and database == self.charm.app_peer_data["mysql-interface-database"]
        ):
            return

        try:
            self.charm._mysql.delete_users_for_unit("mysql-legacy-relation")
        except MySQLDeleteUsersForUnitError:
            logger.error("Failed to delete mysql users")
            self.charm.unit.status = BlockedStatus("Failed to remove relation user")

        password = self._get_or_set_password_in_peer_databag(username)

        try:
            self.charm._mysql.create_application_database_and_scoped_user(
                database,
                username,
                password,
                "%",
                unit_name="mysql-legacy-relation",
            )

            primary_address = self.charm._mysql.get_cluster_primary_address().split(":")[0]

        except (
            MySQLCreateApplicationDatabaseAndScopedUserError,
            MySQLGetClusterPrimaryAddressError,
        ):
            self.charm.unit.status = BlockedStatus("Failed to initialize mysql relation")
            return

        updates = {
            "database": database,
            "host": primary_address,
            "password": password,
            "port": "3306",
            "root_password": self.charm.app_peer_data["root-password"],
            "user": username,
        }

        self.charm.app_peer_data["mysql-interface-user"] = username
        self.charm.app_peer_data["mysql-interface-database"] = database
        self.charm.app_peer_data["mysql_relation_data"] = json.dumps(updates)

        for relation in self.charm.model.relations.get(LEGACY_MYSQL, []):
            relation.data[self.charm.unit].update(updates)

    def _on_mysql_relation_created(self, event: RelationCreatedEvent) -> None:
        """Handle the legacy 'mysql' relation created event.

        Will set up the database and the scoped application user. The connection
        data (relation data) is then copied into the peer relation databag (to
        be copied over to the new leader unit's databag in case of a new leader
        being elected).
        """
        if not self.charm.unit.is_leader():
            return

        # Wait until on-config-changed event is executed
        # (wait for root password to have been set)
        if not self.charm._is_peer_data_set:
            event.defer()
            return

        logger.warning("DEPRECATION WARNING - `mysql` is a legacy interface")

        # wait until the unit is initialized
        if not self.charm.unit_peer_data.get("unit-initialized"):
            event.defer()
            return

        username = self._get_or_generate_username(event.relation.id)
        database = self._get_or_generate_database(event.relation.id)

        # Only execute if the application user does not exist
        # since it could have been created by another related app
        if self.charm._mysql.does_mysql_user_exist(username, "%"):
            return

        password = self._get_or_set_password_in_peer_databag(username)

        try:
            self.charm._mysql.create_application_database_and_scoped_user(
                database,
                username,
                password,
                "%",
                unit_name="mysql-legacy-relation",
            )

            primary_address = self.charm._mysql.get_cluster_primary_address().split(":")[0]

        except (
            MySQLCreateApplicationDatabaseAndScopedUserError,
            MySQLGetClusterPrimaryAddressError,
        ):
            self.charm.unit.status = BlockedStatus("Failed to initialize mysql relation")
            return

        updates = {
            "database": database,
            "host": primary_address,
            "password": password,
            "port": "3306",
            "root_password": self.charm.app_peer_data["root-password"],
            "user": username,
        }

        event.relation.data[self.charm.unit].update(updates)

        # Store the relation data into the peer relation databag
        self.charm.app_peer_data["mysql_relation_data"] = json.dumps(updates)

    def _on_mysql_relation_broken(self, event: RelationBrokenEvent) -> None:
        """Handle the 'mysql' legacy relation broken event.

        Delete the application user created in the relation created
        event handler.
        """
        if not self.charm.unit.is_leader():
            return

        if len(self.model.relations[LEGACY_MYSQL]) > 1:
            # avoid removing user when there's other related applications
            return

        logger.warning("DEPRECATION WARNING - `mysql` is a legacy interface")

        try:
            self.charm._mysql.delete_users_for_unit("mysql-legacy-relation")
        except MySQLDeleteUsersForUnitError:
            logger.error("Failed to delete mysql users")
            self.charm.unit.status = BlockedStatus("Failed to remove relation user")

        del self.charm.app_peer_data["mysql-interface-user"]
        del self.charm.app_peer_data["mysql-interface-database"]
