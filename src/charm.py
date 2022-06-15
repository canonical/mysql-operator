#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charmed Machine Operator for MySQL."""

import hashlib
import json
import logging
import secrets
import string

from charms.mysql.v0.mysql import (
    MySQLCheckUserExistenceError,
    MySQLClientError,
    MySQLConfigureInstanceError,
    MySQLConfigureMySQLUsersError,
    MySQLConfigureRouterUserError,
    MySQLCreateApplicationDatabaseAndScopedUserError,
    MySQLCreateClusterError,
    MySQLInitializeJujuOperationsTableError,
    MySQLRemoveUserError,
)
from ops.charm import (
    ActionEvent,
    CharmBase,
    RelationBrokenEvent,
    RelationChangedEvent,
    RelationDepartedEvent,
    RelationJoinedEvent,
    StartEvent,
)
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus

from mysqlsh_helpers import MySQL

logger = logging.getLogger(__name__)

CLUSTER_ADMIN_USERNAME = "clusteradmin"
SERVER_CONFIG_USERNAME = "serverconfig"
PASSWORD_LENGTH = 24
PEER = "database-peers"
LEGACY_DB_ROUTER = "db-router"
LEGACY_DB_SHARED = "shared-db"


def generate_random_password(length: int) -> str:
    """Randomly generate a string intended to be used as a password.

    Args:
        length: length of the randomly generated string to be returned

    Returns:
        a string with random letters and digits of length specified
    """
    choices = string.ascii_letters + string.digits
    return "".join([secrets.choice(choices) for i in range(length)])


def generate_random_hash() -> str:
    """Generate a random hash.

    Returns:
        A random MD5 hash
    """
    random_characters = generate_random_password(20)
    return hashlib.md5(random_characters.encode("utf-8")).hexdigest()


class MySQLOperatorCharm(CharmBase):
    """Operator framework charm for MySQL."""

    def __init__(self, *args):
        super().__init__(*args)

        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.leader_elected, self._on_leader_elected)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.start, self._on_start)
        self.framework.observe(
            self.on.database_storage_detaching, self._on_database_storage_detaching
        )

        self.framework.observe(self.on[PEER].relation_joined, self._on_peer_relation_joined)
        self.framework.observe(self.on[PEER].relation_changed, self._on_peer_relation_changed)

        self.framework.observe(
            self.on[LEGACY_DB_ROUTER].relation_joined, self._on_db_router_relation_joined
        )
        self.framework.observe(
            self.on[LEGACY_DB_ROUTER].relation_changed, self._on_db_router_relation_changed
        )
        self.framework.observe(
            self.on[LEGACY_DB_ROUTER].relation_departed, self._on_db_router_relation_departed
        )

        self.framework.observe(
            self.on[LEGACY_DB_SHARED].relation_changed, self._on_shared_db_relation_changed
        )

        self.framework.observe(
            self.on[LEGACY_DB_SHARED].relation_broken, self._on_shared_db_broken
        )

        self.framework.observe(
            self.on.get_cluster_admin_credentials_action, self._on_get_cluster_admin_credentials
        )
        self.framework.observe(
            self.on.get_server_config_credentials_action, self._on_get_server_config_credentials
        )
        self.framework.observe(self.on.get_root_credentials_action, self._on_get_root_credentials)
        self.framework.observe(self.on.get_cluster_status_action, self._get_cluster_status)

    # =======================
    #  Charm Lifecycle Hooks
    # =======================

    def _on_install(self, _) -> None:
        """Handle the install event."""
        self.unit.status = MaintenanceStatus("Installing MySQL")

        # Initial setup operations like installing dependencies, and creating users and groups.
        try:
            MySQL.install_and_configure_mysql_dependencies()
        except Exception:
            self.unit.status = BlockedStatus("Failed to install and configure MySQL")
            return

        self.unit.status = WaitingStatus("Waiting to start MySQL")

    def _on_leader_elected(self, _) -> None:
        """Handle the leader elected event."""
        # Set MySQL config values in the peer relation databag
        peer_data = self._peers.data[self.app]

        required_passwords = ["root-password", "server-config-password", "cluster-admin-password"]

        for required_password in required_passwords:
            if not peer_data.get(required_password):
                password = generate_random_password(PASSWORD_LENGTH)
                peer_data[required_password] = password

    def _on_config_changed(self, _) -> None:
        """Handle the config changed event."""
        # Only execute on leader unit
        if not self.unit.is_leader():
            return

        # Set the cluster name in the peer relation databag if it is not already set
        peer_data = self._peers.data[self.app]

        if not peer_data.get("cluster-name"):
            peer_data["cluster-name"] = (
                self.config.get("cluster-name") or f"cluster_{generate_random_hash()}"
            )

    def _on_start(self, event: StartEvent) -> None:
        """Handle the start event."""
        # Configure MySQL users and the instance for use in an InnoDB cluster
        # Safeguard unit starting before leader unit sets peer data
        if not self._is_peer_data_set:
            event.defer()
            return

        self.unit.status = MaintenanceStatus("Setting up database cluster")

        try:
            self._mysql.configure_mysql_users()
            self._mysql.configure_instance()
            self._mysql.wait_until_mysql_connection()
        except MySQLConfigureMySQLUsersError:
            self.unit.status = BlockedStatus("Failed to initialize MySQL users")
            return
        except MySQLConfigureInstanceError:
            self.unit.status = BlockedStatus("Failed to configure instance for InnoDB")
            return

        # Create the cluster on the juju leader unit
        if not self.unit.is_leader():
            self.unit.status = WaitingStatus("Waiting to join the cluster")
            return

        try:
            unit_label = self.unit.name.replace("/", "-")
            self._mysql.create_cluster(unit_label)
            self._mysql.initialize_juju_units_operations_table()
        except MySQLCreateClusterError:
            self.unit.status = BlockedStatus("Failed to create the InnoDB cluster")
            return
        except MySQLInitializeJujuOperationsTableError:
            self.unit.status = BlockedStatus("Failed to initialize juju units operations table")
            return

        self._peers.data[self.app]["units-added-to-cluster"] = "1"

        self.unit.status = ActiveStatus()

    def _on_peer_relation_joined(self, event: RelationJoinedEvent) -> None:
        """Handle the peer relation joined event."""
        # Only execute in the unit leader
        if not self.unit.is_leader():
            return

        logger.warning("DEPRECATION WARNING - `db-router` is a legacy interface")

        # Defer if the instance is not configured for use in an InnoDB cluster
        # Every instance gets configured for use in an InnoDB cluster on start
        event_unit_address = event.relation.data[event.unit]["private-address"]
        event_unit_label = event.unit.name.replace("/", "-")

        if not self._mysql.is_instance_configured_for_innodb(event_unit_address, event_unit_label):
            event.defer()
            return

        # Add the instance to the cluster. This operation uses locks to ensure that
        # only one instance is added to the cluster at a time
        # (so only one instance is involved in a state transfer at a time)
        self._mysql.add_instance_to_cluster(event_unit_address, event_unit_label)

        # Update 'units-added-to-cluster' counter in the peer relation databag
        # in order to trigger a relation_changed event which will move the added unit
        # into ActiveStatus
        units_started = int(self._peers.data[self.app]["units-added-to-cluster"])
        self._peers.data[self.app]["units-added-to-cluster"] = str(units_started + 1)

    def _on_peer_relation_changed(self, event: RelationChangedEvent) -> None:
        """Handle the peer relation changed event."""
        # Only execute if peer relation data contains cluster config values
        if not self._is_peer_data_set:
            event.defer()
            return

        # Update the unit's status to ActiveStatus if it was added to the cluster
        unit_label = self.unit.name.replace("/", "-")
        if isinstance(self.unit.status, WaitingStatus) and self._mysql.is_instance_in_cluster(
            unit_label
        ):
            self.unit.status = ActiveStatus()

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

        for application_name in application_names:
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
            self.unit.status = ActiveStatus()
            return

        password = generate_random_password(PASSWORD_LENGTH)

        try:
            self._mysql.create_application_database_and_scoped_user(
                database_name, database_user, password
            )

            # set the relation data for consumption
            cluster_primary = str(self.model.get_binding(PEER).network.bind_address)

            unit_relation_databag["db_host"] = cluster_primary
            # Database port is static in legacy charm
            unit_relation_databag["db_port"] = "3306"
            # Wait timeout is a config option in legacy charm
            # defaulted to 3600 seconds
            unit_relation_databag["wait_timeout"] = "3600"
            unit_relation_databag["password"] = password

            unit_names = " ".join([unit.name for unit in event.relation.units])
            unit_relation_databag["allowed_units"] = unit_names

            # store username for relation in app databag
            # this is used to remove the user when the relation is broken
            app_relation_databag[f"relation_id_{event.relation.id}_db_user"] = database_user

        except (
            MySQLClientError,
            MySQLCreateApplicationDatabaseAndScopedUserError,
        ):
            self.unit.status = BlockedStatus("Failed to initialize shared_db relation")
            return

        self.unit.status = ActiveStatus()

    def _on_shared_db_broken(self, event: RelationBrokenEvent) -> None:
        """Handle the departure of legacy shared_db relation.

        Remove user created for the relation but keep the database.
        """
        if not self.unit.is_leader():
            return

        app_relation_databag = event.relation.data[self.app]
        username = app_relation_databag.get(f"relation_id_{event.relation.id}_db_user")

        if not username:
            # Can't do much if we don't have the username
            return

        try:
            # remove user and pop relation data from app databag
            self._mysql.remove_user(username)
            app_relation_databag.pop(f"relation_id_{event.relation.id}_db_user")
            logger.info(f"Removed user {username} from database.")
        except MySQLRemoveUserError:
            logger.warning(f"Failed to remove user {username} from database.")

    def _on_database_storage_detaching(self, _) -> None:
        """Handle the database storage detaching event."""
        # The following operation uses locks to ensure that only one instance is removed
        # from the cluster at a time (to avoid split-brain or lack of majority issues)
        unit_label = self.unit.name.replace("/", "-")
        self._mysql.remove_instance(unit_label)

    # =======================
    #  Custom Action Handlers
    # =======================

    def _on_get_cluster_admin_credentials(self, event: ActionEvent) -> None:
        """Action used to retrieve the cluster admin credentials."""
        event.set_results(
            {
                "cluster-admin-username": CLUSTER_ADMIN_USERNAME,
                "cluster-admin-password": self._peers.data[self.app].get(
                    "cluster-admin-password", "<to_be_generated>"
                ),
            }
        )

    def _on_get_server_config_credentials(self, event: ActionEvent) -> None:
        """Action used to retrieve the server config credentials."""
        event.set_results(
            {
                "server-config-username": SERVER_CONFIG_USERNAME,
                "server-config-password": self._peers.data[self.app].get(
                    "server-config-password", "<to_be_generated>"
                ),
            }
        )

    def _on_get_root_credentials(self, event: ActionEvent) -> None:
        """Action used to retrieve the root credentials."""
        event.set_results(
            {
                "root-username": "root",
                "root-password": self._peers.data[self.app].get(
                    "root-password", "<to_be_generated>"
                ),
            }
        )

    def _get_cluster_status(self, event: ActionEvent) -> None:
        """Action used to retrieve the cluster status."""
        event.set_results(self._mysql.get_cluster_status())

    # =======================
    #  Helpers
    # =======================

    @property
    def _mysql(self):
        """Returns an instance of the MySQL object from mysqlsh_helpers."""
        peer_data = self._peers.data[self.app]

        return MySQL(
            self.model.get_binding(PEER).network.bind_address,
            peer_data["cluster-name"],
            peer_data["root-password"],
            SERVER_CONFIG_USERNAME,
            peer_data["server-config-password"],
            CLUSTER_ADMIN_USERNAME,
            peer_data["cluster-admin-password"],
        )

    @property
    def _peers(self):
        """Retrieve the peer relation (`ops.model.Relation`)."""
        return self.model.get_relation(PEER)

    @property
    def _is_peer_data_set(self):
        peer_data = self._peers.data[self.app]

        return (
            peer_data.get("cluster-name")
            and peer_data.get("root-password")
            and peer_data.get("server-config-password")
            and peer_data.get("cluster-admin-password")
        )


if __name__ == "__main__":
    main(MySQLOperatorCharm)
