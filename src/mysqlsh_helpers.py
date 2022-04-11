#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Helper class to manage the MySQL InnoDB cluster lifecycle with MySQL Shell."""

import json
import logging
import os
import pathlib
import shutil
import subprocess
import tempfile

from charms.operator_libs_linux.v0 import apt
from charms.operator_libs_linux.v1 import snap
from tenacity import retry, stop_after_delay, wait_fixed

logger = logging.getLogger(__name__)


# TODO: determine if version locking is needed for both mysql-shell and mysql-server
MYSQL_SHELL_SNAP_NAME = "mysql-shell"
MYSQL_APT_PACKAGE_NAME = "mysql-server-8.0"
MYSQL_SHELL_COMMON_DIRECTORY = "/root/snap/mysql-shell/common"
MYSQLD_SOCK_FILE = "/var/run/mysqld/mysqld.sock"
MYSQLD_CONFIG_DIRECTORY = "/etc/mysql/mysql.conf.d"


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
    def _get_mysqlsh_bin() -> str:
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
                mysqlsh_help_command = [MySQL._get_mysqlsh_bin(), "--help"]
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
            "SET @@SESSION.SQL_LOG_BIN=0;",
            f"CREATE USER 'root'@'%' IDENTIFIED BY '{self.root_password}';",
            "GRANT ALL ON *.* TO 'root'@'%' WITH GRANT OPTION;",
        )

        # commands to be run from mysql client with root user and password set above
        configure_users_commands = (
            "SET @@SESSION.SQL_LOG_BIN=0;",
            f"CREATE USER '{self.server_config_user}'@'%' IDENTIFIED BY '{self.server_config_password}';",
            f"GRANT ALL ON *.* TO '{self.server_config_user}'@'%' WITH GRANT OPTION;",
            "UPDATE mysql.user SET authentication_string=null WHERE User='root' and Host='localhost';",
            f"ALTER USER 'root'@'localhost' IDENTIFIED BY '{self.root_password}';",
            f"REVOKE {', '.join(privileges_to_revoke)} ON *.* FROM root@'%';",
            f"REVOKE {', '.join(privileges_to_revoke)} ON *.* FROM root@localhost;",
            "FLUSH PRIVILEGES;",
        )

        try:
            logger.debug("Configuring MySQL users")
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
            logger.debug("Configuring instance for InnoDB")
            self._run_mysqlsh_script("\n".join(commands))

            logger.debug("Waiting until MySQL is restarted")
            self._wait_until_mysql_connection()
        except (subprocess.CalledProcessError, MySQLServiceNotRunningError) as e:
            logger.exception(
                f"Failed to configure instance: {self.instance_address} with error {e.stderr}",
                exc_info=e,
            )
            raise MySQLConfigureInstanceError(e.stderr)

    def create_cluster(self) -> None:
        """Create an InnoDB cluster with Group Replication enabled.

        Raises MySQLCreateClusterError if there was an issue creating the cluster.
        """
        commands = (
            f"shell.connect('{self.server_config_user}:{self.server_config_password}@{self.instance_address}')",
            f"dba.create_cluster('{self.cluster_name}')",
        )

        try:
            logger.debug("Creating a MySQL InnoDB cluster")
            self._run_mysqlsh_script("\n".join(commands))
        except subprocess.CalledProcessError as e:
            logger.exception(
                f"Failed to create cluster on instance: {self.instance_address} with error {e.stderr}",
                exc_info=e,
            )
            raise MySQLCreateClusterError(e.stderr)

    def add_instance_to_cluster(self, instance_address) -> None:
        """Add an instance to the InnoDB cluster.

        Raises MySQLADDInstanceToClusterError
            if there was an issue adding the instance to the cluster.

        Args:
            instance_address: address of the instance to add to the cluster
        """
        options = {
            "password": self.cluster_admin_password,
            "recoveryMethod": "clone",
        }

        commands = (
            f"shell.connect('{self.cluster_admin_user}:{self.cluster_admin_password}@{self.instance_address}')",
            f"cluster = dba.get_cluster('{self.cluster_name}')",
            f"cluster.add_instance('{self.cluster_admin_user}@{instance_address}', {json.dumps(options)})",
        )

        try:
            logger.debug(f"Adding instance {instance_address} to cluster {self.cluster_name}")
            self._run_mysqlsh_script("\n".join(commands))
        except subprocess.CalledProcessError as e:
            logger.exception(
                f"Failed to add instance {instance_address} to cluster {self.cluster_name} with error {e.stderr}",
                exc_info=e,
            )
            raise MySQLAddInstanceToClusterError(e.stderr)

    @retry(reraise=True, stop=stop_after_delay(30), wait=wait_fixed(5))
    def _wait_until_mysql_connection(self) -> None:
        """Wait until a connection to MySQL has been obtained.

        Retry every 5 seconds for 30 seconds if there is an issue obtaining a connection.
        """
        if not os.path.exists(MYSQLD_SOCK_FILE):
            raise MySQLServiceNotRunningError()

    def _run_mysqlsh_script(self, script: str) -> None:
        """Execute a MySQL shell script.

        Raises CalledProcessError if the script gets a non-zero return code.

        Args:
            script: Mysqlsh script string

        Returns:
            Byte string subprocess output
        """
        # Use the self.mysqlsh_common_dir for the confined mysql-shell snap.
        with tempfile.NamedTemporaryFile(mode="w", dir=MYSQL_SHELL_COMMON_DIRECTORY) as _file:
            _file.write(script)
            _file.flush()

            # Specify python as this is not the default in the deb version
            # of the mysql-shell snap
            command = [MySQL._get_mysqlsh_bin(), "--no-wizard", "--python", "-f", _file.name]
            subprocess.check_output(command, stderr=subprocess.PIPE)

    def _run_mysqlcli_script(self, script: str, password=None) -> None:
        """Execute a MySQL CLI script.

        Execute SQL script as instance root user.
        Raises CalledProcessError if the script gets a non-zero return code.

        Args:
            script: raw SQL script string

        Returns:
            Byte string subprocess output
        """
        command = [
            "mysql",
            "-u",
            "root",
            "--protocol=SOCKET",
            "--socket=/var/run/mysqld/mysqld.sock",
            "-e",
            script,
        ]

        if password:
            command.append(f"--password={password}")

        subprocess.check_output(command, stderr=subprocess.PIPE)
