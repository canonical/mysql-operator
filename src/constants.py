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
CHARMED_MYSQL_SNAP_NAME = "charmed-mysql"
CHARMED_MYSQLD_SERVICE = "mysqld"
CHARMED_MYSQL = "charmed-mysql.mysql"
CHARMED_MYSQLSH = "charmed-mysql.mysqlsh"
CHARMED_MYSQL_COMMON_DIRECTORY = "/var/snap/charmed-mysql/common"
MYSQLD_SOCK_FILE = f"{CHARMED_MYSQL_COMMON_DIRECTORY}/mysql/mysqld.sock"
MYSQLD_CONFIG_DIRECTORY = f"{CHARMED_MYSQL_COMMON_DIRECTORY}/mysql/conf.d"
MYSQL_SYSTEM_USER = "snap_daemon"
MYSQL_DATA_DIR = f"{CHARMED_MYSQL_COMMON_DIRECTORY}/mysql/data"
S3_INTEGRATOR_RELATION_NAME = "s3-parameters"
