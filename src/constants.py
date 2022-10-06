# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""File containing constants to be used in the charm."""

ROOT_USERNAME = "root"
CLUSTER_ADMIN_USERNAME = "clusteradmin"
SERVER_CONFIG_USERNAME = "serverconfig"
PASSWORD_LENGTH = 24
PEER = "database-peers"
LEGACY_DB_ROUTER = "db-router"
LEGACY_DB_SHARED = "shared-db"
LEGACY_MYSQL = "mysql"
DB_RELATION_NAME = "database"
ROOT_PASSWORD_KEY = "root-password"
SERVER_CONFIG_PASSWORD_KEY = "server-config-password"
CLUSTER_ADMIN_PASSWORD_KEY = "cluster-admin-password"
REQUIRED_USERNAMES = [ROOT_USERNAME, SERVER_CONFIG_USERNAME, CLUSTER_ADMIN_USERNAME]
SERVICE_NAME = "mysql.service"
