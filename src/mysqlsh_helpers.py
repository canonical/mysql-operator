#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Helper class to manage the MySQL InnoDB cluster lifecycle with MySQL Shell."""

import logging
import os
import subprocess
import tempfile

from tenacity import retry, stop_after_delay, wait_fixed

logger = logging.getLogger(__name__)


class MySQLInstanceConfigureError(Exception):
    """Exception raised when there is an issue configuring a MySQL instance."""

    pass


class MySQL:
    """Class to encapsulate all operations related to the MySQL instance and cluster.

    This class handles the configuration of MySQL instances, and also the
    creation and configuration of MySQL InnoDB clusters via Group Replication.
    """

    def __init__(
        self,
        root_password: str,
        cluster_admin_user: str,
        cluster_admin_password: str,
        instance_address: str,
    ):
        """Initialize the MySQL class.

        Args:
            root_password: password for the 'root' user
            cluster_admin_user: user name for the cluster admin user
            cluster_admin_password: password for the cluster admin user
            instance_address: address of the targeted instance
        """
        self.root_password = root_password
        self.cluster_admin_user = cluster_admin_user
        self.cluster_admin_password = cluster_admin_password
        self.instance_address = instance_address

    @property
    def mysqlsh_bin(self) -> str:
        """Determine binary path for MySQL Shell.

        Returns:
            Path to binary mysqlsh
        """
        # Allow for various versions of the mysql-shell snap
        # When we get the alias use /snap/bin/mysqlsh
        if os.path.exists("/snap/bin/mysqlsh"):
            return "/snap/bin/mysqlsh"
        if os.path.exists("/snap/bin/mysql-shell.mysqlsh"):
            return "/snap/bin/mysql-shell.mysqlsh"
        # Default to the full path version
        return "/snap/bin/mysql-shell"

    @property
    def mysqlsh_common_dir(self) -> str:
        """Determine snap common dir for mysqlsh.

        Returns:
            Path to common dir
        """
        return "/root/snap/mysql-shell/common"

    def configure_mysql_users(self):
        """Configure the MySQL users for the instance.

        Creates a 'clusteradmin' user with the appropriate privileges and
        revokes certain privileges from the 'root' user.
        """
        pass

    def configure_instance(self) -> None:
        """Configure the instance to be used in an InnoDB cluster."""
        commands = (
            f"dba.configure_instance('{self.cluster_admin_user}:{self.cluster_admin_password}@{self.instance_address}')",
            f"my_shell = shell.connect('{self.cluster_admin_user}:{self.cluster_admin_password}@{self.instance_address}')",
            'my_shell.run_sql("RESTART;");',
        )

        try:
            logger.debug("Configuring instance for InnoDB")
            self._run_mysqlsh_script("\n".join(commands))

            logger.debug("Waiting until MySQL is restarted")
            self._wait_until_mysql_connection()
        except subprocess.CalledProcessError as e:
            logger.exception(f"Failed to configure instance: {self.instance_address}", exc_info=e)
            raise MySQLInstanceConfigureError(e.stderr)

    def create_cluster(self) -> None:
        """Create an InnoDB cluster with Group Replication enabled."""
        pass

    def add_instance_to_cluster(self) -> None:
        """Add an instance to the InnoDB cluster."""
        pass

    @retry(reraise=True, stop=stop_after_delay(30), wait=wait_fixed(5))
    def _wait_until_mysql_connection(self) -> None:
        """Wait until a connection to MySQL has been obtained.

        Retry every 5 seconds for 30 seconds if there is an issue obtaining a connection.
        """
        commands = (
            f"my_shell = shell.connect('{self.cluster_admin_user}:{self.cluster_admin_password}@{self.instance_address}')",
        )

        self._run_mysqlsh_script("\n".join(commands))

    def _run_mysqlsh_script(self, script: str) -> None:
        """Execute a MySQL shell script.

        Raises CalledProcessError if the script gets a non-zero return code.

        Args:
            script: Mysqlsh script string

        Returns:
            Byte string subprocess output
        """
        if not os.path.exists(self.mysqlsh_common_dir):
            # Pre-execute mysqlsh to create self.mysqlsh_common_dir
            # If we don't do this the real execution will fail with an
            # ambiguous error message. This will only ever execute once.
            cmd = [self.mysqlsh_bin, "--help"]
            subprocess.check_call(cmd, stderr=subprocess.PIPE)

        # Use the self.mysqlsh_common_dir dir for the confined
        # mysql-shell snap.
        with tempfile.NamedTemporaryFile(mode="w", dir=self.mysqlsh_common_dir) as _file:
            _file.write(script)
            _file.flush()

            # Specify python as this is not the default in the deb version
            # of the mysql-shell snap
            cmd = [self.mysqlsh_bin, "--no-wizard", "--python", "-f", _file.name]
            subprocess.check_output(cmd, stderr=subprocess.PIPE)
