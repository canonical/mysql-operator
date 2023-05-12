# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Library containing the implementation of the standard relation."""

import logging

from charms.data_platform_libs.v0.data_interfaces import (
    DatabaseProvides,
    DatabaseRequestedEvent,
)
from charms.mysql.v0.mysql import (
    MySQLClientError,
    MySQLCreateApplicationDatabaseAndScopedUserError,
    MySQLDeleteUserError,
    MySQLDeleteUsersForRelationError,
    MySQLGetClusterEndpointsError,
    MySQLGetClusterMembersAddressesError,
    MySQLGetMySQLVersionError,
    MySQLGrantPrivilegesToUserError,
    MySQLRemoveRouterFromMetadataError,
)
from ops.charm import RelationBrokenEvent, RelationDepartedEvent, RelationJoinedEvent
from ops.framework import Object
from ops.model import BlockedStatus

from constants import DB_RELATION_NAME, PASSWORD_LENGTH, PEER
from utils import generate_random_password

logger = logging.getLogger(__name__)


class MySQLProvider(Object):
    """Standard database relation class."""

    def __init__(self, charm):
        super().__init__(charm, DB_RELATION_NAME)

        self.charm = charm

        self.database = DatabaseProvides(self.charm, relation_name=DB_RELATION_NAME)
        self.framework.observe(self.database.on.database_requested, self._on_database_requested)

        self.framework.observe(
            self.charm.on[DB_RELATION_NAME].relation_broken, self._on_database_broken
        )
        self.framework.observe(
            self.charm.on[DB_RELATION_NAME].relation_departed,
            self._on_database_provides_relation_departed,
        )
        self.framework.observe(self.charm.on[PEER].relation_joined, self._on_relation_joined)
        self.framework.observe(self.charm.on[PEER].relation_departed, self._on_relation_departed)

        self.framework.observe(self.charm.on.leader_elected, self._update_endpoints_all_relations)
        self.framework.observe(self.charm.on.update_status, self._update_endpoints_all_relations)

    def _update_endpoints_all_relations(self, _):
        """Update endpoints for all relations."""
        if not self.charm.unit.is_leader():
            return
        # get all relations involving the database relation
        relations = list(self.model.relations[DB_RELATION_NAME])
        # check if there are relations in place
        if len(relations) == 0:
            return

        if not self.charm.cluster_initialized or not self.charm.unit_peer_data.get(
            "unit-initialized"
        ):
            logger.debug("Waiting cluster/unit to be initialized")
            return

        relation_data = self.database.fetch_relation_data()
        # for all relations update the read-only-endpoints
        for relation in relations:
            # check if the on_database_requested has been executed
            if relation.id not in relation_data:
                logger.debug("On database requested not happened yet! Nothing to do in this case")
                continue
            self._update_endpoints(relation.id, relation.app.name)

    def _on_relation_departed(self, event: RelationDepartedEvent):
        """Handle the peer relation departed event for the database relation."""
        if not self.charm.unit.is_leader():
            return
        # get all relations involving the database relation
        relations = list(self.model.relations[DB_RELATION_NAME])
        if len(relations) == 0:
            return

        if not self.charm.cluster_initialized:
            logger.debug("Waiting cluster to be initialized")
            return

        # check if the leader is departing
        if self.charm.unit.name == event.departing_unit.name:
            return

        # get unit name that departed
        dep_unit_name = event.departing_unit.name.replace("/", "-")

        # defer if the added unit is still in the cluster
        if self.charm._mysql.is_instance_in_cluster(dep_unit_name):
            logger.debug(f"Departing unit {dep_unit_name} is still in the cluster!")
            event.defer()
            return

        relation_data = self.database.fetch_relation_data()
        # for all relations update the read-only-endpoints
        for relation in relations:
            # check if the on_database_requested has been executed
            if relation.id not in relation_data:
                logger.debug("On database requested not happened yet! Nothing to do in this case")
                continue
            # update the endpoints
            self._update_endpoints(relation.id, event.app.name)

    def _on_relation_joined(self, event: RelationJoinedEvent):
        """Handle the peer relation joined event for the database relation."""
        if not self.charm.unit.is_leader():
            return
        # get all relations involving the database relation
        relations = list(self.model.relations[DB_RELATION_NAME])

        if len(relations) == 0:
            return

        if not self.charm.cluster_initialized:
            logger.debug("Waiting cluster to be initialized")
            return

        # get unit name that joined
        event_unit_label = event.unit.name.replace("/", "-")

        # defer if the added unit is not in the cluster
        if not self.charm._mysql.is_instance_in_cluster(event_unit_label):
            event.defer()
            return
        relation_data = self.database.fetch_relation_data()
        # for all relations update the read-only-endpoints
        for relation in relations:
            # check if the on_database_requested has been executed
            if relation.id not in relation_data:
                logger.debug("On database requested not happened yet! Nothing to do in this case")
                continue
            # update the endpoints
            self._update_endpoints(relation.id, event.app.name)

    def _update_endpoints(self, relation_id: int, remote_app: str) -> None:
        """Updates the endpoints, checking for necessity.

        Args:
            relation_id (int): The id of the relation
            remote_app (str): The name of the remote application
        """
        try:
            rw_endpoints, ro_endpoints, _ = self.charm._mysql.get_cluster_endpoints()

            # check if endpoints need update
            relation = self.model.get_relation(DB_RELATION_NAME, relation_id)
            relation_data = relation.data[self.charm.app]
            if (
                relation_data.get("endpoints") == rw_endpoints
                and relation_data.get("read-only-endpoints") == ro_endpoints
            ):
                logger.debug(f"Endpoints haven't changed for {remote_app}, skip update.")
                return

            self.database.set_endpoints(relation_id, rw_endpoints)
            self.database.set_read_only_endpoints(relation_id, ro_endpoints)
            logger.debug(f"Updated endpoints for {remote_app}")

        except MySQLGetClusterEndpointsError as e:
            logger.exception("Failed to get cluster members", exc_info=e)

    def _get_or_set_password(self, relation) -> str:
        """Retrieve password from cache or generate a new one.

        Args:
            relation (str): The relation for each the password is cached.

        Returns:
            str: The password.
        """
        if password := relation.data[self.charm.app].get("password"):
            return password
        password = generate_random_password(PASSWORD_LENGTH)
        relation.data[self.charm.app]["password"] = password
        return password

    def _on_database_requested(self, event: DatabaseRequestedEvent):
        """Handle the `database-requested` event."""
        if not self.charm.unit.is_leader():
            return
        # check if cluster is ready and if not, defer
        if not self.charm.cluster_initialized:
            logger.debug("Waiting cluster to be initialized")
            event.defer()
            return

        # get base relation data
        relation_id = event.relation.id
        db_name = event.database
        extra_user_roles = []
        if event.extra_user_roles:
            extra_user_roles = event.extra_user_roles.split(",")
        # user name is derived from the relation id
        db_user = f"relation-{relation_id}"
        db_pass = self._get_or_set_password(event.relation)

        remote_app = event.app.name

        try:
            db_version = self.charm._mysql.get_mysql_version()
            rw_endpoints, ro_endpoints, _ = self.charm._mysql.get_cluster_endpoints()
            self.database.set_database(relation_id, db_name)
            self.database.set_credentials(relation_id, db_user, db_pass)
            self.database.set_endpoints(relation_id, rw_endpoints)
            self.database.set_version(relation_id, db_version)
            self.database.set_read_only_endpoints(relation_id, ro_endpoints)
            # TODO:
            # add setup of tls, tls_ca and status
            self.charm._mysql.create_application_database_and_scoped_user(
                db_name, db_user, db_pass, "%"
            )

            if "mysqlrouter" in extra_user_roles:
                self.charm._mysql.grant_privileges_to_user(
                    db_user, "%", ["ALL PRIVILEGES"], with_grant_option=True
                )

            logger.info(f"Created user for app {remote_app}")
        except (
            MySQLCreateApplicationDatabaseAndScopedUserError,
            MySQLGetMySQLVersionError,
            MySQLGetClusterMembersAddressesError,
            MySQLGrantPrivilegesToUserError,
            MySQLClientError,
        ) as e:
            logger.exception("Failed to set up database relation", exc_info=e)
            self.charm.unit.status = BlockedStatus("Failed to set up relation")

    def _on_database_broken(self, event: RelationBrokenEvent) -> None:
        """Handle the removal of database relation.

        Remove user, keeping database intact.
        """
        if not self.charm.unit.is_leader():
            # run once by the leader
            return

        if self.charm.unit_peer_data.get("unit-status", None) == "removing":
            # safeguard against relation broken being triggered for
            # a unit being torn down (instead of un-related)
            # https://github.com/canonical/mysql-operator/issues/32
            return

        try:
            relation_id = event.relation.id
            self.charm._mysql.delete_users_for_relation(relation_id)
            logger.info(f"Removed user for relation {relation_id}")
        except (MySQLDeleteUsersForRelationError, KeyError):
            logger.error(f"Failed to delete user for relation {relation_id}")
            return

    def _on_database_provides_relation_departed(self, event: RelationDepartedEvent) -> None:
        """Remove MySQL Router cluster metadata & user for departing unit."""
        if not self.charm.unit.is_leader():
            return
        if event.departing_unit.app.name == self.charm.app.name:
            return

        users = self.charm._mysql.get_mysql_router_users_for_unit(
            relation_id=event.relation.id, mysql_router_unit_name=event.departing_unit.name
        )
        if not users:
            return

        if len(users) > 1:
            logger.error(
                f"More than one router user for departing unit {event.departing_unit.name}"
            )
            return

        user = users[0]
        try:
            self.charm._mysql.delete_user(user.username)
            logger.info(f"Deleted router user {user.username}")
        except MySQLDeleteUserError:
            logger.error(f"Failed to delete user {user.username}")
        try:
            self.charm._mysql.remove_router_from_cluster_metadata(user.router_id)
            logger.info(f"Removed router from metadata {user.router_id}")
        except MySQLRemoveRouterFromMetadataError:
            logger.error(f"Failed to remove router from metadata with ID {user.router_id}")
