# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Helper class to manage the MySQL InnoDB cluster lifecycle with MySQL Shell."""

import logging
import os
import pathlib
import shutil
import socket
import subprocess
import tempfile
from typing import Dict, List, Optional, Tuple

from charms.mysql.v0.mysql import (
    BYTES_1MiB,
    Error,
    MySQLBase,
    MySQLClientError,
    MySQLExecError,
    MySQLGetAutoTunningParametersError,
    MySQLRestoreBackupError,
    MySQLServiceNotRunningError,
    MySQLStartMySQLDError,
    MySQLStopMySQLDError,
)
from charms.operator_libs_linux.v1 import snap
from tenacity import retry, stop_after_delay, wait_fixed

from constants import (
    CHARMED_MYSQL,
    CHARMED_MYSQL_COMMON_DIRECTORY,
    CHARMED_MYSQL_SNAP_NAME,
    CHARMED_MYSQL_SNAP_REVISION,
    CHARMED_MYSQL_XBCLOUD_LOCATION,
    CHARMED_MYSQL_XBSTREAM_LOCATION,
    CHARMED_MYSQL_XTRABACKUP_LOCATION,
    CHARMED_MYSQLD_EXPORTER_SERVICE,
    CHARMED_MYSQLD_SERVICE,
    CHARMED_MYSQLSH,
    MYSQL_DATA_DIR,
    MYSQL_SYSTEM_USER,
    MYSQLD_CONFIG_DIRECTORY,
    MYSQLD_DEFAULTS_CONFIG_FILE,
    MYSQLD_SOCK_FILE,
    ROOT_SYSTEM_USER,
    XTRABACKUP_PLUGIN_DIR,
)

logger = logging.getLogger(__name__)


class MySQLResetRootPasswordAndStartMySQLDError(Error):
    """Exception raised when there's an error resetting root password and starting mysqld."""


class MySQLCreateCustomMySQLDConfigError(Error):
    """Exception raised when there's an error creating custom mysqld config."""


class SnapServiceOperationError(Error):
    """Exception raised when there's an error running an operation on a snap service."""


class MySQLExporterConnectError(Error):
    """Exception raised when there's an error setting up MySQL exporter."""


class MySQLFlushHostCacheError(Error):
    """Exception raised when there's an error flushing the MySQL host cache."""


class MySQLInstallError(Error):
    """Exception raised when there's an error installing MySQL."""


class MySQL(MySQLBase):
    """Class to encapsulate all operations related to the MySQL instance and cluster.

    This class handles the configuration of MySQL instances, and also the
    creation and configuration of MySQL InnoDB clusters via Group Replication.
    """

    def __init__(
        self,
        instance_address: str,
        cluster_name: str,
        cluster_set_name: str,
        root_password: str,
        server_config_user: str,
        server_config_password: str,
        cluster_admin_user: str,
        cluster_admin_password: str,
        monitoring_user: str,
        monitoring_password: str,
        backups_user: str,
        backups_password: str,
    ):
        """Initialize the MySQL class.

        Args:
            instance_address: address of the targeted instance
            cluster_name: cluster name
            cluster_set_name: cluster set domain name
            root_password: password for the 'root' user
            server_config_user: user name for the server config user
            server_config_password: password for the server config user
            cluster_admin_user: user name for the cluster admin user
            cluster_admin_password: password for the cluster admin user
            monitoring_user: user name for the mysql exporter
            monitoring_password: password for the monitoring user
            backups_user: user name used to create backups
            backups_password: password for the backups user
        """
        super().__init__(
            instance_address=instance_address,
            cluster_name=cluster_name,
            cluster_set_name=cluster_set_name,
            root_password=root_password,
            server_config_user=server_config_user,
            server_config_password=server_config_password,
            cluster_admin_user=cluster_admin_user,
            cluster_admin_password=cluster_admin_password,
            monitoring_user=monitoring_user,
            monitoring_password=monitoring_password,
            backups_user=backups_user,
            backups_password=backups_password,
        )

    @staticmethod
    def install_and_configure_mysql_dependencies() -> None:
        """Install and configure MySQL dependencies.

        Raises
            subprocess.CalledProcessError: if issue creating mysqlsh common dir
            snap.SnapNotFoundError, snap.SnapError: if issue installing charmed-mysql snap
        """
        logger.debug("Retrieving snap cache")
        cache = snap.SnapCache()
        charmed_mysql = cache[CHARMED_MYSQL_SNAP_NAME]
        # This charm can override/use an existing snap installation only if the snap was previously
        # installed by this charm.
        # Otherwise, the snap could be in use by another charm (e.g. MySQL Router charm).
        installed_by_mysql_server_file = pathlib.Path(
            CHARMED_MYSQL_COMMON_DIRECTORY, "installed_by_mysql_server_charm"
        )
        if charmed_mysql.present and not installed_by_mysql_server_file.exists():
            logger.error(
                f"{CHARMED_MYSQL_SNAP_NAME} snap already installed on machine. Installation aborted"
            )
            raise Exception(
                f"Multiple {CHARMED_MYSQL_SNAP_NAME} snap installs not supported on one machine"
            )

        try:
            # install the charmed-mysql snap
            logger.debug("Installing charmed-mysql snap")
            charmed_mysql.ensure(snap.SnapState.Present, revision=CHARMED_MYSQL_SNAP_REVISION)

            # ensure creation of mysql shell common directory by running 'mysqlsh --help'
            if not os.path.exists(CHARMED_MYSQL_COMMON_DIRECTORY):
                logger.debug("Creating mysql shell common directory")
                mysqlsh_help_command = ["charmed-mysql.mysqlsh", "--help"]
                subprocess.check_call(mysqlsh_help_command, stderr=subprocess.PIPE)

            subprocess.run(["snap", "alias", "charmed-mysql.mysql", "mysql"], check=True)

            installed_by_mysql_server_file.touch(exist_ok=True)
        except snap.SnapError:
            logger.exception("Failed to install snaps")
            # reraise SnapError exception so the caller can retry
            raise
        except (subprocess.CalledProcessError, snap.SnapNotFoundError, Exception):
            logger.exception("Failed to install and configure MySQL dependencies")
            # other exceptions are not retried
            raise MySQLInstallError

    def create_custom_mysqld_config(self, profile: str) -> None:
        """Create custom mysql config file.

        Raises MySQLCreateCustomMySQLDConfigError if there is an error creating the
            custom mysqld config
        """
        group_replication_message_cache_size = None
        if profile == "testing":
            innodb_buffer_pool_size = 20 * BYTES_1MiB
            innodb_buffer_pool_chunk_size = 1 * BYTES_1MiB
            group_replication_message_cache_size = 128 * BYTES_1MiB
            max_connections = 20
        else:
            try:
                (
                    innodb_buffer_pool_size,
                    innodb_buffer_pool_chunk_size,
                    group_replication_message_cache_size,
                ) = self.get_innodb_buffer_pool_parameters()
                max_connections = self.get_max_connections()
            except MySQLGetAutoTunningParametersError:
                raise MySQLCreateCustomMySQLDConfigError(
                    "Failed to compute mysql parameters automatically"
                )

        content = [
            "[mysqld]",
            "bind-address = 0.0.0.0",
            "mysqlx-bind-address = 0.0.0.0",
            f"innodb_buffer_pool_size = {innodb_buffer_pool_size}",
            f"max_connections = {max_connections}",
        ]

        if innodb_buffer_pool_chunk_size:
            content.append(f"innodb_buffer_pool_chunk_size = {innodb_buffer_pool_chunk_size}")

        if group_replication_message_cache_size:
            content.append(
                f"loose-group_replication_message_cache_size = {group_replication_message_cache_size}"
            )

        content.append(f"report_host = {socket.getfqdn()}")
        content.append("")

        # create the mysqld config directory if it does not exist
        logger.debug("Copying custom mysqld config")
        pathlib.Path(MYSQLD_CONFIG_DIRECTORY).mkdir(mode=0o755, parents=True, exist_ok=True)

        with open(f"{MYSQLD_CONFIG_DIRECTORY}/z-custom-mysqld.cnf", "w") as config_file:
            config_file.write("\n".join(content))

    def reset_root_password_and_start_mysqld(self) -> None:
        """Reset the root user password and start mysqld."""
        logger.debug("Resetting root user password and starting mysqld")
        with tempfile.NamedTemporaryFile(
            dir=MYSQLD_CONFIG_DIRECTORY,
            prefix="z-custom-init-file.",
            suffix=".cnf",
            mode="w+",
            encoding="utf-8",
        ) as _custom_config_file:
            with tempfile.NamedTemporaryFile(
                dir=CHARMED_MYSQL_COMMON_DIRECTORY,
                prefix="alter-root-user.",
                suffix=".sql",
                mode="w",
                encoding="utf-8",
            ) as _sql_file:
                _sql_file.write(
                    f"ALTER USER 'root'@'localhost' IDENTIFIED BY '{self.root_password}';\n"
                    "FLUSH PRIVILEGES;"
                )
                _sql_file.flush()

                try:
                    subprocess.check_output(
                        [
                            "sudo",
                            "chown",
                            f"{MYSQL_SYSTEM_USER}:{ROOT_SYSTEM_USER}",
                            _sql_file.name,
                        ]
                    )
                except subprocess.CalledProcessError:
                    raise MySQLResetRootPasswordAndStartMySQLDError(
                        "Failed to change permissions for temp SQL file"
                    )

                _custom_config_file.write(f"[mysqld]\ninit_file = {_sql_file.name}")
                _custom_config_file.flush()

                try:
                    subprocess.check_output(
                        [
                            "sudo",
                            "chown",
                            f"{MYSQL_SYSTEM_USER}:{ROOT_SYSTEM_USER}",
                            _custom_config_file.name,
                        ]
                    )
                except subprocess.CalledProcessError:
                    raise MySQLResetRootPasswordAndStartMySQLDError(
                        "Failed to change permissions for custom mysql config"
                    )

                try:
                    snap_service_operation(
                        CHARMED_MYSQL_SNAP_NAME, CHARMED_MYSQLD_SERVICE, "start"
                    )
                except SnapServiceOperationError:
                    raise MySQLResetRootPasswordAndStartMySQLDError("Failed to restart mysqld")

                try:
                    self.wait_until_mysql_connection()
                except MySQLServiceNotRunningError:
                    raise MySQLResetRootPasswordAndStartMySQLDError("mysqld service not running")

    @retry(reraise=True, stop=stop_after_delay(120), wait=wait_fixed(5))
    def wait_until_mysql_connection(self) -> None:
        """Wait until a connection to MySQL has been obtained.

        Retry every 5 seconds for 120 seconds if there is an issue obtaining a connection.
        """
        logger.debug("Waiting for MySQL connection")
        if not os.path.exists(MYSQLD_SOCK_FILE):
            raise MySQLServiceNotRunningError("MySQL socket file not found")
        logger.debug("MySQL connection possible")

    def execute_backup_commands(
        self,
        s3_directory: str,
        s3_parameters: Dict[str, str],
    ) -> Tuple[str, str]:
        """Executes commands to create a backup."""
        return super().execute_backup_commands(
            s3_directory,
            s3_parameters,
            CHARMED_MYSQL_XTRABACKUP_LOCATION,
            CHARMED_MYSQL_XBCLOUD_LOCATION,
            XTRABACKUP_PLUGIN_DIR,
            MYSQLD_SOCK_FILE,
            CHARMED_MYSQL_COMMON_DIRECTORY,
            MYSQLD_DEFAULTS_CONFIG_FILE,
            user=ROOT_SYSTEM_USER,
            group=ROOT_SYSTEM_USER,
        )

    def delete_temp_backup_directory(
        self, from_directory: str = CHARMED_MYSQL_COMMON_DIRECTORY
    ) -> None:
        """Delete the temp backup directory."""
        super().delete_temp_backup_directory(
            from_directory,
            user=ROOT_SYSTEM_USER,
            group=ROOT_SYSTEM_USER,
        )

    def retrieve_backup_with_xbcloud(
        self,
        backup_id: str,
        s3_parameters: Dict[str, str],
    ) -> Tuple[str, str, str]:
        """Retrieve the provided backup with xbcloud."""
        return super().retrieve_backup_with_xbcloud(
            backup_id,
            s3_parameters,
            CHARMED_MYSQL_COMMON_DIRECTORY,
            CHARMED_MYSQL_XBCLOUD_LOCATION,
            CHARMED_MYSQL_XBSTREAM_LOCATION,
            user=ROOT_SYSTEM_USER,
            group=ROOT_SYSTEM_USER,
        )

    def prepare_backup_for_restore(self, backup_location: str) -> Tuple[str, str]:
        """Prepare the download backup for restore with xtrabackup --prepare."""
        return super().prepare_backup_for_restore(
            backup_location,
            CHARMED_MYSQL_XTRABACKUP_LOCATION,
            XTRABACKUP_PLUGIN_DIR,
            user=ROOT_SYSTEM_USER,
            group=ROOT_SYSTEM_USER,
        )

    def empty_data_files(self) -> None:
        """Empty the mysql data directory in preparation of the restore."""
        super().empty_data_files(
            MYSQL_DATA_DIR,
            user=ROOT_SYSTEM_USER,
            group=ROOT_SYSTEM_USER,
        )

    def restore_backup(
        self,
        backup_location: str,
    ) -> Tuple[str, str]:
        """Restore the provided prepared backup."""
        # TODO: remove workaround for changing permissions and ownership of data
        # files once restore backup commands can be run with snap_daemon user
        try:
            # provide write permissions to root (group owner of the data directory)
            # so the root user can move back files into the data directory
            command = f"chmod 770 {MYSQL_DATA_DIR}".split()
            subprocess.run(
                command,
                user=ROOT_SYSTEM_USER,
                group=ROOT_SYSTEM_USER,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as e:
            logger.exception("Failed to change data directory permissions before restoring")
            raise MySQLRestoreBackupError(e)

        stdout, stderr = super().restore_backup(
            backup_location,
            CHARMED_MYSQL_XTRABACKUP_LOCATION,
            MYSQLD_DEFAULTS_CONFIG_FILE,
            MYSQL_DATA_DIR,
            XTRABACKUP_PLUGIN_DIR,
            user=ROOT_SYSTEM_USER,
            group=ROOT_SYSTEM_USER,
        )

        try:
            # Revert permissions for the data directory
            command = f"chmod 750 {MYSQL_DATA_DIR}".split()
            subprocess.run(
                command,
                user=ROOT_SYSTEM_USER,
                group=ROOT_SYSTEM_USER,
                capture_output=True,
                text=True,
            )

            # Change ownership to the snap_daemon user since the restore files
            # are owned by root
            command = f"chown -R {MYSQL_SYSTEM_USER}:{ROOT_SYSTEM_USER} {MYSQL_DATA_DIR}".split()
            subprocess.run(
                command,
                user=ROOT_SYSTEM_USER,
                group=ROOT_SYSTEM_USER,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as e:
            logger.exception(
                "Failed to change data directory permissions or ownershp after restoring"
            )
            raise MySQLRestoreBackupError(e)

        return (stdout, stderr)

    def delete_temp_restore_directory(self) -> None:
        """Delete the temp restore directory from the mysql data directory."""
        super().delete_temp_restore_directory(
            CHARMED_MYSQL_COMMON_DIRECTORY,
            user=ROOT_SYSTEM_USER,
            group=ROOT_SYSTEM_USER,
        )

    def _execute_commands(
        self,
        commands: List[str],
        bash: bool = False,
        user: str = None,
        group: str = None,
        env_extra: Dict = None,
    ) -> Tuple[str, str]:
        """Execute commands on the server where mysql is running.

        Args:
            commands: a list containing the commands to execute
            bash: whether to run the commands with bash
            user: the user with which to execute the commands
            group: the group with which to execute the commands
            env_extra: the environment variables to add to the current process’ environment

        Returns: tuple of (stdout, stderr)

        Raises: MySQLExecError if there was an error executing the commands
        """
        env = os.environ.copy()
        if env_extra:
            env.update(env_extra)
        try:
            if bash:
                commands = ["bash", "-c", "set -o pipefail; " + " ".join(commands)]

            process = subprocess.run(
                commands,
                user=user,
                group=group,
                env=env,
                capture_output=True,
                check=True,
                encoding="utf-8",
            )
            return (process.stdout.strip(), process.stderr.strip())
        except subprocess.CalledProcessError as e:
            logger.debug(f"Failed command: {commands}; user={user}; group={group}")
            raise MySQLExecError(e.stderr)

    def is_mysqld_running(self) -> bool:
        """Returns whether mysqld is running."""
        return os.path.exists(MYSQLD_SOCK_FILE)

    def is_server_connectable(self) -> bool:
        """Returns whether the server is connectable."""
        # Always true since the charm runs on the same server as mysqld
        return True

    def stop_mysqld(self) -> None:
        """Stops the mysqld process."""
        logger.info(
            f"Stopping service snap={CHARMED_MYSQL_SNAP_NAME}, service={CHARMED_MYSQLD_SERVICE}"
        )

        try:
            snap_service_operation(CHARMED_MYSQL_SNAP_NAME, CHARMED_MYSQLD_SERVICE, "stop")
        except SnapServiceOperationError as e:
            raise MySQLStopMySQLDError(e.message)

    def start_mysqld(self) -> None:
        """Starts the mysqld process."""
        logger.info(
            f"Starting service snap={CHARMED_MYSQL_SNAP_NAME}, service={CHARMED_MYSQLD_SERVICE}"
        )

        try:
            snap_service_operation(CHARMED_MYSQL_SNAP_NAME, CHARMED_MYSQLD_SERVICE, "start")
            self.wait_until_mysql_connection()
        except (
            MySQLServiceNotRunningError,
            SnapServiceOperationError,
        ) as e:
            if isinstance(e, MySQLServiceNotRunningError):
                logger.exception("Failed to start mysqld")

            raise MySQLStartMySQLDError(e.message)

    def flush_host_cache(self) -> None:
        """Flush the MySQL in-memory host cache."""
        flush_host_cache_command = "TRUNCATE TABLE performance_schema.host_cache"

        try:
            logger.debug("Truncating the MySQL host cache")
            self._run_mysqlcli_script(
                flush_host_cache_command,
                user=self.server_config_user,
                password=self.server_config_password,
            )
        except MySQLClientError as e:
            logger.exception("Failed to truncate the MySQL host cache")
            raise MySQLFlushHostCacheError(e.message)

    def connect_mysql_exporter(self) -> None:
        """Set up mysqld-exporter config options.

        Raises
            snap.SnapError: if an issue occurs during config setting or restart
        """
        cache = snap.SnapCache()
        mysqld_snap = cache[CHARMED_MYSQL_SNAP_NAME]

        try:
            # Set up exporter credentials
            mysqld_snap.set(
                {
                    "exporter.user": self.monitoring_user,
                    "exporter.password": self.monitoring_password,
                }
            )
            snap_service_operation(
                CHARMED_MYSQL_SNAP_NAME, CHARMED_MYSQLD_EXPORTER_SERVICE, "start"
            )
        except snap.SnapError:
            logger.exception("An exception occurred when setting up mysqld-exporter.")
            raise MySQLExporterConnectError("Error setting up mysqld-exporter")

    def stop_mysql_exporter(self) -> None:
        """Stop the mysqld exporter."""
        try:
            snap_service_operation(
                CHARMED_MYSQL_SNAP_NAME, CHARMED_MYSQLD_EXPORTER_SERVICE, "stop"
            )
        except snap.SnapError:
            logger.exception("An exception occurred when stopping mysqld-exporter")
            raise MySQLExporterConnectError("Error stopping mysqld-exporter")

    def restart_mysql_exporter(self) -> None:
        """Restart the mysqld exporter."""
        self._stop_mysql_exporter()
        self._connect_mysql_exporter()

    def _run_mysqlsh_script(self, script: str, timeout=None) -> str:
        """Execute a MySQL shell script.

        Raises CalledProcessError if the script gets a non-zero return code.

        Args:
            script: Mysqlsh script string

        Returns:
            String representing the output of the mysqlsh command
        """
        # Use the self.mysqlsh_common_dir for the confined mysql-shell snap.
        with tempfile.NamedTemporaryFile(mode="w", dir=CHARMED_MYSQL_COMMON_DIRECTORY) as _file:
            _file.write(script)
            _file.flush()

            command = [CHARMED_MYSQLSH, "--no-wizard", "--python", "-f", _file.name]

            try:
                # need to change permissions since charmed-mysql.mysqlsh runs as
                # snap_daemon
                shutil.chown(_file.name, user="snap_daemon", group="root")

                return subprocess.check_output(
                    command, stderr=subprocess.PIPE, timeout=timeout
                ).decode("utf-8")
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
                raise MySQLClientError(e.stderr)

    def _run_mysqlcli_script(
        self, script: str, user: str = "root", password: str = None, timeout: Optional[int] = None
    ) -> str:
        """Execute a MySQL CLI script.

        Execute SQL script as instance root user.
        Raises CalledProcessError if the script gets a non-zero return code.

        Args:
            script: raw SQL script string
            user: (optional) user to invoke the mysql cli script with (default is "root")
            password: (optional) password to invoke the mysql cli script with
            timeout: (optional) time before the query should timeout
        """
        command = [
            CHARMED_MYSQL,
            "-u",
            user,
            "--protocol=SOCKET",
            f"--socket={MYSQLD_SOCK_FILE}",
            "-e",
            script,
        ]

        if password:
            command.append(f"--password={password}")

        try:
            return subprocess.check_output(
                command, stderr=subprocess.PIPE, timeout=timeout
            ).decode("utf-8")
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

    @staticmethod
    def write_content_to_file(
        path: str,
        content: str,
        owner: str = MYSQL_SYSTEM_USER,
        group: str = "root",
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


def is_volume_mounted() -> bool:
    """Returns if data directory is attached."""
    try:
        subprocess.check_call(["mountpoint", "-q", CHARMED_MYSQL_COMMON_DIRECTORY])
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


def snap_service_operation(snapname: str, service: str, operation: str) -> bool:
    """Helper function to run an operation on a snap service.

    Args:
        snapname: The name of the snap
        service: The name of the service
        operation: The name of the operation (restart, start, stop)
        enable: (optional) A bool indicating if the service should be enabled or disabled on start

    Returns:
        a bool indicating if the operation was successful.
    """
    if operation not in ["restart", "start", "stop"]:
        raise SnapServiceOperationError(f"Invalid snap service operation {operation}")

    try:
        cache = snap.SnapCache()
        selected_snap = cache[snapname]

        if not selected_snap.present:
            raise SnapServiceOperationError(f"Snap {snapname} not installed")

        if operation == "restart":
            selected_snap.restart(services=[service])
            return selected_snap.services[service]["active"]
        elif operation == "start":
            selected_snap.start(services=[service], enable=True)
            return selected_snap.services[service]["active"]
        else:
            selected_snap.stop(services=[service], disable=True)
            return not selected_snap.services[service]["active"]
    except snap.SnapError:
        error_message = f"Failed to run snap service operation, snap={snapname}, service={service}, operation={operation}"
        logger.exception(error_message)
        raise SnapServiceOperationError(error_message)
