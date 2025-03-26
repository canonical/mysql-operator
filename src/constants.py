# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""File containing constants to be used in the charm."""

ROOT_USERNAME = "root"
CLUSTER_ADMIN_USERNAME = "clusteradmin"
SERVER_CONFIG_USERNAME = "serverconfig"
MONITORING_USERNAME = "monitoring"
BACKUPS_USERNAME = "backups"
PASSWORD_LENGTH = 24
PEER = "database-peers"
LEGACY_DB_ROUTER = "db-router"
LEGACY_DB_SHARED = "shared-db"
LEGACY_MYSQL = "mysql"
DB_RELATION_NAME = "database"
ROOT_PASSWORD_KEY = "root-password"
SERVER_CONFIG_PASSWORD_KEY = "server-config-password"
CLUSTER_ADMIN_PASSWORD_KEY = "cluster-admin-password"
MONITORING_PASSWORD_KEY = "monitoring-password"
BACKUPS_PASSWORD_KEY = "backups-password"
TLS_RELATION = "certificates"
TLS_SSL_CA_FILE = "custom-ca.pem"
TLS_SSL_KEY_FILE = "custom-server-key.pem"
TLS_SSL_CERT_FILE = "custom-server-cert.pem"
MYSQL_EXPORTER_PORT = 9104
CHARMED_MYSQL_SNAP_NAME = "charmed-mysql"
CHARMED_MYSQLD_EXPORTER_SERVICE = "mysqld-exporter"
CHARMED_MYSQLD_SERVICE = "mysqld"
CHARMED_MYSQL = "charmed-mysql.mysql"
CHARMED_MYSQLSH = "charmed-mysql.mysqlsh"
CHARMED_MYSQL_PITR_HELPER = "charmed-mysql.mysql-pitr-helper"
CHARMED_MYSQL_BINLOGS_COLLECTOR_SERVICE = "mysql-pitr-helper-collector"
CHARMED_MYSQL_COMMON_DIRECTORY = "/var/snap/charmed-mysql/common"
CHARMED_MYSQL_DATA_DIRECTORY = "/var/snap/charmed-mysql/current"
MYSQLD_SOCK_FILE = f"{CHARMED_MYSQL_COMMON_DIRECTORY}/var/run/mysqld/mysqld.sock"
MYSQLD_CONFIG_DIRECTORY = f"{CHARMED_MYSQL_DATA_DIRECTORY}/etc/mysql/mysql.conf.d"
MYSQLD_DEFAULTS_CONFIG_FILE = f"{CHARMED_MYSQL_DATA_DIRECTORY}/etc/mysql/mysql.cnf"
MYSQLD_CUSTOM_CONFIG_FILE = f"{MYSQLD_CONFIG_DIRECTORY}/z-custom-mysqld.cnf"
MYSQL_SYSTEM_USER = "snap_daemon"
MYSQL_DATA_DIR = f"{CHARMED_MYSQL_COMMON_DIRECTORY}/var/lib/mysql"
CHARMED_MYSQL_XTRABACKUP_LOCATION = "/snap/bin/charmed-mysql.xtrabackup"
CHARMED_MYSQL_XBCLOUD_LOCATION = "/snap/bin/charmed-mysql.xbcloud"
CHARMED_MYSQL_XBSTREAM_LOCATION = "/snap/bin/charmed-mysql.xbstream"
XTRABACKUP_PLUGIN_DIR = "/snap/charmed-mysql/current/usr/lib/xtrabackup/plugin"
ROOT_SYSTEM_USER = "root"
GR_MAX_MEMBERS = 9
HOSTNAME_DETAILS = "hostname-details"
COS_AGENT_RELATION_NAME = "cos-agent"
SECRET_KEY_FALLBACKS = {
    "root-password": "root_password",
    "server-config-password": "server_config_password",
    "cluster-admin-password": "cluster_admin_password",
    "monitoring-password": "monitoring_password",
    "backups-password": "backups_password",
    "certificate": "cert",
    "certificate-authority": "ca",
}
TRACING_PROTOCOL = "otlp_http"
