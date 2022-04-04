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


class MySQL:
    """Class to encapsulate all operations related to the MySQL instance and cluster.

    This class handles the configuration of MySQL instances, and also the
    creation and configuration of MySQL InnoDB clusters via Group Replication.
    """

    def __init__(self):
        pass

    @property
    def mysqlsh_bin(self) -> str:
        """Determine binary path for MySQL Shell.

        :returns: Path to binary mysqlsh
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

        :returns: Path to common dir
        """
        return "/root/snap/mysql-shell/common"

    def configure_mysql_users(self):
        """Configure the MySQL users for the instance.

        Creates a 'clusteradmin' user with the appropriate privileges and
        revokes certain privileges from the 'root' user.
        """
        pass

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

        :param script: Mysqlsh script
        :raises subprocess.CalledProcessError: Raises CalledProcessError if the
                                               script gets a non-zero return
                                               code.
        :returns: subprocess output
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
