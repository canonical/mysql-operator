# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Library containing the implementation of the legacy db-router relation."""

import json
import logging

from charms.mysql.v0.mysql import (
    MySQLCheckUserExistenceError,
    MySQLConfigureRouterUserError,
    MySQLCreateApplicationDatabaseAndScopedUserError,
    MySQLRemoveDatabaseError,
)
from ops.charm import (
    RelationBrokenEvent,
    RelationChangedEvent,
    RelationDepartedEvent,
    RelationJoinedEvent,
)
from ops.framework import Object
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus

from constants import LEGACY_DB_ROUTER, PASSWORD_LENGTH, PEER
from utils import generate_random_password

logger = logging.getLogger(__name__)


class DBRouterRelation(Object):
    """Encapsulation of the legacy db-router relation."""

    def __init__(self, charm):
        super().__init__(charm)

        self.framework.observe(
            charm.on[LEGACY_DB_ROUTER].relation_joined, self._on_db_router_relation_joined
        )
        self.framework.observe(
            charm.on[LEGACY_DB_ROUTER].relation_changed, self._on_db_router_relation_changed
        )
        self.framework.observe(
            charm.on[LEGACY_DB_ROUTER].relation_departed, self._on_db_router_relation_departed
        )
        self.framework.observe(
            charm.on[LEGACY_DB_ROUTER].relation_broken, self._on_db_router_relation_broken
        )

    def _on_db_router_relation_joined(self, event: RelationJoinedEvent) -> None:
        """Handle the legacy db_router relation joined event.

        Ensure that the <app_user>_allowed_units relation data is correctly reflected.
        """
        if not self.unit.is_leader():
            return

        logger.warning("DEPRECATION WARNING - `db-router` is a legacy interface")

        # Add the joining unit's name for any key in the databag of the form "_allowed_units"
        joining_unit_name = event.unit.name
        leader_db_router_databag = event.relation.data[self.unit]

        for key in leader_db_router_databag:
            if "_allowed_units" in key:
                allowed_units = set(json.loads(leader_db_router_databag[key]).split())
                allowed_units.add(joining_unit_name)

                leader_db_router_databag[key] = json.dumps(" ".join(allowed_units))

    def _on_db_router_relation_changed(self, event: RelationChangedEvent) -> None:
        """Handle the db_router relation changed event."""
        if not self.unit.is_leader():
            return

        logger.warning("DEPRECATION WARNING - `db-router` is a legacy interface")

        self.unit.status = MaintenanceStatus("Setting up db-router relation")

        # Get the application data from the relation databag
        # Abstracted is the fact that it is received from the leader unit of the related app
        unit_address = str(self.model.get_binding(PEER).network.bind_address)
        unit_names = " ".join([unit.name for unit in event.relation.units])

        event_relation_databag = event.relation.data[self.unit]
        event_relation_databag["db_host"] = json.dumps(unit_address)

        application_unit = list(event.relation.units)[0]
        application_data = event.relation.data[application_unit]

        # Retrieve application names in the relation databag (which correspond to usernames)
        # Keys that include an _ are generally the ones set by the mysqlrouter legacy charm
        application_names = set(
            [
                key.split("_")[0]
                for key in application_data
                if "_" in key and "username" == key.split("_")[1]
            ]
        )

        for index, application_name in enumerate(application_names):
            username = application_data.get(f"{application_name}_username")
            database = application_data.get(f"{application_name}_database")

            if not username or (application_name != "mysqlrouter" and not database):
                logger.warning(
                    f"Missing information for application {application_name} to create a database and scoped user"
                )
                continue

            try:
                password = generate_random_password(PASSWORD_LENGTH)

                # Bootstrap the mysql router user
                if application_name == "mysqlrouter":
                    mysqlrouter_user_exists = self._mysql.does_mysql_user_exist(username)
                    if not mysqlrouter_user_exists:
                        self._mysql.configure_mysqlrouter_user(username, password)
                        event_relation_databag["mysqlrouter_password"] = json.dumps(password)

                        # Store the mysqlrouter username to be able to query and remove
                        # it when relation is broken
                        event_relation_databag[
                            f"relation_id_{event.relation.id}_mysqlrouter_username"
                        ] = username

                    # Update the allowed units in case a new unit joins the relation
                    event_relation_databag["mysqlrouter_allowed_units"] = json.dumps(unit_names)

                    continue

                # Create an application database and an application user scoped to that database
                if not self._mysql.does_mysql_user_exist(username):
                    self._mysql.create_application_database_and_scoped_user(
                        database,
                        username,
                        password,
                    )

                    event_relation_databag[f"{application_name}_password"] = json.dumps(password)

                    # store application username and database to be able to query and
                    # remove them when relation is broken
                    event_relation_databag[
                        f"relation_id_{event.relation.id}_app_user_{index}"
                    ] = username
                    event_relation_databag[
                        f"relation_id_{event.relation.id}_app_db_name_{index}"
                    ] = database

                # Update the allowed units in case a new unit joins the relation
                event_relation_databag[f"{application_name}_allowed_units"] = json.dumps(
                    unit_names
                )
            except (
                MySQLCheckUserExistenceError,
                MySQLConfigureRouterUserError,
                MySQLCreateApplicationDatabaseAndScopedUserError,
            ):
                self.unit.status = BlockedStatus("Failed to initialize db-router relation")
                return

        self.unit.status = ActiveStatus()

    def _on_db_router_relation_departed(self, event: RelationDepartedEvent) -> None:
        """Handle the legacy db_router relation departed event.

        Ensure that the <app_user>_allowed_units relation data is correctly reflected.
        """
        if not self.unit.is_leader():
            return

        logger.warning("DEPRECATION WARNING - `db-router` is a legacy interface")

        # Remove departing unit's name from any key in the databag of the form "_allowed_units"
        departing_unit_name = event.departing_unit.name
        leader_db_router_databag = event.relation.data[self.unit]

        for key in leader_db_router_databag:
            if "_allowed_units" in key:
                allowed_units = json.loads(leader_db_router_databag[key]).split()
                allowed_units.remove(departing_unit_name)

                leader_db_router_databag[key] = json.dumps(" ".join(allowed_units))

    def _on_db_router_relation_broken(self, event: RelationBrokenEvent) -> None:
        """Handle the legacy db_router relation broken event.

        Clean up the mysqlrouter user, and any application users and databases.
        """
        if not self.unit.is_leader():
            return

        leader_db_router_databag = event.relation.data[self.app]

        app_username_prefix = f"relation_id_{event.relation.id}_app_user_"
        app_database_prefix = f"relation_id_{event.relation.id}_app_db_name_"
        for key in leader_db_router_databag:
            try:
                if key.startswith(app_username_prefix):
                    app_username = leader_db_router_databag[key]
                    self._mysql.remove_user(app_username)

                if self.config.get("auto-delete", False) and key.startswith(app_database_prefix):
                    app_database_name = leader_db_router_databag[key]
                    self._mysql.remove_database(app_database_name)
            except MySQLRemoveDatabaseError:
                self.unit.status = BlockedStatus("Failed to remove users")
                return

        mysql_router_username = leader_db_router_databag[
            f"relation_id_{event.relation.id}_mysqlrouter_username"
        ]
        try:
            self._mysql.remove_user(mysql_router_username)
        except MySQLRemoveDatabaseError:
            self.unit.status = BlockedStatus("Failed to remove mysqlrouter user")
