# Copyright 2022 Canonical Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""MySQL helper class and functions.

The `mysql` module provides an abstraction class and methods for for managing a
Group Replication enabled MySQL cluster.

The `MySQLBase` abstract class must be inherited and have its abstract methods
implemented for each platform (vm/k8s) before being directly used in charm code.

An example of inheriting `MySQLBase` and implementing the abstract methods plus extending it:

```python
from charms.mysql.v0.mysql import MySQLBase
from tenacity import retry, stop_after_delay, wait_fixed

class MySQL(MySQLBase):
    def __init__(
        self,
        instance_address: str,
        cluster_name: str,
        root_password: str,
        server_config_user: str,
        server_config_password: str,
        cluster_admin_user: str,
        cluster_admin_password: str,
        new_parameter: str
    ):
        super().__init__(
                instance_address=instance_address,
                cluster_name=cluster_name,
                root_password=root_password,
                server_config_user=server_config_user,
                server_config_password=server_config_password,
                cluster_admin_user=cluster_admin_user,
                cluster_admin_password=cluster_admin_password,
            )
        # Add new attribute
        self.new_parameter = new_parameter

    # abstract method implementation
    @retry(reraise=True, stop=stop_after_delay(30), wait=wait_fixed(5))
    def wait_until_mysql_connection(self) -> None:
        if not os.path.exists(MYSQLD_SOCK_FILE):
            raise MySQLServiceNotRunningError()

    ...
```

The module also provides a set of custom exceptions, used to trigger specific
error handling on the subclass and in the charm code.


"""

import json
import logging
import re
from abc import ABC, abstractmethod
from typing import List, Tuple

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_random

logger = logging.getLogger(__name__)

# The unique Charmhub library identifier, never change it
LIBID = "7c3dbc9c2ad44a47bd6fcb25caa270e5"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 0

UNIT_TEARDOWN_LOCKNAME = "unit-teardown"


class Error(Exception):
    """Base class for exceptions in this module."""

    def __repr__(self):
        """String representation of the Error class."""
        return "<{}.{} {}>".format(type(self).__module__, type(self).__name__, self.args)

    @property
    def name(self):
        """Return a string representation of the model plus class."""
        return "<{}.{}>".format(type(self).__module__, type(self).__name__)

    @property
    def message(self):
        """Return the message passed as an argument."""
        return self.args[0]


class MySQLConfigureMySQLUsersError(Error):
    """Exception raised when creating a user fails."""


class MySQLCheckUserExistenceError(Error):
    """Exception raised when checking for the existence of a MySQL user."""


class MySQLConfigureRouterUserError(Error):
    """Exception raised when configuring the MySQLRouter user."""


class MySQLCreateApplicationDatabaseAndScopedUserError(Error):
    """Exception raised when creating application database and scoped user."""


class MySQLDeleteUsersForUnitError(Error):
    """Exception raised when there is an issue deleting users for a unit."""


class MySQLConfigureInstanceError(Error):
    """Exception raised when there is an issue configuring a MySQL instance."""


class MySQLCreateClusterError(Error):
    """Exception raised when there is an issue creating an InnoDB cluster."""


class MySQLAddInstanceToClusterError(Error):
    """Exception raised when there is an issue add an instance to the MySQL InnoDB cluster."""


class MySQLRemoveInstanceRetryError(Error):
    """Exception raised when there is an issue removing an instance.

    Utilized by tenacity to retry the method.
    """


class MySQLRemoveInstanceError(Error):
    """Exception raised when there is an issue removing an instance.

    Exempt from the retry mechanism provided by tenacity.
    """


class MySQLInitializeJujuOperationsTableError(Error):
    """Exception raised when there is an issue initializing the juju units operations table."""


class MySQLClientError(Error):
    """Exception raised when there is an issue using the mysql cli or mysqlsh.

    Abstract platform specific exceptions for external commands execution Errors.
    """


class MySQLBase(ABC):
    """Abstract class to encapsulate all operations related to the MySQL instance and cluster.

    This class handles the configuration of MySQL instances, and also the
    creation and configuration of MySQL InnoDB clusters via Group Replication.
    Some methods are platform specific and must be implemented in the related
    charm code.
    """

    def __init__(
        self,
        instance_address: str,
        cluster_name: str,
        root_password: str,
        server_config_user: str,
        server_config_password: str,
        cluster_admin_user: str,
        cluster_admin_password: str,
    ):
        """Initialize the MySQL class.

        Args:
            instance_address: address of the targeted instance
            cluster_name: cluster name
            root_password: password for the 'root' user
            server_config_user: user name for the server config user
            server_config_password: password for the server config user
            cluster_admin_user: user name for the cluster admin user
            cluster_admin_password: password for the cluster admin user
        """
        self.instance_address = instance_address
        self.cluster_name = cluster_name
        self.root_password = root_password
        self.server_config_user = server_config_user
        self.server_config_password = server_config_password
        self.cluster_admin_user = cluster_admin_user
        self.cluster_admin_password = cluster_admin_password

    def configure_mysql_users(self):
        """Configure the MySQL users for the instance.

        Creates base `root@%` and `<server_config>@%` users with the
        appropriate privileges, and reconfigure `root@localhost` user password.

        Raises MySQLConfigureMySQLUsersError if the user creation fails.
        """
        # SYSTEM_USER and SUPER privileges to revoke from the root users
        # Reference: https://dev.mysql.com/doc/refman/8.0/en/privileges-provided.html#priv_super
        privileges_to_revoke = (
            "SYSTEM_USER",
            "SYSTEM_VARIABLES_ADMIN",
            "SUPER",
            "REPLICATION_SLAVE_ADMIN",
            "GROUP_REPLICATION_ADMIN",
            "BINLOG_ADMIN",
            "SET_USER_ID",
            "ENCRYPTION_KEY_ADMIN",
            "VERSION_TOKEN_ADMIN",
            "CONNECTION_ADMIN",
        )

        # commands  to create 'root'@'%' user
        create_root_user_commands = (
            f"CREATE USER 'root'@'%' IDENTIFIED BY '{self.root_password}'",
            "GRANT ALL ON *.* TO 'root'@'%' WITH GRANT OPTION",
        )

        # commands to be run from mysql client with root user and password set above
        configure_users_commands = (
            f"CREATE USER '{self.server_config_user}'@'%' IDENTIFIED BY '{self.server_config_password}'",
            f"GRANT ALL ON *.* TO '{self.server_config_user}'@'%' WITH GRANT OPTION",
            "UPDATE mysql.user SET authentication_string=null WHERE User='root' and Host='localhost'",
            f"ALTER USER 'root'@'localhost' IDENTIFIED BY '{self.root_password}'",
            f"REVOKE {', '.join(privileges_to_revoke)} ON *.* FROM root@'%'",
            f"REVOKE {', '.join(privileges_to_revoke)} ON *.* FROM root@localhost",
            "FLUSH PRIVILEGES",
        )

        try:
            logger.debug(f"Configuring MySQL users for {self.instance_address}")
            self._run_mysqlcli_script("; ".join(create_root_user_commands))
            # run configure users commands with newly created root user
            self._run_mysqlcli_script(
                "; ".join(configure_users_commands), password=self.root_password
            )
        except MySQLClientError as e:
            logger.exception(
                f"Failed to configure users for: {self.instance_address} with error {e.message}",
                exc_info=e,
            )
            raise MySQLConfigureMySQLUsersError(e.message)

    def does_mysql_user_exist(self, username: str, hostname: str) -> bool:
        """Checks if a mysqlrouter user already exists.

        Args:
            username: The username for the mysql user
            hostname: The hostname for the mysql user

        Returns:
            A boolean indicating whether the provided mysql user exists

        Raises MySQLCheckUserExistenceError
            if there is an issue confirming that the mysql user exists
        """
        user_existence_commands = (
            f"select if((select count(*) from mysql.user where user = '{username}' and host = '{hostname}'), 'USER_EXISTS', 'USER_DOES_NOT_EXIST') as ''",
        )

        try:
            output = self._run_mysqlcli_script("; ".join(user_existence_commands))
            return "USER_EXISTS" in output
        except MySQLClientError as e:
            logger.exception(
                f"Failed to check for existence of mysql user {username}@{hostname}",
                exc_info=e,
            )
            raise MySQLCheckUserExistenceError(e.message)

    def configure_mysqlrouter_user(
        self, username: str, password: str, hostname: str, unit_name: str
    ) -> None:
        """Configure a mysqlrouter user and grant the appropriate permissions to the user.

        Args:
            username: The username for the mysqlrouter user
            password: The password for the mysqlrouter user
            hostname: The hostname for the mysqlrouter user
            unit_name: The name of unit from which the mysqlrouter user will be accessed

        Raises MySQLConfigureRouterUserError
            if there is an issue creating and configuring the mysqlrouter user
        """
        mysqlrouter_user_attributes = {"unit_name": unit_name}
        create_mysqlrouter_user_commands = (
            f"CREATE USER '{username}'@'{hostname}' IDENTIFIED BY '{password}' ATTRIBUTE '{json.dumps(mysqlrouter_user_attributes)}'",
        )
        mysqlrouter_user_grant_commands = (
            f"GRANT CREATE USER ON *.* TO '{username}'@'{hostname}' WITH GRANT OPTION",
            f"GRANT SELECT, INSERT, UPDATE, DELETE, EXECUTE ON mysql_innodb_cluster_metadata.* TO '{username}'@'{hostname}'",
            f"GRANT SELECT ON mysql.user TO '{username}'@'{hostname}'",
            f"GRANT SELECT ON performance_schema.replication_group_members TO '{username}'@'{hostname}'",
            f"GRANT SELECT ON performance_schema.replication_group_member_stats TO '{username}'@'{hostname}'",
            f"GRANT SELECT ON performance_schema.global_variables TO '{username}'@'{hostname}'",
        )

        try:
            logger.debug(f"Configuring MySQLRouter user for {self.instance_address}")
            self._run_mysqlcli_script("; ".join(create_mysqlrouter_user_commands))
            # grant permissions to the newly created mysqlrouter user
            self._run_mysqlcli_script("; ".join(mysqlrouter_user_grant_commands))
        except MySQLClientError as e:
            logger.exception(
                f"Failed to configure mysqlrouter user for: {self.instance_address} with error {e.message}",
                exc_info=e,
            )
            raise MySQLConfigureRouterUserError(e.message)

    def create_application_database_and_scoped_user(
        self, database_name: str, username: str, password: str, hostname: str, unit_name: str
    ) -> None:
        """Create an application database and a user scoped to the created database.

        Args:
            database_name: The name of the database to create
            username: The username of the scoped user
            password: The password of the scoped user
            hostname: The hostname of the scoped user
            unit_name: The name of the unit from which the user will be accessed

        Raises MySQLCreateApplicationDatabaseAndScopedUserError
            if there is an issue creating the application database or a user scoped to the database
        """
        create_database_commands = (f"CREATE DATABASE IF NOT EXISTS {database_name}",)
        user_attributes = {"unit_name": unit_name}
        create_scoped_user_commands = (
            f"CREATE USER '{username}'@'{hostname}' IDENTIFIED BY '{password}' ATTRIBUTE '{json.dumps(user_attributes)}'",
            f"GRANT USAGE ON *.* TO '{username}'@`{hostname}`",
            f"GRANT ALL PRIVILEGES ON `{database_name}`.* TO `{username}`@`{hostname}`",
        )

        try:
            self._run_mysqlcli_script("; ".join(create_database_commands))
            self._run_mysqlcli_script("; ".join(create_scoped_user_commands))
        except MySQLClientError as e:
            logger.exception(
                f"Failed to create application database {database_name} and scoped user {username}@{hostname}",
                exc_info=e,
            )
            raise MySQLCreateApplicationDatabaseAndScopedUserError(e.message)

    def delete_users_for_unit(self, unit_name: str) -> None:
        """Delete users for a unit.

        Args:
            unit_name: The name of the unit for which to delete mysql users for

        Raises:
            MySQLDeleteUsersForUnitError if there is an error deleting users for the unit
        """
        get_unit_user_commands = (
            "SELECT CONCAT(user.user, '@', user.host) FROM mysql.user AS user JOIN",
            "information_schema.user_attributes AS attributes ON (user.user = attributes.user",
            "AND user.host = attributes.host) WHERE attributes.attribute LIKE",
            f' \'%"unit_name": "{unit_name}"%\';',
        )

        try:
            output = self._run_mysqlcli_script(" ".join(get_unit_user_commands))
            users = [line.strip() for line in output.split("\n") if line.strip()][1:]

            if len(users) == 0:
                logger.debug(f"There are no users to drop for unit {unit_name}")
                return

            primary_address = self.get_cluster_primary_address()
            drop_users_command = (
                f"shell.connect('{self.cluster_admin_user}:{self.cluster_admin_password}@{primary_address}')",
                f"session.run_sql(\"DROP USER IF EXISTS {', '.join(users)};\")",
            )
            self._run_mysqlsh_script("\n".join(drop_users_command))
        except MySQLClientError as e:
            logger.exception(f"Failed to query and delete users for unit {unit_name}", exc_info=e)
            raise MySQLDeleteUsersForUnitError(e.message)

    def configure_instance(self, restart: bool = True) -> None:
        """Configure the instance to be used in an InnoDB cluster.

        Raises MySQLConfigureInstanceError
            if the was an error configuring the instance for use in an InnoDB cluster.
        """
        options = {
            "clusterAdmin": self.cluster_admin_user,
            "clusterAdminPassword": self.cluster_admin_password,
            "restart": "true" if restart else "false",
        }

        configure_instance_command = (
            f"dba.configure_instance('{self.server_config_user}:{self.server_config_password}@{self.instance_address}', {json.dumps(options)})",
        )

        try:
            logger.debug(f"Configuring instance for InnoDB on {self.instance_address}")
            self._run_mysqlsh_script("\n".join(configure_instance_command))

        except MySQLClientError as e:
            logger.exception(
                f"Failed to configure instance: {self.instance_address} with error {e.message}",
                exc_info=e,
            )
            raise MySQLConfigureInstanceError(e.message)

    def create_cluster(self, unit_label: str) -> None:
        """Create an InnoDB cluster with Group Replication enabled.

        Raises MySQLCreateClusterError if there was an issue creating the cluster.
        """
        commands = (
            f"shell.connect('{self.server_config_user}:{self.server_config_password}@{self.instance_address}')",
            f"cluster = dba.create_cluster('{self.cluster_name}')",
            f"cluster.set_instance_option('{self.instance_address}', 'label', '{unit_label}')",
        )

        try:
            logger.debug(f"Creating a MySQL InnoDB cluster on {self.instance_address}")
            self._run_mysqlsh_script("\n".join(commands))
        except MySQLClientError as e:
            logger.exception(
                f"Failed to create cluster on instance: {self.instance_address} with error {e.message}",
                exc_info=e,
            )
            raise MySQLCreateClusterError(e.message)

    def initialize_juju_units_operations_table(self) -> None:
        """Initialize the mysql.juju_units_operations table using the serverconfig user.

        Raises
            MySQLInitializeJujuOperationsTableError if there is an issue
                initializing the juju_units_operations table
        """
        initialize_table_commands = (
            "CREATE TABLE mysql.juju_units_operations (task varchar(20), executor varchar(20), status varchar(20), primary key(task))",
            f"INSERT INTO mysql.juju_units_operations values ('{UNIT_TEARDOWN_LOCKNAME}', '', 'not-started')",
        )

        try:
            logger.debug(
                f"Initializing the juju_units_operations table on {self.instance_address}"
            )

            self._run_mysqlcli_script(
                "; ".join(initialize_table_commands),
                user=self.server_config_user,
                password=self.server_config_password,
            )
        except MySQLClientError as e:
            logger.exception(
                f"Failed to initialize mysql.juju_units_operations table with error {e.message}",
                exc_info=e,
            )
            raise MySQLInitializeJujuOperationsTableError(e.message)

    def add_instance_to_cluster(self, instance_address: str, instance_unit_label: str) -> None:
        """Add an instance to the InnoDB cluster.

        This method is only called from the juju leader unit (thus locks are
        obtained locally)

        Raises MySQLADDInstanceToClusterError
            if there was an issue adding the instance to the cluster.

        Args:
            instance_address: address of the instance to add to the cluster
            instance_unit_label: the label/name of the unit
        """
        options = {
            "password": self.cluster_admin_password,
            "label": instance_unit_label,
        }

        connect_commands = (
            f"shell.connect('{self.cluster_admin_user}:{self.cluster_admin_password}@{self.instance_address}')",
            f"cluster = dba.get_cluster('{self.cluster_name}')",
        )

        for recovery_method in ["auto", "clone"]:
            # Prefer "auto" recovery method, but if it fails, try "clone"
            try:
                options["recoveryMethod"] = recovery_method
                add_instance_command = (
                    f"cluster.add_instance('{self.cluster_admin_user}@{instance_address}', {json.dumps(options)})",
                )

                logger.debug(
                    f"Adding instance {instance_address}/{instance_unit_label} to cluster {self.cluster_name} with recovery method {recovery_method}"
                )
                self._run_mysqlsh_script("\n".join(connect_commands + add_instance_command))

                break
            except MySQLClientError as e:
                if recovery_method == "clone":
                    logger.exception(
                        f"Failed to add instance {instance_address} to cluster {self.cluster_name} on {self.instance_address}",
                        exc_info=e,
                    )
                    raise MySQLAddInstanceToClusterError(e.message)

                logger.debug(
                    f"Failed to add instance {instance_address} to cluster {self.cluster_name} with recovery method 'auto'. Trying method 'clone'"
                )

    def is_instance_configured_for_innodb(
        self, instance_address: str, instance_unit_label: str
    ) -> bool:
        """Confirm if instance is configured for use in an InnoDB cluster.

        Args:
            instance_address: The instance address for which to confirm InnoDB configuration
            instance_unit_label: The label of the instance unit to confirm InnoDB configuration

        Returns:
            Boolean indicating whether the instance is configured for use in an InnoDB cluster
        """
        commands = (
            f"shell.connect('{self.cluster_admin_user}:{self.cluster_admin_password}@{instance_address}')",
            "instance_configured = dba.check_instance_configuration()['status'] == 'ok'",
            'print("INSTANCE_CONFIGURED" if instance_configured else "INSTANCE_NOT_CONFIGURED")',
        )

        try:
            logger.debug(
                f"Confirming instance {instance_address}/{instance_unit_label} configuration for InnoDB"
            )

            output = self._run_mysqlsh_script("\n".join(commands))
            return "INSTANCE_CONFIGURED" in output
        except MySQLClientError as e:
            # confirmation can fail if the clusteradmin user does not yet exist on the instance
            logger.warning(
                f"Failed to confirm instance configuration for {instance_address} with error {e.message}",
                exc_info=e,
            )
            return False

    def is_instance_in_cluster(self, unit_label: str) -> bool:
        """Confirm if instance is in the cluster.

        Args:
            unit_label: The label of unit to check existence in cluster for

        Returns:
            Boolean indicating whether the unit is a member of the cluster
        """
        commands = (
            f"shell.connect('{self.cluster_admin_user}:{self.cluster_admin_password}@{self.instance_address}')",
            f"cluster = dba.get_cluster('{self.cluster_name}')",
            f"print(cluster.status()['defaultReplicaSet']['topology'].get('{unit_label}', {{}}).get('status', 'NOT_A_MEMBER'))",
        )

        try:
            logger.debug(f"Checking existence of unit {unit_label} in cluster {self.cluster_name}")

            output = self._run_mysqlsh_script("\n".join(commands))
            return "ONLINE" in output
        except MySQLClientError:
            # confirmation can fail if the clusteradmin user does not yet exist on the instance
            logger.debug(
                f"Failed to confirm existence of unit {unit_label} in cluster {self.cluster_name}"
            )
            return False

    def get_cluster_status(self) -> dict:
        """Get the cluster status.

        Executes script to retrieve cluster status.
        Won't raise errors.

        Returns:
            Cluster status as a dictionary
        """
        status_commands = (
            f"shell.connect('{self.cluster_admin_user}:{self.cluster_admin_password}@{self.instance_address}')",
            f"cluster = dba.get_cluster('{self.cluster_name}')",
            "print(cluster.status())",
        )

        try:
            output = self._run_mysqlsh_script("\n".join(status_commands))
            output_dict = json.loads(output.lower())
            return output_dict
        except MySQLClientError as e:
            logger.exception(f"Failed to get cluster status for {self.cluster_name}", exc_info=e)

    @retry(
        retry=retry_if_exception_type(MySQLRemoveInstanceRetryError),
        stop=stop_after_attempt(15),
        reraise=True,
        wait=wait_random(min=4, max=30),
    )
    def remove_instance(self, unit_label: str) -> None:
        """Remove instance from the cluster.

        This method is called from each unit being torn down, thus we must obtain
        locks on the cluster primary. There is a retry mechanism for any issues
        obtaining the lock, removing instances/dissolving the cluster, or releasing
        the lock.

        Raises:
            MySQLRemoveInstanceRetryError - to retry this method if there was an issue
                obtaining a lock or removing the instance
            MySQLRemoveInstanceError - if there is an issue releasing
                the lock after the instance is removed from the cluster (avoids retries)

        Args:
            unit_label: The label for this unit's instance (to be torn down)
        """
        try:
            # Get the cluster primary's address to direct lock acquisition request to.
            primary_address = self.get_cluster_primary_address()
            if not primary_address:
                raise MySQLRemoveInstanceRetryError(
                    "Unable to retrieve the cluster primary's address"
                )

            # Attempt to acquire a lock on the primary instance
            acquired_lock = self._acquire_lock(primary_address, unit_label, UNIT_TEARDOWN_LOCKNAME)
            if not acquired_lock:
                raise MySQLRemoveInstanceRetryError("Did not acquire lock to remove unit")

            # Get remaining cluster member addresses before calling mysqlsh.remove_instance()
            remaining_cluster_member_addresses, valid = self._get_cluster_member_addresses(
                exclude_unit_labels=[unit_label]
            )
            if not valid:
                raise MySQLRemoveInstanceRetryError("Unable to retrieve cluster member addresses")

            # Remove instance from cluster, or dissolve cluster if no other members remain
            logger.debug(
                f"Removing instance {self.instance_address} from cluster {self.cluster_name}"
            )
            remove_instance_options = {
                "password": self.cluster_admin_password,
                "force": "true",
            }
            dissolve_cluster_options = {
                "force": "true",
            }
            remove_instance_commands = (
                f"shell.connect('{self.cluster_admin_user}:{self.cluster_admin_password}@{self.instance_address}')",
                f"cluster = dba.get_cluster('{self.cluster_name}')",
                "number_cluster_members = len(cluster.status()['defaultReplicaSet']['topology'])",
                f"cluster.remove_instance('{self.cluster_admin_user}@{self.instance_address}', {json.dumps(remove_instance_options)}) if number_cluster_members > 1 else cluster.dissolve({json.dumps(dissolve_cluster_options)})",
            )
            self._run_mysqlsh_script("\n".join(remove_instance_commands))
        except MySQLClientError as e:
            # In case of an error, raise an error and retry
            logger.warning(
                f"Failed to acquire lock and remove instance {self.instance_address} with error {e.message}",
                exc_info=e,
            )
            raise MySQLRemoveInstanceRetryError(e.message)

        # There is no need to release the lock if cluster was dissolved
        if not remaining_cluster_member_addresses:
            return

        # The below code should not result in retries of this method since the
        # instance would already be removed from the cluster.
        try:
            # Retrieve the cluster primary's address again (in case the old primary is scaled down)
            # Release the lock by making a request to this primary member's address
            primary_address = self.get_cluster_primary_address(
                connect_instance_address=remaining_cluster_member_addresses[0]
            )
            if not primary_address:
                raise MySQLRemoveInstanceError(
                    "Unable to retrieve the address of the cluster primary"
                )

            self._release_lock(primary_address, unit_label, UNIT_TEARDOWN_LOCKNAME)
        except MySQLClientError as e:
            # Raise an error that does not lead to a retry of this method
            logger.exception(
                f"Failed to release lock on {unit_label} with error {e.message}", exc_info=e
            )
            raise MySQLRemoveInstanceError(e.message)

    def _acquire_lock(self, primary_address: str, unit_label: str, lock_name: str) -> bool:
        """Attempts to acquire a lock by using the mysql.juju_units_operations table.

        Note that there must exist the appropriate rows in the table, created in the
        initialize_juju_units_operations_table() method.

        Args:
            primary_address: The address of the cluster's primary
            unit_label: The label of the unit for which to obtain the lock
            lock_name: The name of the lock to obtain

        Returns:
            Boolean indicating whether the lock was obtained
        """
        logger.debug(
            f"Attempting to acquire lock {lock_name} on {primary_address} for unit {unit_label}"
        )

        acquire_lock_commands = (
            f"shell.connect('{self.cluster_admin_user}:{self.cluster_admin_password}@{primary_address}')",
            f"session.run_sql(\"UPDATE mysql.juju_units_operations SET executor='{unit_label}', status='in-progress' WHERE task='{lock_name}' AND executor='';\")",
            f"acquired_lock = session.run_sql(\"SELECT count(*) FROM mysql.juju_units_operations WHERE task='{lock_name}' AND executor='{unit_label}';\").fetch_one()[0]",
            "print(f'<ACQUIRED_LOCK>{acquired_lock}</ACQUIRED_LOCK>')",
        )

        output = self._run_mysqlsh_script("\n".join(acquire_lock_commands))
        matches = re.search(r"<ACQUIRED_LOCK>(\d)</ACQUIRED_LOCK>", output)
        if not matches:
            return False

        return bool(int(matches.group(1)))

    def _release_lock(self, primary_address: str, unit_label: str, lock_name: str) -> None:
        """Releases a lock in the mysql.juju_units_operations table.

        Note that there must exist the appropriate rows in the table, created in the
        initialize_juju_units_operations_table() method.

        Args:
            primary_address: The address of the cluster's primary
            unit_label: The label of the unit to release the lock for
            lock_name: The name of the lock to release
        """
        logger.debug(f"Releasing lock {lock_name} on {primary_address} for unit {unit_label}")

        release_lock_commands = (
            f"shell.connect('{self.cluster_admin_user}:{self.cluster_admin_password}@{primary_address}')",
            f"session.run_sql(\"UPDATE mysql.juju_units_operations SET executor='', status='not-started' WHERE task='{lock_name}' AND executor='{unit_label}';\")",
        )
        self._run_mysqlsh_script("\n".join(release_lock_commands))

    def _get_cluster_member_addresses(self, exclude_unit_labels: List = []) -> Tuple[List, bool]:
        """Get the addresses of the cluster's members.

        Keyword args:
            exclude_unit_labels: (Optional) unit labels to exclude when retrieving cluster members

        Returns:
            ([member_addresses], valid): a list of member addresses and
                whether the method's execution was valid
        """
        logger.debug(f"Getting cluster member addresses, excluding units {exclude_unit_labels}")

        get_cluster_members_commands = (
            f"shell.connect('{self.cluster_admin_user}:{self.cluster_admin_password}@{self.instance_address}')",
            f"cluster = dba.get_cluster('{self.cluster_name}')",
            f"member_addresses = ','.join([member['address'] for label, member in cluster.status()['defaultReplicaSet']['topology'].items() if label not in {exclude_unit_labels}])",
            "print(f'<MEMBER_ADDRESSES>{member_addresses}</MEMBER_ADDRESSES>')",
        )

        output = self._run_mysqlsh_script("\n".join(get_cluster_members_commands))
        matches = re.search(r"<MEMBER_ADDRESSES>(.*)</MEMBER_ADDRESSES>", output)

        if not matches:
            return ([], False)

        # Filter out any empty values (in case there are no members)
        member_addresses = [
            member_address for member_address in matches.group(1).split(",") if member_address
        ]

        return (member_addresses, "<MEMBER_ADDRESSES>" in output)

    def get_cluster_primary_address(self, connect_instance_address: str = None) -> str:
        """Get the cluster primary's address.

        Keyword args:
            connect_instance_address: The address for the cluster primary
                (default to this instance's address)

        Returns:
            The address of the cluster's primary
        """
        logger.debug(f"Getting cluster primary member's address from {connect_instance_address}")

        if not connect_instance_address:
            connect_instance_address = self.instance_address

        get_cluster_primary_commands = (
            f"shell.connect('{self.cluster_admin_user}:{self.cluster_admin_password}@{connect_instance_address}')",
            f"cluster = dba.get_cluster('{self.cluster_name}')",
            "primary_address = sorted([cluster_member['address'] for cluster_member in cluster.status()['defaultReplicaSet']['topology'].values() if cluster_member['mode'] == 'R/W'])[0]",
            "print(f'<PRIMARY_ADDRESS>{primary_address}</PRIMARY_ADDRESS>')",
        )

        output = self._run_mysqlsh_script("\n".join(get_cluster_primary_commands))
        matches = re.search(r"<PRIMARY_ADDRESS>(.+)</PRIMARY_ADDRESS>", output)

        if not matches:
            return None

        return matches.group(1)

    @abstractmethod
    def wait_until_mysql_connection(self) -> None:
        """Wait until a connection to MySQL has been obtained.

        Implemented in subclasses, test for socket file existence.
        """
        pass

    @abstractmethod
    def _run_mysqlsh_script(self, script: str) -> str:
        """Execute a MySQL shell script.

        Raises MySQLClientError if script execution fails.

        Args:
            script: Mysqlsh script string

        Returns:
            String representing the output of the mysqlsh command
        """
        pass

    @abstractmethod
    def _run_mysqlcli_script(self, script: str, user: str = "root", password: str = None) -> str:
        """Execute a MySQL CLI script.

        Execute SQL script as instance with given user.

        Raises MySQLClientError if script execution fails.

        Args:
            script: raw SQL script string
            user: (optional) user to invoke the mysql cli script with (default is "root")
            password: (optional) password to invoke the mysql cli script with
        """
        pass
