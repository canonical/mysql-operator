#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Helper class to manage the MySQL InnoDB cluster lifecycle with MySQL Shell."""

import logging
import os
import subprocess
import tempfile
from typing import AnyStr

logger = logging.getLogger(__name__)


class MySQLCreateUserError(Exception):
    """Exception raised when creating a user fails."""

    pass


class MySQL:
    """Class to encapsulate all operations related to the MySQL instance and cluster.

    This class handles the configuration of MySQL instances, and also the
    creation and configuration of MySQL InnoDB clusters via Group Replication.
    """

    def __init__(self, root_password: str, cluster_admin_user: str, cluster_admin_password: str):
        """Initialize the MySQL class.

        Args:
            root_password: Password for the 'root' user
            cluster_admin_user: User name for the cluster admin user
            cluster_admin_password: Password for the cluster admin user
        """
        self.root_password = root_password
        self.cluster_admin_user = cluster_admin_user
        self.cluster_admin_password = cluster_admin_password
        self.instance_address = None

    @property
    def mysqlsh_bin(self) -> str:
        """Determine binary path for MySQL Shell.

        Returns:
            Path to binary mysqlsh
        """
        # Allow for various versions of the mysql-shell snap
        # When we get the alias use /snap/bin/mysqlsh
        if os.path.exists("/usr/bin/mysqlsh"):
            return "/usr/bin/mysqlsh"
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
        if os.path.exists("/root/snap/mysql-shell/common"):
            return "/root/snap/mysql-shell/common"
        else:
            return "/tmp"

    def configure_mysql_users(self):
        """Configure the MySQL users for the instance.

        Creates a 'clusteradmin' user with the appropriate privileges and
        revokes certain privileges from the 'root' user.
        """
        _script = (
            f'shell.connect("root:{self.root_password}@localhost")',
            f"dba.session.run_sql(\"CREATE USER '{self.cluster_admin_user}'@'%' IDENTIFIED BY '{self.cluster_admin_password}' ;\")",
            f"dba.session.run_sql(\"GRANT ALL ON *.* TO '{self.cluster_admin_user}'@'%' WITH GRANT OPTION ;\")",
            'dba.session.run_sql("REVOKE SYSTEM_USER ON *.* FROM root ;")',
        )

        try:
            output = self.run_mysqlsh_script("\n".join(_script))
            return output.decode("utf-8")
        except subprocess.CalledProcessError as e:
            logger.exception(f"Failed to configure instance: {self.instance_address}", exc_info=e)
            raise MySQLCreateUserError(e.stdout)

    def configure_instance(self):
        """Configure the instance to be used in an InnoDB cluster."""
        pass

    def create_cluster(self):
        """Create an InnoDB cluster with Group Replication enabled."""
        pass

    def add_instance_to_cluster(self):
        """Add an instance to the InnoDB cluster."""
        pass

    def run_mysqlsh_script(self, script: str) -> AnyStr:
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
            return subprocess.check_output(cmd, stderr=subprocess.PIPE)
