# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Helper class to manage the MySQL InnoDB cluster lifecycle with MySQL Shell."""

import logging
import os
import pathlib
import shutil
import subprocess
import tempfile

from charms.mysql.v0.mysql import Error, MySQLBase, MySQLClientError
from charms.operator_libs_linux.v0 import apt
from charms.operator_libs_linux.v1 import snap
from tenacity import retry, stop_after_delay, wait_fixed

from constants import (
    MYSQL_APT_PACKAGE_NAME,
    MYSQL_DATA_DIR,
    MYSQL_EXPORTER_SNAP_NAME,
    MYSQL_SHELL_COMMON_DIRECTORY,
    MYSQL_SHELL_SNAP_NAME,
    MYSQL_SYSTEM_USER,
    MYSQLD_CONFIG_DIRECTORY,
    MYSQLD_SOCK_FILE,
    NODE_EXPORTER_SNAP_NAME,
    XTRABACKUP_SNAP_NAME,
)

logger = logging.getLogger(__name__)


class MySQLServiceNotRunningError(Error):
    """Exception raised when the MySQL service is not running."""


class MySQLReconfigureError(Error):
    """Exception raised when the MySQL server fails to bootstrap."""


class MySQLDataPurgeError(Error):
    """Exception raised when there's an error purging data dir."""


class MySQL(MySQLBase):
    """Class to encapsulate all operations related to the MySQL instance and cluster.

    This class handles the configuration of MySQL instances, and also the
    creation and configuration of MySQL InnoDB clusters via Group Replication.
    """

    def __init__(
        self,
        instance_address: str,
        cluster_name: str,
        root_password: str,
        server_config_user: str,
        server_config_password: str,
        cluster_admin_user: str,
        cluster_admin_password: str,
        monitoring_user: str,
        monitoring_password: str,
    ):
        """Initialize the MySQL class.

        Args:
            instance_address: address of the targeted instance
            cluster_name: cluster name
            root_password: password for the 'root' user
            server_config_user: user name for the server config user
            server_config_password: password for the server config user
            cluster_admin_user: user name for the cluster admin user
            cluster_admin_password: password for the cluster admin user
            monitoring_user: user name for the mysql exporter
            monitoring_password: password for the monitoring user
        """
        super().__init__(
            instance_address=instance_address,
            cluster_name=cluster_name,
            root_password=root_password,
            server_config_user=server_config_user,
            server_config_password=server_config_password,
            cluster_admin_user=cluster_admin_user,
            cluster_admin_password=cluster_admin_password,
            monitoring_user=monitoring_user,
            monitoring_password=monitoring_password,
        )

    @staticmethod
    def get_mysqlsh_bin() -> str:
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

    @staticmethod
    def install_and_configure_mysql_dependencies() -> None:
        """Install and configure MySQL dependencies.

        Raises
            subprocess.CalledProcessError: if issue updating apt or creating mysqlsh common dir
            apt.PackageNotFoundError, apt.PackageError: if issue install mysql server
            snap.SnapNotFOundError, snap.SnapError: if issue installing mysql shell snap
        """
        try:
            # create the mysqld config directory if it does not exist
            logger.debug("Copying custom mysqld config")
            pathlib.Path(MYSQLD_CONFIG_DIRECTORY).mkdir(mode=0o755, parents=True, exist_ok=True)
            # target file has prefix 'z-' to ensure priority over the default mysqld config file
            shutil.copyfile(
                "templates/mysqld.cnf", f"{MYSQLD_CONFIG_DIRECTORY}/z-custom-mysqld.cnf"
            )

            # install mysql server
            logger.debug("Updating apt")
            apt.update()
            logger.debug("Installing mysql server")
            apt.add_package(MYSQL_APT_PACKAGE_NAME)

            # install mysql shell if not already installed
            logger.debug("Retrieving snap cache")
            cache = snap.SnapCache()
            mysql_shell = cache[MYSQL_SHELL_SNAP_NAME]
            xtrabackup = cache[XTRABACKUP_SNAP_NAME]
            mysql_exporter = cache[MYSQL_EXPORTER_SNAP_NAME]
            node_exporter = cache[NODE_EXPORTER_SNAP_NAME]

            if not mysql_shell.present:
                logger.debug("Installing mysql shell snap")
                mysql_shell.ensure(snap.SnapState.Latest, channel="edge")

            # ensure creation of mysql shell common directory by running 'mysqlsh --help'
            if not os.path.exists(MYSQL_SHELL_COMMON_DIRECTORY):
                logger.debug("Creating mysql shell common directory")
                mysqlsh_help_command = [MySQL.get_mysqlsh_bin(), "--help"]
                subprocess.check_call(mysqlsh_help_command, stderr=subprocess.PIPE)

            # install xtrabackup snap and connect system-files interface
            if not xtrabackup.present:
                logger.debug("Installing xtrabackup snap")
                xtrabackup.ensure(snap.SnapState.Latest, channel="edge")

            # install mysqld-exporter snap
            mysql_exporter.ensure(snap.SnapState.Latest, channel="edge")

            # install node-exporter snap
            node_exporter.ensure(snap.SnapState.Latest, channel="edge")
            node_exporter_plugs = [
                "hardware-observe",
                "network-observe",
                "mount-observe",
                "system-observe",
            ]
            for plug in node_exporter_plugs:
                node_exporter.connect(plug=plug)

        except subprocess.CalledProcessError as e:
            logger.exception("Failed to execute subprocess command", exc_info=e)
            raise
        except (apt.PackageNotFoundError, apt.PackageError) as e:
            logger.exception("Failed to install apt packages", exc_info=e)
            raise
        except (snap.SnapNotFoundError, snap.SnapError) as e:
            logger.exception("Failed to install snaps", exc_info=e)
            raise
        except Exception as e:
            logger.exception("Encountered an unexpected exception", exc_info=e)
            raise

    @retry(reraise=True, stop=stop_after_delay(30), wait=wait_fixed(5))
    def wait_until_mysql_connection(self) -> None:
        """Wait until a connection to MySQL has been obtained.

        Retry every 5 seconds for 30 seconds if there is an issue obtaining a connection.
        """
        if not os.path.exists(MYSQLD_SOCK_FILE):
            raise MySQLServiceNotRunningError()

    def connect_mysql_exporter(self) -> None:
        """Set up mysqld-exporter config options.

        Raises
            snap.SnapError: if an issue occurs during config setting or restart
        """
        cache = snap.SnapCache()
        mysqld_exporter = cache[MYSQL_EXPORTER_SNAP_NAME]

        try:
            # Set up exporter with connection info and disable metrics
            mysqld_exporter.set(
                {
                    "mysql.host": "unix(/var/run/mysqld/mysqld.sock)",
                    "mysql.user": self.monitoring_user,
                    "mysql.password": self.monitoring_password,
                    "collect.auto_increment.columns": False,
                    "collect.info_schema.tables": False,
                    "collect.info_schema.tablestats": False,
                    "collect.perf_schema.indexiowaits": False,
                    "collect.perf_schema.tableiowaits": False,
                    "collect.perf_schema.tablelocks": False,
                    "collect.info_schema.userstats": False,
                    "collect.binlog_size": False,
                    "collect.info_schema.processlist": False,
                }
            )
            mysqld_exporter.restart()
        except snap.SnapError as e:
            logger.error(
                "An exception occurred when setting configs for mysqld-exporter snap. Reason: %s"
                % e.message
            )
            raise

    def _run_mysqlsh_script(self, script: str, timeout=None) -> str:
        """Execute a MySQL shell script.

        Raises CalledProcessError if the script gets a non-zero return code.

        Args:
            script: Mysqlsh script string

        Returns:
            String representing the output of the mysqlsh command
        """
        # Use the self.mysqlsh_common_dir for the confined mysql-shell snap.
        with tempfile.NamedTemporaryFile(mode="w", dir=MYSQL_SHELL_COMMON_DIRECTORY) as _file:
            _file.write(script)
            _file.flush()

            # Specify python as this is not the default in the deb version
            # of the mysql-shell snap
            command = [MySQL.get_mysqlsh_bin(), "--no-wizard", "--python", "-f", _file.name]

            try:
                return subprocess.check_output(
                    command, stderr=subprocess.PIPE, timeout=timeout
                ).decode("utf-8")
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
                raise MySQLClientError(e.stderr)

    def _run_mysqlcli_script(self, script: str, user: str = "root", password: str = None) -> str:
        """Execute a MySQL CLI script.

        Execute SQL script as instance root user.
        Raises CalledProcessError if the script gets a non-zero return code.

        Args:
            script: raw SQL script string
            user: (optional) user to invoke the mysql cli script with (default is "root")
            password: (optional) password to invoke the mysql cli script with
        """
        command = [
            "mysql",
            "-u",
            user,
            "--protocol=SOCKET",
            "--socket=/var/run/mysqld/mysqld.sock",
            "-e",
            script,
        ]

        if password:
            command.append(f"--password={password}")

        try:
            return subprocess.check_output(command, stderr=subprocess.PIPE).decode("utf-8")
        except subprocess.CalledProcessError as e:
            raise MySQLClientError(e.stderr)

    def is_data_dir_initialised(self) -> bool:
        """Check if data dir is initialised.

        Returns:
            A bool for an initialised and integral data dir.
        """
        try:
            content = os.listdir(MYSQL_DATA_DIR)

            # minimal expected content for an integral mysqld data-dir
            expected_content = {
                "mysql",
                "public_key.pem",
                "sys",
                "ca.pem",
                "client-key.pem",
                "mysql.ibd",
                "auto.cnf",
                "server-cert.pem",
                "ib_buffer_pool",
                "server-key.pem",
                "undo_002",
                "#innodb_redo",
                "undo_001",
                "#innodb_temp",
                "private_key.pem",
                "client-cert.pem",
                "ca-key.pem",
                "performance_schema",
            }

            return expected_content <= set(content)
        except FileNotFoundError:
            return False

    def reset_data_dir(self) -> None:
        """Reset a data directory to a pristine state."""
        logger.info("Purge data directory")
        try:
            for file_name in os.listdir(MYSQL_DATA_DIR):
                file_path = os.path.join(MYSQL_DATA_DIR, file_name)
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
        except OSError:
            logger.error(f"Failed to remove {file_path}")
            raise MySQLDataPurgeError("Failed to purge data")

    def reconfigure_mysqld(self) -> None:
        """Reconfigure mysql-server package.

        Reconfiguring mysql-package recreates data structures as if it was newly installed.

        Raises:
            MySQLReconfigureError: Error occurred when reconfiguring server package.
        """
        bootstrap_command = ["dpkg-reconfigure", MYSQL_APT_PACKAGE_NAME]

        logger.info("Reconfiguring mysql-server package")
        try:
            subprocess.check_call(bootstrap_command)
        except subprocess.CalledProcessError:
            logger.debug("Failed to reconfigure package")
            raise MySQLReconfigureError("Failed to reconfigure mysql-server")


def is_data_dir_attached() -> bool:
    """Returns if data directory is attached."""
    try:
        subprocess.check_call(["mountpoint", "-q", MYSQL_DATA_DIR])
        return True
    except subprocess.CalledProcessError:
        return False


def reboot_system() -> None:
    """Reboot host machine."""
    try:
        subprocess.check_call(["systemctl", "reboot"])
    except subprocess.CalledProcessError:
        pass


def instance_hostname():
    """Retrieve machine hostname."""
    try:
        raw_hostname = subprocess.check_output(["hostname"])

        return raw_hostname.decode("utf8").strip()
    except subprocess.CalledProcessError as e:
        logger.exception("Failed to retrieve hostname", e)
        return None


def write_content_to_file(
    path: str,
    content: str,
    owner: str = MYSQL_SYSTEM_USER,
    group: str = MYSQL_SYSTEM_USER,
    permission: int = 0o640,
) -> None:
    """Write content to file.

    Args:
        path: filesystem full path (with filename)
        content: string content to write
        owner: file owner
        group: file group
        permission: file permission
    """
    with open(path, "w", encoding="utf-8") as fd:
        fd.write(content)

    shutil.chown(path, owner, group)
    os.chmod(path, mode=permission)
