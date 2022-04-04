#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Helper class to manage the MySQL InnoDB cluster lifecycle with MySQL Shell."""

import logging

logger = logging.getLogger(__name__)


class MySQL:
    """Class to encapsulate all operations related to the MySQL instance and cluster.

    This class handles the configuration of MySQL instances, and also the
    creation and configuration of MySQL InnoDB clusters via Group Replication.
    """

    def __init__(self):
        pass

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
