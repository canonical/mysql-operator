#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Helper class to manage the MySQL InnoDB cluster lifecycle with MySQL Shell."""

import json
import logging
import os
import shutil
import subprocess
import tempfile

from tenacity import retry, stop_after_delay, wait_fixed

logger = logging.getLogger(__name__)


class MySQLInitializationError(Exception):
    """Exception raised when initializing MySQL helper class."""

    pass


class MySQLConfigureMySQLUsersError(Exception):
    """Exception raised when creating a user fails."""

    pass


class MySQLConfigureInstanceError(Exception):
    """Exception raised when there is an issue configuring a MySQL instance."""

    pass


class MySQLCreateClusterError(Exception):
    """Exception raised when there is an issue creating an InnoDB cluster."""

    pass


class MySQLUpdateConfigurationError(Exception):
    """Exception raised when there is an issue updating the MySQL configuration."""

    pass


class MySQLAddInstanceToClusterError(Exception):
    """Exception raised when there is an issue add an instance to the MySQL InnoDB cluster."""

    pass


class MySQL:
    """Class to encapsulate all operations related to the MySQL instance and cluster.

    This class handles the configuration of MySQL instances, and also the
    creation and configuration of MySQL InnoDB clusters via Group Replication.
    """

    def __init__(
        self,
        cluster_admin_password: str,
        cluster_admin_user: str,
        cluster_name: str,
        instance_address: str,
        root_password: str,
        server_config_password: str,
        server_config_user: str,
    ):
        """Initialize the MySQL class.

        Raises MySQLInitializationError if the was an error initializing the helper class.

        Args:
            cluster_admin_password: password for the cluster admin user
            cluster_admin_user: user name for the cluster admin user
            cluster_name: cluster name
            instance_address: address of the targeted instance
            root_password: password for the 'root' user
            server_config_password: password for the server config user
            server_config_user: user name for the server config user
        """
        self.cluster_admin_password = cluster_admin_password
        self.cluster_admin_user = cluster_admin_user
        self.cluster_name = cluster_name
        self.instance_address = instance_address
        self.root_password = root_password
        self.server_config_password = server_config_password
        self.server_config_user = server_config_user

        try:
            self._ensure_mysqlsh_common_dir()
        except subprocess.CalledProcessError as e:
            logger.exception(
                f"Failed to ensure mysqlsh common dir for: {self.instance_address}", exc_info=e
            )
            raise MySQLInitializationError(e.stderr)

    @property
    def _mysqlsh_bin(self) -> str:
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

    @property
    def _mysqlsh_common_dir(self) -> str:
        """Determine snap common dir for mysqlsh.

        Raises MySQLUpdateConfigurationError if there was an issue configuring the mysql service.

        Returns:
            Path to common dir
        """
        return "/root/snap/mysql-shell/common"

    def update_mysql_configuration(self):
        """Add a configuration file for mysqld and restart the mysql service."""
        try:
            # target file starts with 'z-' so it has priority over the default config file
            shutil.copyfile("templates/mysqld.cnf", "/etc/mysql/mysql.conf.d/z-custom-mysqld.cnf")

            restart_mysql_command = ["systemctl", "restart", "mysql"]
            subprocess.check_output(restart_mysql_command, stderr=subprocess.PIPE)
        except Exception as e:
            logger.exception(
                f"Failed to update mysql config for: {self.instance_address}", exc_info=e
            )
            raise MySQLUpdateConfigurationError(e.stderr)

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

        commands = (
            "SET @@SESSION.SQL_LOG_BIN=0;",
            f"CREATE USER 'root'@'%' IDENTIFIED BY '{self.root_password}';",
            "GRANT ALL ON *.* TO 'root'@'%' WITH GRANT OPTION;",
            f"CREATE USER '{self.server_config_user}'@'%' IDENTIFIED BY '{self.server_config_password}';",
            f"GRANT ALL ON *.* TO '{self.server_config_user}'@'%' WITH GRANT OPTION;",
            "UPDATE mysql.user SET authentication_string=null WHERE User='root' and Host='localhost';",
            f"ALTER USER 'root'@'localhost' IDENTIFIED WITH mysql_native_password BY '{self.root_password}';",
            f"REVOKE {', '.join(privileges_to_revoke)} ON *.* FROM root@'%';",
            f"REVOKE {', '.join(privileges_to_revoke)} ON *.* FROM root@localhost;",
            "FLUSH PRIVILEGES;",
        )

        try:
            logger.debug("Configuring MySQL users=")
            self._run_mysqlcli_script(" ".join(commands))
        except subprocess.CalledProcessError as e:
            logger.exception(f"Failed to configure users for: {self.instance_address}", exc_info=e)
            raise MySQLConfigureMySQLUsersError(e.stdout)

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
        except subprocess.CalledProcessError as e:
            logger.exception(f"Failed to configure instance: {self.instance_address}", exc_info=e)
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
                f"Failed to create cluster on instance: {self.instance_address}", exc_info=e
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
                f"Failed to add instance {instance_address} to cluster {self.cluster_name}",
                exc_info=e,
            )
            raise MySQLAddInstanceToClusterError(e.stderr)

    @retry(reraise=True, stop=stop_after_delay(30), wait=wait_fixed(5))
    def _wait_until_mysql_connection(self) -> None:
        """Wait until a connection to MySQL has been obtained.

        Retry every 5 seconds for 30 seconds if there is an issue obtaining a connection.
        """
        commands = (
            f"my_shell = shell.connect('root:{self.root_password}@{self.instance_address}')",
        )

        self._run_mysqlsh_script("\n".join(commands))

    def _ensure_mysqlsh_common_dir(self) -> None:
        """Ensure that the mysql-shell common directory exists.

        Creates the directory by running 'mysqlsh --help' if it doesn't exist.
        """
        if not os.path.exists(self._mysqlsh_common_dir):
            # Execute mysqlsh to create self.mysqlsh_common_dir
            # This will only ever execute once
            cmd = [self._mysqlsh_bin, "--help"]
            subprocess.check_call(cmd, stderr=subprocess.PIPE)

    def _run_mysqlsh_script(self, script: str) -> None:
        """Execute a MySQL shell script.

        Raises CalledProcessError if the script gets a non-zero return code.

        Args:
            script: Mysqlsh script string

        Returns:
            Byte string subprocess output
        """
        self._ensure_mysqlsh_common_dir()

        # Use the self.mysqlsh_common_dir dir for the confined mysql-shell snap.
        with tempfile.NamedTemporaryFile(mode="w", dir=self._mysqlsh_common_dir) as _file:
            _file.write(script)
            _file.flush()

            # Specify python as this is not the default in the deb version
            # of the mysql-shell snap
            cmd = [self._mysqlsh_bin, "--no-wizard", "--python", "-f", _file.name]
            subprocess.check_output(cmd, stderr=subprocess.PIPE)

    def _run_mysqlcli_script(self, script: str) -> None:
        """Execute a MySQL CLI script.

        Execute SQL script as instance root user.
        Raises CalledProcessError if the script gets a non-zero return code.

        Args:
            script: raw SQL script string

        Returns:
            Byte string subprocess output
        """
        cmd = [
            "mysql",
            "-u",
            "root",
            "--protocol=SOCKET",
            "--socket=/var/run/mysqld/mysqld.sock",
            "-e",
            script,
        ]

        subprocess.check_output(cmd, stderr=subprocess.PIPE)
