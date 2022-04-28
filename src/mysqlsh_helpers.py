#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Helper class to manage the MySQL InnoDB cluster lifecycle with MySQL Shell."""

import json
import logging
import os
import pathlib
import re
import shutil
import subprocess
import tempfile
from typing import List, Tuple

from charms.operator_libs_linux.v0 import apt
from charms.operator_libs_linux.v1 import snap
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    stop_after_delay,
    wait_fixed,
    wait_random,
)

logger = logging.getLogger(__name__)


# TODO: determine if version locking is needed for both mysql-shell and mysql-server
MYSQL_SHELL_SNAP_NAME = "mysql-shell"
MYSQL_APT_PACKAGE_NAME = "mysql-server-8.0"
MYSQL_SHELL_COMMON_DIRECTORY = "/root/snap/mysql-shell/common"
MYSQLD_SOCK_FILE = "/var/run/mysqld/mysqld.sock"
MYSQLD_CONFIG_DIRECTORY = "/etc/mysql/mysql.conf.d"

UNIT_TEARDOWN_LOCKNAME = "unit-teardown"


class MySQLConfigureMySQLUsersError(Exception):
    """Exception raised when creating a user fails."""

    pass


class MySQLConfigureInstanceError(Exception):
    """Exception raised when there is an issue configuring a MySQL instance."""

    pass


class MySQLCreateClusterError(Exception):
    """Exception raised when there is an issue creating an InnoDB cluster."""

    pass


class MySQLAddInstanceToClusterError(Exception):
    """Exception raised when there is an issue add an instance to the MySQL InnoDB cluster."""

    pass


class MySQLServiceNotRunningError(Exception):
    """Exception raised when the MySQL service is not running."""

    pass


class MySQLRemoveInstanceRetryError(Exception):
    """Exception raised when there is an issue removing an instance.

    Utilized by tenacity to retry the method.
    """

    pass


class MySQLRemoveInstanceError(Exception):
    """Exception raised when there is an issue removing an instance.

    Exempt from the retry mechanism provided by tenacity.
    """


class MySQLInitializeJujuOperationsTableError(Exception):
    """Exception raised when there is an issue initializing the juju units operations table."""

    pass


class MySQL:
    """Class to encapsulate all operations related to the MySQL instance and cluster.

    This class handles the configuration of MySQL instances, and also the
    creation and configuration of MySQL InnoDB clusters via Group Replication.
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

    @staticmethod
    def get_mysqlsh_bin() -> str:
        """Determine binary path for MySQL Shell.

        Returns:
            Path to binary mysqlsh
        """
        # Allow for various versions of the mysql-shell snap
        # When we get the alias use /snap/bin/mysqlsh
        paths = ("/usr/bin/mysqlsh", "/snap/bin/mysqlsh", "/snap/bin/mysql-shell.mysqlsh")

        for path in paths:
            if os.path.exists(path):
                return path

        # Default to the full path version
        return "/snap/bin/mysql-shell"

    @staticmethod
    def install_and_configure_mysql_dependencies() -> None:
        """Install and configure MySQL dependencies.

        Raises
            subprocess.CalledProcessError: if issue updating apt or creating mysqlsh common dir
            apt.PackageNotFoundError, apt.PackageError: if issue install mysql server
            snap.SnapNotFOundError, snap.SnapError: if issue installing mysql shell snap
        """
        try:
            # create the mysqld config directory if it does not exist
            logger.debug("Copying custom mysqld config")
            pathlib.Path(MYSQLD_CONFIG_DIRECTORY).mkdir(mode=0o755, parents=True, exist_ok=True)
            # target file has prefix 'z-' to ensure priority over the default mysqld config file
            shutil.copyfile(
                "templates/mysqld.cnf", f"{MYSQLD_CONFIG_DIRECTORY}/z-custom-mysqld.cnf"
            )

            # install mysql server
            logger.debug("Updating apt")
            apt.update()
            logger.debug("Installing mysql server")
            apt.add_package(MYSQL_APT_PACKAGE_NAME)

            # install mysql shell if not already installed
            logger.debug("Retrieving snap cache")
            cache = snap.SnapCache()
            mysql_shell = cache[MYSQL_SHELL_SNAP_NAME]

            if not mysql_shell.present:
                logger.debug("Installing mysql shell snap")
                mysql_shell.ensure(snap.SnapState.Latest, channel="stable")

            # ensure creation of mysql shell common directory by running 'mysqlsh --help'
            if not os.path.exists(MYSQL_SHELL_COMMON_DIRECTORY):
                logger.debug("Creating mysql shell common directory")
                mysqlsh_help_command = [MySQL.get_mysqlsh_bin(), "--help"]
                subprocess.check_call(mysqlsh_help_command, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as e:
            logger.exception("Failed to execute subprocess command", exc_info=e)
            raise
        except (apt.PackageNotFoundError, apt.PackageError) as e:
            logger.exception("Failed to install apt packages", exc_info=e)
            raise
        except (snap.SnapNotFoundError, snap.SnapError) as e:
            logger.exception("Failed to install snaps", exc_info=e)
            raise
        except Exception as e:
            logger.exception("Encountered an unexpected exception", exc_info=e)
            raise

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
            f"CREATE USER 'root'@'%' IDENTIFIED BY '{self.root_password}';",
            "GRANT ALL ON *.* TO 'root'@'%' WITH GRANT OPTION;",
        )

        # commands to be run from mysql client with root user and password set above
        configure_users_commands = (
            f"CREATE USER '{self.server_config_user}'@'%' IDENTIFIED BY '{self.server_config_password}';",
            f"GRANT ALL ON *.* TO '{self.server_config_user}'@'%' WITH GRANT OPTION;",
            "UPDATE mysql.user SET authentication_string=null WHERE User='root' and Host='localhost';",
            f"ALTER USER 'root'@'localhost' IDENTIFIED BY '{self.root_password}';",
            f"REVOKE {', '.join(privileges_to_revoke)} ON *.* FROM root@'%';",
            f"REVOKE {', '.join(privileges_to_revoke)} ON *.* FROM root@localhost;",
            "FLUSH PRIVILEGES;",
        )

        try:
            logger.debug(f"Configuring MySQL users for {self.instance_address}")
            self._run_mysqlcli_script(" ".join(create_root_user_commands))
            # run configure users commands with newly created root user
            self._run_mysqlcli_script(
                " ".join(configure_users_commands), password=self.root_password
            )
        except subprocess.CalledProcessError as e:
            logger.exception(
                f"Failed to configure users for: {self.instance_address} with error {e.stderr}",
                exc_info=e,
            )
            raise MySQLConfigureMySQLUsersError(e.stderr)

    def configure_instance(self) -> None:
        """Configure the instance to be used in an InnoDB cluster.

        Raises MySQLConfigureInstanceError
            if the was an error configuring the instance for use in an InnoDB cluster.
        """
        options = {
            "clusterAdmin": self.cluster_admin_user,
            "clusterAdminPassword": self.cluster_admin_password,
            "restart": "true",
        }

        commands = (
            f"dba.configure_instance('{self.server_config_user}:{self.server_config_password}@{self.instance_address}', {json.dumps(options)})",
        )

        try:
            logger.debug(f"Configuring instance for InnoDB on {self.instance_address}")
            self._run_mysqlsh_script("\n".join(commands))

            logger.debug("Waiting until MySQL is restarted")
            self._wait_until_mysql_connection()
        except (subprocess.CalledProcessError, MySQLServiceNotRunningError) as e:
            logger.exception(
                f"Failed to configure instance: {self.instance_address} with error {e.stderr}",
                exc_info=e,
            )
            raise MySQLConfigureInstanceError(e.stderr)

    def create_cluster(self, unit_label) -> None:
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
        except subprocess.CalledProcessError as e:
            logger.exception(
                f"Failed to create cluster on instance: {self.instance_address} with error {e.stderr}",
                exc_info=e,
            )
            raise MySQLCreateClusterError(e.stderr)

    def initialize_juju_units_operations_table(self) -> None:
        """Initialize the mysql.juju_units_operations table using the serverconfig user.

        Raises
            MySQLInitializeJujuOperationsTableError if there is an issue
                initializing the juju_units_opertions table
        """
        initalize_table_commands = (
            "CREATE TABLE mysql.juju_units_operations (task varchar(20), executor varchar(20), status varchar(20), primary key(task));",
            f"INSERT INTO mysql.juju_units_operations values ('{UNIT_TEARDOWN_LOCKNAME}', '', 'not-started');",
        )

        try:
            logger.debug(
                f"Initializing the juju_units_operations table on {self.instance_address}"
            )

            self._run_mysqlcli_script(
                " ".join(initalize_table_commands),
                user=self.server_config_user,
                password=self.server_config_password,
            )
        except subprocess.CalledProcessError as e:
            logger.exception(
                f"Failed to initialize mysql.juju_units_operations table with error {e.stderr}",
                exc_info=e,
            )
            raise MySQLInitializeJujuOperationsTableError(e.stderr)

    def add_instance_to_cluster(self, instance_address, instance_unit_label) -> None:
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
            except subprocess.CalledProcessError as e:
                if recovery_method == "clone":
                    logger.exception(
                        f"Failed to add instance {instance_address} to cluster {self.cluster_name} on {self.instance_address}",
                        exc_info=e,
                    )
                    raise MySQLAddInstanceToClusterError(e.stderr)

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
        except subprocess.CalledProcessError as e:
            # confirmation can fail if the clusteradmin user does not yet exist on the instance
            logger.warning(
                f"Failed to confirm instance configuration for {instance_address} with error {e.stderr}",
                exc_info=e,
            )
            return False

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
            primary_address = self._get_cluster_primary_address()
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
        except subprocess.CalledProcessError as e:
            # In case of an error, raise an error and retry
            logger.warning(
                f"Failed to acquire lock and remove instance {self.instance_address} with error {e.stderr}",
                exc_info=e,
            )
            raise MySQLRemoveInstanceRetryError(e.stderr)

        # There is no need to release the lock if cluster was dissolved
        if not remaining_cluster_member_addresses:
            return

        # The below code should not result in retries of this method since the
        # instance would already be removed from the cluster.
        try:
            # Retrieve the cluster primary's address again (in case the old primary is scaled down)
            # Release the lock by making a request to this primary member's address
            primary_address = self._get_cluster_primary_address(
                connect_instance_address=remaining_cluster_member_addresses[0]
            )
            if not primary_address:
                raise MySQLRemoveInstanceError(
                    "Unable to retrieve the address of the cluster primary"
                )

            self._release_lock(primary_address, unit_label, UNIT_TEARDOWN_LOCKNAME)
        except subprocess.CalledProcessError as e:
            # Raise an error that does not lead to a retry of this method
            logger.exception(
                f"Failed to release lock on {unit_label} with error {e.stderr}", exc_info=e
            )
            raise MySQLRemoveInstanceError(e.stderr)

    def _acquire_lock(self, primary_address: str, unit_label: str, lock_name: str) -> bool:
        """Attempts to acquire a lock by using the mysql.juju_units_operations table.

        Note that there must exist the appropriate rows in the table, created in the
        initialize_juju_units_operations_table() method.

        Args:
            primary_address: The address of the cluster's primary
            unit_label: The label of the unit for which to obtain the lock
            lock_name: The name of the lock to obtain

        Raises:
            subprocess.CalledProcessError if there's an issue acquiring the lock

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

        Raises:
            subprocess.CalledProcessError if there's an issue releasing the lock
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

        Raises:
            subprocess.CalledProcessError if there is an issue getting cluster
                members' addresses

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

    def _get_cluster_primary_address(self, connect_instance_address: str = None) -> str:
        """Get the cluster primary's address.

        Keyword args:
            connect_instance_address: The address for the cluster primary
                (default to this instance's address)

        Raises:
            subprocess.CalledProcessError if there is an issue retrieving the
                cluster primary's address

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

    @retry(reraise=True, stop=stop_after_delay(30), wait=wait_fixed(5))
    def _wait_until_mysql_connection(self) -> None:
        """Wait until a connection to MySQL has been obtained.

        Retry every 5 seconds for 30 seconds if there is an issue obtaining a connection.
        """
        if not os.path.exists(MYSQLD_SOCK_FILE):
            raise MySQLServiceNotRunningError()

    def _run_mysqlsh_script(self, script: str) -> str:
        """Execute a MySQL shell script.

        Raises CalledProcessError if the script gets a non-zero return code.

        Args:
            script: Mysqlsh script string

        Returns:
            String representing the output of the mysqlsh command
        """
        # Use the self.mysqlsh_common_dir for the confined mysql-shell snap.
        with tempfile.NamedTemporaryFile(mode="w", dir=MYSQL_SHELL_COMMON_DIRECTORY) as _file:
            _file.write(script)
            _file.flush()

            # Specify python as this is not the default in the deb version
            # of the mysql-shell snap
            command = [MySQL.get_mysqlsh_bin(), "--no-wizard", "--python", "-f", _file.name]
            return subprocess.check_output(command, stderr=subprocess.PIPE).decode("utf-8")

    def _run_mysqlcli_script(self, script: str, user: str = "root", password: str = None) -> None:
        """Execute a MySQL CLI script.

        Execute SQL script as instance root user.
        Raises CalledProcessError if the script gets a non-zero return code.

        Args:
            script: raw SQL script string
            user: (optional) user to invoke the mysql cli script with (default is "root")
            password: (optional) password to invoke the mysql cli script with
        """
        command = [
            "mysql",
            "-u",
            user,
            "--protocol=SOCKET",
            "--socket=/var/run/mysqld/mysqld.sock",
            "-e",
            script,
        ]

        if password:
            command.append(f"--password={password}")

        subprocess.check_output(command, stderr=subprocess.PIPE)
