# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Library containing the implementation of the legacy mysql relation."""

import json
import logging
import socket
import typing

from charms.mysql.v0.mysql import (
    MySQLCheckUserExistenceError,
    MySQLCreateApplicationDatabaseAndScopedUserError,
    MySQLDeleteUsersForUnitError,
    MySQLGetClusterPrimaryAddressError,
)
from ops.charm import RelationBrokenEvent, RelationCreatedEvent
from ops.framework import Object
from ops.model import ActiveStatus, BlockedStatus

from constants import LEGACY_MYSQL, PASSWORD_LENGTH, ROOT_PASSWORD_KEY
from utils import generate_random_password

logger = logging.getLogger(__name__)

MYSQL_RELATION_DATA_KEY = "mysql_relation_data"
MYSQL_RELATION_USER_KEY = "mysql-interface-user"
MYSQL_RELATION_DATABASE_KEY = "mysql-interface-database"

if typing.TYPE_CHECKING:
    from charm import MySQLOperatorCharm


class MySQLRelation(Object):
    """Encapsulation of the legacy mysql relation."""

    def __init__(self, charm: "MySQLOperatorCharm"):
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

    def _get_or_set_password_in_peer_secrets(self, username: str) -> str:
        """Get a user's password from the peer secrets, if it exists, else populate a password.

        Args:
            username: The mysql username

        Returns:
            a string representing the password for the mysql user
        """
        password_key = f"{username}-password"
        password = self.charm.get_secret("app", password_key)
        if password:
            return password

        password = generate_random_password(PASSWORD_LENGTH)
        self.charm.set_secret("app", password_key, password)
        return password

    def _get_or_generate_username(self, event_relation_id: int) -> str:
        """Retrieve username from databag or config or generate a new one.

        Assumes that the caller is the leader unit.
        """
        return self.charm.app_peer_data.setdefault(
            MYSQL_RELATION_USER_KEY,
            self.charm.config.mysql_interface_user or f"relation-{event_relation_id}",
        )

    def _get_or_generate_database(self, event_relation_id: int) -> str:
        """Retrieve database from databag or config or generate a new one.

        Assumes that the caller is the leader unit.
        """
        return self.charm.app_peer_data.setdefault(
            MYSQL_RELATION_DATABASE_KEY,
            self.charm.config.mysql_interface_database or f"database-{event_relation_id}",
        )

    def _on_leader_elected(self, _) -> None:
        """Handle the leader elected event.

        Retrieves relation data from the peer relation databag and copies
        the relation data into the new leader unit's databag.
        """
        # Skip if the charm is not past the setup phase (config-changed event not executed yet)
        if not self.charm._is_peer_data_set:
            return

        relation_data = json.loads(self.charm.app_peer_data.get(MYSQL_RELATION_DATA_KEY, "{}"))

        for relation in self.charm.model.relations.get(LEGACY_MYSQL, []):
            relation_databag = relation.data

            # Copy relation data into the new leader unit's databag
            for key, value in relation_data.items():
                if relation_databag[self.charm.unit].get(key) != value:
                    relation_databag[self.charm.unit][key] = value

            # Assign the cluster primary's address as the database host
            try:
                primary_address = self.charm._mysql.get_cluster_primary_address()
            except MySQLGetClusterPrimaryAddressError:
                logger.debug("First leader elected run, bailing out.")
                return

            if not primary_address:
                self.charm.unit.status = BlockedStatus(
                    "Failed to retrieve cluster primary address"
                )
                return

            primary_address_ip = socket.gethostbyname(primary_address.split(":")[0])

            relation_databag[self.charm.unit]["host"] = primary_address_ip

    def _on_config_changed(self, _) -> None:
        """Handle the change of the username/database in config."""
        if not self.charm.unit.is_leader():
            return

        if not (
            self.charm.app_peer_data.get(MYSQL_RELATION_USER_KEY)
            and self.charm.app_peer_data.get(MYSQL_RELATION_DATABASE_KEY)
        ):
            return

        if isinstance(self.charm.unit.status, ActiveStatus) and self.model.relations.get(
            LEGACY_MYSQL
        ):
            if (
                self.charm.config.mysql_interface_database
                != self.charm.app_peer_data[MYSQL_RELATION_DATABASE_KEY]
                or self.charm.config.mysql_interface_user
                != self.charm.app_peer_data[MYSQL_RELATION_USER_KEY]
            ):
                self.charm.app.status = BlockedStatus(
                    "Remove and re-relate `mysql` relations in order to change config"
                )

    def _on_mysql_relation_created(self, event: RelationCreatedEvent) -> None:
        """Handle the legacy `mysql` relation created event.

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

        # wait until the unit is initialized
        if not self.charm.unit_initialized:
            event.defer()
            return

        logger.warning("DEPRECATION WARNING - `mysql` is a legacy interface")

        username = self._get_or_generate_username(event.relation.id)
        database = self._get_or_generate_database(event.relation.id)

        try:
            user_exists = self.charm._mysql.does_mysql_user_exist(username, "%")
        except MySQLCheckUserExistenceError:
            self.charm.unit.status = BlockedStatus("Failed to check user existence")
            return

        # Only execute if the application user does not exist
        # since it could have been created by another related app
        if user_exists:
            mysql_relation_data = self.charm.app_peer_data[MYSQL_RELATION_DATA_KEY]

            updates = json.loads(mysql_relation_data)
            event.relation.data[self.charm.unit].update(updates)

            return

        password = self._get_or_set_password_in_peer_secrets(username)

        try:
            self.charm._mysql.create_application_database_and_scoped_user(
                database,
                username,
                password,
                "%",
                unit_name="mysql-legacy-relation",
            )

            primary_address = self.charm._mysql.get_cluster_primary_address()

        except (
            MySQLCreateApplicationDatabaseAndScopedUserError,
            MySQLGetClusterPrimaryAddressError,
        ):
            self.charm.unit.status = BlockedStatus("Failed to initialize `mysql` relation")
            return

        if not primary_address:
            self.charm.unit.status = BlockedStatus("Failed to retrieve cluster primary address")
            return

        primary_address_ip = socket.gethostbyname(primary_address.split(":")[0])

        updates = {
            "database": database,
            "host": primary_address_ip,
            "password": password,
            "port": "3306",
            "root_password": self.charm.get_secret("app", ROOT_PASSWORD_KEY),
            "user": username,
        }

        event.relation.data[self.charm.unit].update(updates)

        self.charm.app_peer_data[MYSQL_RELATION_USER_KEY] = username
        self.charm.app_peer_data[MYSQL_RELATION_DATABASE_KEY] = database

        # Store the relation data into the peer relation databag
        self.charm.app_peer_data[MYSQL_RELATION_DATA_KEY] = json.dumps(updates)

    def _on_mysql_relation_broken(self, event: RelationBrokenEvent) -> None:
        """Handle the `mysql` legacy relation broken event.

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
            return

        del self.charm.app_peer_data[MYSQL_RELATION_USER_KEY]
        del self.charm.app_peer_data[MYSQL_RELATION_DATABASE_KEY]

        del self.charm.app_peer_data[MYSQL_RELATION_DATA_KEY]

        if isinstance(
            self.charm.app.status, BlockedStatus
        ) and self.charm.app.status.message.startswith(
            "Remove `mysql` relations in order to change"
        ):
            self.charm.app.status = ActiveStatus()
