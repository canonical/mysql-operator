#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charmed Machine Operator for MySQL."""

import hashlib
import logging
import secrets
import string

from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus

from mysqlsh_helpers import (
    MySQL,
    MySQLConfigureInstanceError,
    MySQLConfigureMySQLUsersError,
)

logger = logging.getLogger(__name__)

PASSWORD_LENGTH = 24
PEER = "mysql-replicas"


def generate_random_password(length: int) -> str:
    """Randomly generate a string intended to be used as a password.

    Args:
        length: length of the randomly generated string to be returned
    """
    choices = string.ascii_letters + string.digits
    return "".join([secrets.choice(choices) for i in range(length)])


def generate_random_hash() -> str:
    """Generate a hash based on a random string."""
    random_characters = generate_random_password(10)
    return hashlib.md5(random_characters.encode("utf-8")).hexdigest()


class MySQLOperatorCharm(CharmBase):
    """Operator framework charm for MySQL."""

    def __init__(self, *args):
        super().__init__(*args)

        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.start, self._on_start)

    # =======================
    #  Charm Lifecycle Hooks
    # =======================

    def _on_install(self, _) -> None:
        """Initial setup operations like installing dependencies, and creating users and groups."""
        self.unit.status = MaintenanceStatus("Installing MySQL")

        try:
            MySQL.install_and_configure_mysql_dependencies()
        except Exception:
            self.unit.status = BlockedStatus("Failed to install and configure MySQL")
            return

        self.unit.status = WaitingStatus("Waiting to start MySQL")

    def _on_start(self, _) -> None:
        """Ensure that required software is running."""
        try:
            # TODO: add logic to determine how to add non-leader instances to the cluster
            if self.unit.is_leader():
                self._mysql.configure_mysql_users()
                self._mysql.configure_instance()
        except MySQLConfigureMySQLUsersError:
            self.unit.status = BlockedStatus("Failed to initialize MySQL users")
            return
        except MySQLConfigureInstanceError:
            self.unit.status = BlockedStatus("Failed to configure instance for InnoDB")
            return

        self.unit.status = ActiveStatus()

    # =======================
    #  Helpers
    # =======================

    def _get_mysql_helpers(self):
        """Returns an instance of the MySQL object from mysqlsh_helpers."""
        mysql_configs = self._get_or_create_mysql_configs()

        return MySQL(
            mysql_configs["unit_ip"],
            mysql_configs["cluster_name"],
            mysql_configs["root_password"],
            "serverconfig",
            mysql_configs["server_config_password"],
            "clusteradmin",
            mysql_configs["cluster_admin_password"],
        )

        return self._mysql_helpers

    def _get_or_create_mysql_configs(self):
        peer_relation = self.model.get_relation(PEER)
        if peer_relation is None:
            raise Exception(f"Peer relation {PEER} has not yet been established")

        mysql_configs = {
            "unit_ip": self.model.get_binding(PEER).network.bind_address,
            "cluster_name": peer_relation.data[self.app].get("cluster_name"),
            "root_password": peer_relation.data[self.app].get("root_password"),
            "server_config_password": peer_relation.data[self.app].get("server_config_password"),
            "cluster_admin_password": peer_relation.data[self.app].get("cluster_admin_password"),
        }

        is_unit_leader = self.unit.is_leader()
        has_missing_peer_data = any([value is None for value in mysql_configs.values()])
        if has_missing_peer_data and not is_unit_leader:
            raise Exception("Trying to store data in peer relation on non-leader unit")

        if not mysql_configs["cluster_name"]:
            cluster_name = self.config.get("cluster_name") or generate_random_hash()
            peer_relation.data[self.app]["cluster_name"] = cluster_name
            mysql_configs["cluster_name"] = cluster_name

        if not mysql_configs["root_password"]:
            root_password = generate_random_password(PASSWORD_LENGTH)
            peer_relation.data[self.app]["root_password"] = root_password
            mysql_configs["root_password"] = root_password

        if not mysql_configs["server_config_password"]:
            server_config_password = generate_random_password(PASSWORD_LENGTH)
            peer_relation.data[self.app]["server_config_password"] = server_config_password
            mysql_configs["server_config_password"] = server_config_password

        if not mysql_configs["cluster_admin_password"]:
            cluster_admin_password = generate_random_password(PASSWORD_LENGTH)
            peer_relation.data[self.app]["cluster_admin_password"] = cluster_admin_password
            mysql_configs["cluster_admin_password"] = cluster_admin_password

        return mysql_configs


if __name__ == "__main__":
    main(MySQLOperatorCharm)
