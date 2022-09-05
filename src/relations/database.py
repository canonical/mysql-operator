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
    MySQLGetClusterMembersAddressesError,
    MySQLGetMySQLVersionError,
    MySQLGrantPrivilegesToUserError,
    MySQLUpgradeUserForMySQLRouterError,
)

from ops.charm import RelationDepartedEvent, RelationJoinedEvent, RelationEvent, RelationBrokenEvent
from ops.framework import Object
from ops.model import BlockedStatus

from constants import DB_RELATION_NAME, PASSWORD_LENGTH, PEER
from utils import generate_random_password

logger = logging.getLogger(__name__)


class DatabaseRelation(Object):
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
            self.charm.on[PEER].relation_joined, self._on_relation_joined
        )
        self.framework.observe(
            self.charm.on[PEER].relation_departed, self._on_relation_departed
        )
    
    def _on_relation_departed(self, event: RelationDepartedEvent):
        """Handle the peer relation departed event for the database relation."""
        if not self.charm.unit.is_leader():
            return
        # get all relations involving the database relation
        relations = list(self.model.relations[DB_RELATION_NAME])
        logger.info(f"Number of relations: {len(relations)}")
        if len(relations) == 0:
            return

        if not self.charm.cluster_initialized:
            logger.debug("Waiting cluster to be initialized")
            return
        
        logger.info(f"self charm: {self.charm.unit.name} and departing unit: {event.departing_unit.name}")
        # check if the leader is departing
        logger.info(f"is leader leaving: {self.charm.unit.name == event.departing_unit.name}")
        if self.charm.unit.name == event.departing_unit.name:
            event.defer()
            return

        # get unit name that departed
        dep_unit_name = event.departing_unit.name.replace("/", "-")
        
        # differ if the added unit is still in the cluster
        if self.charm._mysql.is_instance_in_cluster(dep_unit_name):
            logger.info(f"Departing unit {dep_unit_name} is still in the cluster!")
            event.defer()
            return
        
        relation_data = self.database.fetch_relation_data()
        # for all relations update the read-only-endpoints
        for relation in relations:
            # check if the on_database_requested has been executed
            if relation.id not in relation_data:
                logger.info("On database requested not happened yet! Nothing to do in this case")
                continue
            # update the endpoints
            self._update_endpoints(relation.id, event)


    def _on_relation_joined(self, event: RelationJoinedEvent):
        """Handle the peer relation joined event for the database relation."""
        if not self.charm.unit.is_leader():
            return
        # get all relations involving the database relation
        relations = list(self.model.relations[DB_RELATION_NAME])
        logger.info(f"Number of relations: {len(relations)}")
        if len(relations) == 0:
            return

        if not self.charm.cluster_initialized:
            logger.debug("Waiting cluster to be initialized")
            return
         
        # get unit name that joined
        event_unit_label = event.unit.name.replace("/", "-")    

        # differ if the added unit is not in the cluster
        if not self.charm._mysql.is_instance_in_cluster(event_unit_label):
            logger.info(f"Added unit {event_unit_label} it is not part of the cluster: differ!")
            event.defer()
            return
        relation_data = self.database.fetch_relation_data()
        # for all relations update the read-only-endpoints
        for relation in relations:
            # check if the on_database_requested has been executed
            if relation.id not in relation_data:
                logger.info("On database requested not happened yet! Nothing to do in this case")
                continue
            # update the endpoints
            self._update_endpoints(relation.id, event)


    def _update_endpoints(self, relation_id: int, event: RelationEvent):
        """Update the read-only-endpoints

        Args:
            relation_id (int): The id of the relation 
            event (RelationEvent): the triggered event

        """
        remote_app = event.app.name
        logger.info("Start endpoint update: ")
        try:

            primary_endpoint = self.charm._mysql.get_cluster_primary_address()
            self.database.set_endpoints(relation_id, primary_endpoint)
            # get read only endpoints by removing primary from all members
            read_only_endpoints = sorted(
                self.charm._mysql.get_cluster_members_addresses()
                - {
                    primary_endpoint,
                }
            )
            self.database.set_read_only_endpoints(relation_id, ",".join(read_only_endpoints))
            logger.debug(f"Updated endpoints for {remote_app}")

        except MySQLCreateApplicationDatabaseAndScopedUserError:
            logger.error(f"Failed to create scoped user for app {remote_app}")
            self.charm.unit.status = BlockedStatus("Failed to create scoped user")
        except MySQLGetMySQLVersionError as e:
            logger.exception("Failed to get MySQL version", exc_info=e)
            self.charm.unit.status = BlockedStatus("Failed to get MySQL version")
        except MySQLGetClusterMembersAddressesError as e:
            logger.exception("Failed to get cluster members", exc_info=e)
            self.charm.unit.status = BlockedStatus("Failed to get cluster members")
        except MySQLClientError as e:
            logger.exception("Failed to get primary", exc_info=e)
            self.charm.unit.status = BlockedStatus("Failed to get primary")

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
            primary_endpoint = self.charm._mysql.get_cluster_primary_address()
            self.database.set_credentials(relation_id, db_user, db_pass)
            self.database.set_endpoints(relation_id, primary_endpoint)
            self.database.set_version(relation_id, db_version)
            # get read only endpoints by removing primary from all members
            read_only_endpoints = sorted(
                self.charm._mysql.get_cluster_members_addresses()
                - {
                    primary_endpoint,
                }
            )

            self.database.set_read_only_endpoints(relation_id, ",".join(read_only_endpoints))
            # TODO:
            # add setup of tls, tls_ca and status
            # add extra roles parsing from relation data
            self.charm._mysql.create_application_database_and_scoped_user(
                db_name, db_user, db_pass, "%", remote_app
            )

            if "mysqlrouter" in extra_user_roles:
                self.charm._mysql.upgrade_user_for_mysqlrouter(db_user, "%")
                self.charm._mysql.grant_privileges_to_user(
                    db_user, "%", ["CREATE USER"], with_grant_option=True
                )

            logger.info(f"Created user for app {remote_app}")
        except (
            MySQLCreateApplicationDatabaseAndScopedUserError,
            MySQLGetMySQLVersionError,
            MySQLGetClusterMembersAddressesError,
            MySQLUpgradeUserForMySQLRouterError,
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

        if self.charm._peers.data[self.charm.unit].get("unit-status", None) == "removing":
            # safeguard against relation broken being triggered for
            # a unit being torn down (instead of un-related)
            # https://github.com/canonical/mysql-operator/issues/32
            return

        logger.info(f"On database broken!")
        try:
            relation_id = event.relation.id
            self.charm._mysql.delete_user_for_relation(relation_id)
            logger.info(f"Removed user for relation {relation_id}")
        except MySQLDeleteUserForRelationError:
            logger.error(f"Failed to delete user for relation {relation_id}")
            return
