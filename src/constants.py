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
TLS_RELATION = "certificates"
TLS_SSL_CA_FILE = "custom-ca.pem"
TLS_SSL_KEY_FILE = "custom-server-key.pem"
TLS_SSL_CERT_FILE = "custom-server-cert.pem"
SERVICE_NAME = "mysql.service"
MYSQL_SHELL_SNAP_NAME = "mysql-shell"
MYSQL_APT_PACKAGE_NAME = "mysql-server-8.0"
MYSQL_SHELL_COMMON_DIRECTORY = "/root/snap/mysql-shell/common"
MYSQLD_SOCK_FILE = "/var/run/mysqld/mysqld.sock"
MYSQLD_CONFIG_DIRECTORY = "/etc/mysql/mysql.conf.d"
MYSQL_SYSTEM_USER = "mysql"
MYSQL_DATA_DIR = "/var/lib/mysql"
