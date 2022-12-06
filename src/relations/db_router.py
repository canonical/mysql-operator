# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Library containing the implementation of the legacy db-router relation."""

import json
import logging
from collections import namedtuple
from typing import Dict, List, Set, Tuple

from charms.mysql.v0.mysql import (
    MySQLCheckUserExistenceError,
    MySQLConfigureRouterUserError,
    MySQLCreateApplicationDatabaseAndScopedUserError,
    MySQLDeleteUsersForUnitError,
    MySQLGetClusterPrimaryAddressError,
)
from ops.charm import (
    CharmBase,
    LeaderElectedEvent,
    RelationChangedEvent,
    RelationDepartedEvent,
)
from ops.framework import Object
from ops.model import BlockedStatus, RelationDataContent

from constants import LEGACY_DB_ROUTER, PASSWORD_LENGTH
from utils import generate_random_password

logger = logging.getLogger(__name__)

RequestedUser = namedtuple(
    "RequestedUser", ["application_name", "username", "hostname", "database"]
)


class DBRouterRelation(Object):
    """Encapsulation of the legacy db-router relation."""

    def __init__(self, charm: CharmBase):
        super().__init__(charm, LEGACY_DB_ROUTER)

        self.charm = charm

        self.framework.observe(self.charm.on.leader_elected, self._on_leader_elected)
        self.framework.observe(
            self.charm.on[LEGACY_DB_ROUTER].relation_changed, self._on_db_router_relation_changed
        )
        self.framework.observe(
            self.charm.on[LEGACY_DB_ROUTER].relation_departed, self._on_db_router_relation_departed
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

    def _get_requested_users_from_relation_databag(
        self, db_router_databag: RelationDataContent
    ) -> List[RequestedUser]:
        """Retrieve requested user information from the db-router relation databag.

        Args:
            db_router_databag: The databag for the 'db-router' relation

        Returns:
            A list of RequestedUsers (a named tuple containing information about requested users)
        """
        requested_users = []

        # Retrieve application names in the relation databag (which correspond to usernames)
        # Keys that include an _ are generally the ones set by the mysqlrouter legacy charm
        application_names = set(
            [
                key.split("_")[0]
                for key in db_router_databag
                if "_" in key and "username" == key.split("_")[1]
            ]
        )

        for application_name in application_names:
            username = db_router_databag.get(f"{application_name}_username")
            hostname = db_router_databag.get(f"{application_name}_hostname")
            database = db_router_databag.get(f"{application_name}_database")

            if (
                not username
                or not hostname
                or (application_name != "mysqlrouter" and not database)
            ):
                logger.warning(
                    f"Missing information to creata a database and scoped user for {application_name}"
                )
                continue

            requested_users.append(RequestedUser(application_name, username, hostname, database))

        return requested_users

    def _create_requested_users(
        self, requested_users: List[RequestedUser], user_unit_name: str
    ) -> Tuple[Dict[str, str], Set[str]]:
        """Create the requested users and said user scoped databases.

        Args:
            requested_users: A list of RequestedUser
                (named tuples containing user and database info)
            user_unit_name: Name of unit from which the requested users will be accessed from

        Returns:
            tuple containing a dictionary of application_name to password
                and a list of requested user applications

        Raises:
            MySQLCheckUserExistenceError if there is an issue checking a user's existence
            MySQLConfigureRouterUserError if there is an issue configuring the mysqlrouter user
            MySQLCreateApplicationDatabaseAndScopedUserError if there is an issue creating a
                user or said user scoped database
        """
        user_passwords = {}
        requested_user_applications = set()

        for requested_user in requested_users:
            password = self._get_or_set_password_in_peer_databag(requested_user.username)

            if not self.charm._mysql.does_mysql_user_exist(
                requested_user.username, requested_user.hostname
            ):
                if requested_user.application_name == "mysqlrouter":
                    self.charm._mysql.configure_mysqlrouter_user(
                        requested_user.username, password, requested_user.hostname, user_unit_name
                    )
                else:
                    self.charm._mysql.create_application_database_and_scoped_user(
                        requested_user.database,
                        requested_user.username,
                        password,
                        requested_user.hostname,
                        user_unit_name,
                    )

            user_passwords[requested_user.application_name] = password
            requested_user_applications.add(requested_user.application_name)

        return user_passwords, requested_user_applications

    def _on_leader_elected(self, event: LeaderElectedEvent) -> None:
        """Handle the leader elected event.

        Copy data from the relation's application databag to the leader unit databag
        since legacy applications expect credential data to be populated on the leader
        unit databag.
        """
        # Skip if the charm is not past the setup phase (config-changed event not executed yet)
        if not self.charm._is_peer_data_set:
            return

        relations = self.charm.model.relations.get(LEGACY_DB_ROUTER, [])
        if not relations:
            # Bypass run if no relation
            return

        try:
            primary_address = self._charm._mysql.get_cluster_primary_address().split(":")[0]
        except MySQLGetClusterPrimaryAddressError:
            logger.error("Can't get primary address. Deferring")
            event.defer()
            return

        for relation in relations:
            relation_databag = relation.data

            # Copy data from the application databag into the leader unit's databag
            for key, value in relation_databag.get(self.charm.app, {}).items():
                if relation_databag[self.charm.unit].get(key) != value:
                    relation_databag[self.charm.unit][key] = value

            # Update the db host as the cluster primary may have changed
            relation_databag[self.charm.unit]["db_host"] = json.dumps(primary_address)
            relation_databag[self.charm.app]["db_host"] = json.dumps(primary_address)

    def _on_db_router_relation_changed(self, event: RelationChangedEvent) -> None:
        """Handle the db-router relation changed event.

        Designed to be idempotent, the handler will execute only on the leader unit.
        It will generate any requested users and scoped databases, and share the
        credentials via the leader unit databag.
        """
        if not self.charm.unit.is_leader():
            return

        logger.warning("DEPRECATION WARNING - `db-router` is a legacy interface")

        changed_unit_databag = event.relation.data.get(event.unit)
        if not changed_unit_databag:
            # Guard against relating and unrelating too fast
            logger.warning("No data found for remote relation. Was the relation removed?")
            return

        changed_unit_name = event.unit.name
        requested_users = self._get_requested_users_from_relation_databag(changed_unit_databag)

        try:
            requested_user_passwords, requested_user_applications = self._create_requested_users(
                requested_users, changed_unit_name
            )
        except (
            MySQLCheckUserExistenceError,
            MySQLConfigureRouterUserError,
            MySQLCreateApplicationDatabaseAndScopedUserError,
        ):
            self.charm.unit.status = BlockedStatus("Failed to create app user or scoped database")
            return

        # All values consumed by the legacy mysqlrouter charm are expected to be json encoded
        databag_updates = {}
        for application_name, password in requested_user_passwords.items():
            databag_updates[f"{application_name}_password"] = json.dumps(password)

        application_databag = event.relation.data[self.charm.app]
        unit_databag = event.relation.data[self.charm.unit]

        for application_name in requested_user_applications:
            application_allowed_units = set(
                json.loads(unit_databag.get(f"{application_name}_allowed_units", '""')).split()
            )
            application_allowed_units.add(changed_unit_name)
            databag_updates[f"{application_name}_allowed_units"] = json.dumps(
                " ".join(application_allowed_units)
            )

        primary_address = self.charm._mysql.get_cluster_primary_address().split(":")[0]
        databag_updates["db_host"] = json.dumps(primary_address)

        # Copy the databag_updates to both the leader unit databag
        # as well as the application databag (so it can be copied to a
        # new leader in the case that a new leader is elected)
        for key, value in databag_updates.items():
            if unit_databag.get(key) != value:
                unit_databag[key] = value

            if application_databag.get(key) != value:
                application_databag[key] = value

    def _on_db_router_relation_departed(self, event: RelationDepartedEvent) -> None:
        """Handle the legacy db_router relation departed event.

        Ensure that the <app_user>_allowed_units relation data is correctly reflected.
        Also clean up users for the departing unit created by this charm.
        """
        # Only execute if the departing unit is from the remote related application
        if self.charm.app.name == event.departing_unit.app.name:
            return

        if not self.charm.unit.is_leader():
            return

        logger.warning("DEPRECATION WARNING - `db-router` is a legacy interface")

        # Remove departing unit's name from any key in the databag of the form "_allowed_units"
        departing_unit_name = event.departing_unit.name
        leader_db_router_databag = event.relation.data[self.charm.unit]

        for key in leader_db_router_databag:
            if "_allowed_units" in key:
                allowed_units = set(json.loads(leader_db_router_databag[key]).split())
                allowed_units.discard(departing_unit_name)

                leader_db_router_databag[key] = json.dumps(" ".join(allowed_units))

        try:
            self.charm._mysql.delete_users_for_unit(departing_unit_name)
        except MySQLDeleteUsersForUnitError:
            self.charm.unit.status = BlockedStatus("Failed to delete users for departing unit")
