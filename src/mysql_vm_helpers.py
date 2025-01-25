# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Helper class to manage the MySQL InnoDB cluster lifecycle with MySQL Shell."""

import json
import logging
import os
import pathlib
import platform
import shutil
import subprocess
import tempfile
import typing
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

import jinja2
import pexpect
from charms.mysql.v0.mysql import (
    BYTES_1MB,
    Error,
    MySQLBase,
    MySQLClientError,
    MySQLExecError,
    MySQLGetAutoTuningParametersError,
    MySQLGetAvailableMemoryError,
    MySQLKillSessionError,
    MySQLRestoreBackupError,
    MySQLServiceNotRunningError,
    MySQLStartMySQLDError,
    MySQLStopMySQLDError,
)
from charms.operator_libs_linux.v2 import snap
from tenacity import RetryError, Retrying, retry, stop_after_attempt, stop_after_delay, wait_fixed
from typing_extensions import override

from constants import (
    CHARMED_MYSQL,
    CHARMED_MYSQL_BINLOGS_COLLECTOR_SERVICE,
    CHARMED_MYSQL_COMMON_DIRECTORY,
    CHARMED_MYSQL_DATA_DIRECTORY,
    CHARMED_MYSQL_SNAP_NAME,
    CHARMED_MYSQL_XBCLOUD_LOCATION,
    CHARMED_MYSQL_XBSTREAM_LOCATION,
    CHARMED_MYSQL_XTRABACKUP_LOCATION,
    CHARMED_MYSQLD_EXPORTER_SERVICE,
    CHARMED_MYSQLD_SERVICE,
    CHARMED_MYSQLSH,
    MYSQL_BINLOGS_COLLECTOR_CONFIG_FILE,
    MYSQL_DATA_DIR,
    MYSQL_SYSTEM_USER,
    MYSQLD_CONFIG_DIRECTORY,
    MYSQLD_CUSTOM_CONFIG_FILE,
    MYSQLD_DEFAULTS_CONFIG_FILE,
    MYSQLD_SOCK_FILE,
    ROOT_SYSTEM_USER,
    XTRABACKUP_PLUGIN_DIR,
)

logger = logging.getLogger(__name__)

if typing.TYPE_CHECKING:
    from charm import MySQLOperatorCharm


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


class MySQLUninstallError(Error):
    """Exception raised when there's an error installing MySQL."""


class MySQL(MySQLBase):
    """Class to encapsulate all operations related to the MySQL instance and cluster.

    This class handles the configuration of MySQL instances, and also the
    creation and configuration of MySQL InnoDB clusters via Group Replication.
    """

    def __init__(
        self,
        instance_address: str,
        socket_path: str,
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
        charm: "MySQLOperatorCharm",
    ):
        """Initialize the MySQL class.

        Args:
            instance_address: address of the targeted instance
            socket_path: path to the MySQL socket
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
            charm: The charm object
        """
        super().__init__(
            instance_address=instance_address,
            socket_path=socket_path,
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

        self.charm = charm

    @staticmethod
    def install_and_configure_mysql_dependencies() -> None:
        """Install and configure MySQL dependencies.

        Raises:
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
            with pathlib.Path("snap_revisions.json").open("r") as file:
                revision = json.load(file)[platform.machine()]
            logger.debug(f"Installing {CHARMED_MYSQL_SNAP_NAME} revision {revision}")
            charmed_mysql.ensure(snap.SnapState.Present, revision=revision)
            if not charmed_mysql.held:
                # hold the snap in charm determined revision
                charmed_mysql.hold()

            # ensure creation of mysql shell common directory by running 'mysqlsh --help'
            common_path = pathlib.Path(CHARMED_MYSQL_COMMON_DIRECTORY)
            if not common_path.exists():
                logger.debug("Creating charmed-mysql common directory")
                mysqlsh_help_command = ["charmed-mysql.mysqlsh", "--help"]
                subprocess.check_call(mysqlsh_help_command, stderr=subprocess.PIPE)

            # fix ownership necessary for upgrades from 8/stable@r151
            # TODO: remove once snap post-refresh fixes the permission
            if common_path.owner() != MYSQL_SYSTEM_USER:
                logger.debug("Updating charmed-mysql common directory ownership")
                os.system(f"chown -R {MYSQL_SYSTEM_USER} {CHARMED_MYSQL_COMMON_DIRECTORY}")

            subprocess.run(["snap", "alias", "charmed-mysql.mysql", "mysql"], check=True)
            subprocess.run(
                ["snap", "alias", "charmed-mysql.mysqlbinlog", "mysqlbinlog"], check=True
            )

            installed_by_mysql_server_file.touch(exist_ok=True)
        except snap.SnapError:
            logger.exception("Failed to install snaps")
            # reraise SnapError exception so the caller can retry
            raise
        except (subprocess.CalledProcessError, snap.SnapNotFoundError, Exception):
            logger.exception("Failed to install and configure MySQL dependencies")
            # other exceptions are not retried
            raise MySQLInstallError

    @staticmethod
    def uninstall_mysql() -> None:
        """Uninstall MySQL.

        Raises: MySQLUninstallError if there is an error uninstalling MySQL
        """
        for attempt in range(1, 4):
            # make 3 tries to uninstall MySQL
            try:
                logger.debug("Uninstalling MySQL")
                subprocess.run(["snap", "remove", "charmed-mysql"], check=True)
                return
            except subprocess.CalledProcessError:
                # uninstalls fail due to SNAP_DATA_DIR fails to umount
                # try umount it, without check
                subprocess.run(["umount", CHARMED_MYSQL_COMMON_DIRECTORY])
                shutil.rmtree(f"{CHARMED_MYSQL_DATA_DIRECTORY}/etc", ignore_errors=True)
                logger.exception(f"Failed to uninstall MySQL on {attempt=}")
        raise MySQLUninstallError from None

    @override
    def get_available_memory(self) -> int:
        """Retrieves the total memory of the server where mysql is running."""
        try:
            logger.debug("Querying system total memory")
            with open("/proc/meminfo") as meminfo:
                for line in meminfo:
                    if "MemTotal" in line:
                        return int(line.split()[1]) * 1024

            raise MySQLGetAvailableMemoryError
        except OSError:
            logger.error("Failed to query system memory")
            raise MySQLGetAvailableMemoryError

    def write_mysqld_config(self) -> None:
        """Create custom mysql config file.

        Raises: MySQLCreateCustomMySQLDConfigError if there is an error creating the
            custom mysqld config
        """
        logger.debug("Writing mysql configuration file")
        memory_limit = None
        if self.charm.config.profile_limit_memory:
            # Convert from config value in MB to bytes
            memory_limit = self.charm.config.profile_limit_memory * BYTES_1MB
        try:
            content_str, _ = self.render_mysqld_configuration(
                profile=self.charm.config.profile,
                audit_log_enabled=self.charm.config.plugin_audit_enabled,
                audit_log_strategy=self.charm.config.plugin_audit_strategy,
                snap_common=CHARMED_MYSQL_COMMON_DIRECTORY,
                memory_limit=memory_limit,
                binlog_retention_days=self.charm.config.binlog_retention_days,
                experimental_max_connections=self.charm.config.experimental_max_connections,
            )
        except (MySQLGetAvailableMemoryError, MySQLGetAutoTuningParametersError):
            logger.exception("Failed to get available memory or auto tuning parameters")
            raise MySQLCreateCustomMySQLDConfigError

        # create the mysqld config directory if it does not exist
        pathlib.Path(MYSQLD_CONFIG_DIRECTORY).mkdir(mode=0o755, parents=True, exist_ok=True)

        self.write_content_to_file(
            path=MYSQLD_CUSTOM_CONFIG_FILE,
            content=content_str,
        )

    def setup_logrotate_and_cron(self, enabled_log_files: Iterable) -> None:
        """Setup log rotation configuration for text files.

        Args:
            enabled_log_files: a iterable of enabled text logs
        """
        logger.debug("Creating logrotate config file")
        config_path = "/etc/logrotate.d/flush_mysql_logs"
        script_path = f"{self.charm.charm_dir}/logrotation.sh"
        cron_path = "/etc/cron.d/flush_mysql_logs"
        logs_dir = f"{CHARMED_MYSQL_COMMON_DIRECTORY}/var/log/mysql"

        with open("templates/logrotate.j2", "r") as file:
            template = jinja2.Template(file.read())

        logrotate_conf_content = template.render(
            system_user=MYSQL_SYSTEM_USER,
            log_dir=logs_dir,
            charm_directory=self.charm.charm_dir,
            unit_name=self.charm.unit.name,
            enabled_log_files=enabled_log_files,
        )

        self.write_content_to_file(
            config_path, logrotate_conf_content, owner="root", permission=0o644
        )

        with open("templates/run_log_rotation.sh.j2", "r") as file:
            template = jinja2.Template(file.read())

        logrotation_script_content = template.render(
            log_path=f"{CHARMED_MYSQL_COMMON_DIRECTORY}/var/log/mysql",
            enabled_log_files=enabled_log_files,
            logrotate_conf=config_path,
            owner=MYSQL_SYSTEM_USER,
            group=MYSQL_SYSTEM_USER,
        )

        self.write_content_to_file(script_path, logrotation_script_content, permission=0o550)

        cron_content = f"* 1-23 * * * root {script_path}\n1-59 0 * * * root {script_path}\n"
        self.write_content_to_file(cron_path, cron_content, owner="root")

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
                    subprocess.check_output([
                        "sudo",
                        "chown",
                        f"{MYSQL_SYSTEM_USER}:{ROOT_SYSTEM_USER}",
                        _sql_file.name,
                    ])
                except subprocess.CalledProcessError:
                    raise MySQLResetRootPasswordAndStartMySQLDError(
                        "Failed to change permissions for temp SQL file"
                    )

                _custom_config_file.write(f"[mysqld]\ninit_file = {_sql_file.name}")
                _custom_config_file.flush()

                try:
                    subprocess.check_output([
                        "sudo",
                        "chown",
                        f"{MYSQL_SYSTEM_USER}:{ROOT_SYSTEM_USER}",
                        _custom_config_file.name,
                    ])
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
                    # Do not try to connect over port as we may not have configured user/passwords
                    self.wait_until_mysql_connection(check_port=False)
                except MySQLServiceNotRunningError:
                    raise MySQLResetRootPasswordAndStartMySQLDError("mysqld service not running")

    @retry(reraise=True, stop=stop_after_delay(120), wait=wait_fixed(5))
    def wait_until_mysql_connection(self, check_port: bool = True) -> None:
        """Wait until a connection to MySQL has been obtained.

        Retry every 5 seconds for 120 seconds if there is an issue obtaining a connection.
        """
        logger.debug("Waiting for MySQL connection")

        if not os.path.exists(MYSQLD_SOCK_FILE):
            raise MySQLServiceNotRunningError("MySQL socket file not found")

        if check_port and not self.check_mysqlsh_connection():
            raise MySQLServiceNotRunningError("Connection with mysqlsh not possible")

        logger.debug("MySQL connection possible")

    def execute_backup_commands(  # type: ignore
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

    def delete_temp_backup_directory(  # type: ignore
        self, from_directory: str = CHARMED_MYSQL_COMMON_DIRECTORY
    ) -> None:
        """Delete the temp backup directory."""
        super().delete_temp_backup_directory(
            from_directory,
            user=ROOT_SYSTEM_USER,
            group=ROOT_SYSTEM_USER,
        )

    def retrieve_backup_with_xbcloud(  # type: ignore
        self,
        backup_id: str,
        s3_parameters: Dict[str, str],
        temp_restore_directory: str = CHARMED_MYSQL_COMMON_DIRECTORY,
        xbcloud_location: str = CHARMED_MYSQL_XBCLOUD_LOCATION,
        xbstream_location: str = CHARMED_MYSQL_XBSTREAM_LOCATION,
        user=ROOT_SYSTEM_USER,
        group=ROOT_SYSTEM_USER,
    ) -> Tuple[str, str, str]:
        """Retrieve the provided backup with xbcloud."""
        return super().retrieve_backup_with_xbcloud(
            backup_id,
            s3_parameters,
            temp_restore_directory,
            xbcloud_location,
            xbstream_location,
            user,
            group,
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
        except subprocess.CalledProcessError:
            logger.exception("Failed to change data directory permissions before restoring")
            raise MySQLRestoreBackupError

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
        except subprocess.CalledProcessError:
            logger.exception(
                "Failed to change data directory permissions or ownership after restoring"
            )
            raise MySQLRestoreBackupError

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
        env_extra: Dict = {},
        stream_output: Optional[str] = None,
    ) -> Tuple[str, str]:
        """Execute commands on the server where mysql is running.

        Args:
            commands: a list containing the commands to execute
            bash: whether to run the commands with bash
            user: the user with which to execute the commands
            group: the group with which to execute the commands
            env_extra: the environment variables to add to the current process’ environment
            stream_output: whether to stream the output to stdout, stderr or None

        Returns: tuple of (stdout, stderr)

        Raises: MySQLExecError if there was an error executing the commands
        """
        stdout = stderr = ""
        env = os.environ.copy()
        if env_extra:
            env.update(env_extra)
        if bash:
            commands = ["bash", "-c", "set -o pipefail; " + " ".join(commands)]

        process = subprocess.Popen(
            commands,
            user=user,
            group=group,
            env=env,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        if stream_output == "stderr":
            while process.stderr and (line := process.stderr.readline()):
                logger.debug(line.strip())
                stderr += line
        elif stream_output == "stdout":
            while process.stdout and (line := process.stdout.readline()):
                logger.debug(line.strip())
                stdout += line

        return_code = process.wait()
        if return_code != 0:
            message = (
                "Failed command: "
                f"{self.strip_off_passwords(' '.join(commands))};"
                f" {user=}; {group=}"
            )
            logger.error(message)
            raise MySQLExecError from None

        if not stdout and process.stdout:
            stdout = process.stdout.read()
        if not stderr and process.stderr:
            stderr = process.stderr.read()

        return (stdout.strip(), stderr.strip())

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
        except (SnapServiceOperationError, MySQLKillSessionError) as e:
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

    def restart_mysqld(self) -> None:
        """Restarts the mysqld process."""
        self.stop_mysqld()
        self.start_mysqld()

    def flush_host_cache(self) -> None:
        """Flush the MySQL in-memory host cache."""
        if not self.is_mysqld_running():
            logger.warning("mysqld is not running, skipping flush host cache")
            return
        flush_host_cache_command = ("TRUNCATE TABLE performance_schema.host_cache",)

        try:
            logger.debug("Truncating the MySQL host cache")
            self._run_mysqlcli_script(
                flush_host_cache_command,
                user=self.server_config_user,
                password=self.server_config_password,
            )
        except MySQLClientError:
            logger.error("Failed to truncate the MySQL host cache")
            raise MySQLFlushHostCacheError

    def connect_mysql_exporter(self) -> None:
        """Set up mysqld-exporter config options.

        Raises:
            snap.SnapError: if an issue occurs during config setting or restart
        """
        cache = snap.SnapCache()
        mysqld_snap = cache[CHARMED_MYSQL_SNAP_NAME]

        try:
            # Set up exporter credentials
            mysqld_snap.set({
                "exporter.user": self.monitoring_user,
                "exporter.password": self.monitoring_password,
            })
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
        self.stop_mysql_exporter()
        self.connect_mysql_exporter()

    def _run_mysqlsh_script(
        self,
        script: str,
        user: str,
        host: str,
        password: str,
        timeout=None,
        exception_as_warning: bool = False,
    ) -> str:
        """Execute a MySQL shell script.

        Raises:
            MySQLClientError if the script gets a non-zero return code.
            TimeoutError if the script times out.

        Args:
            script: Mysqlsh script string
            user: User to invoke the mysqlsh script with
            host: Host to run the script on
            password: Password to invoke the mysqlsh script
            timeout: (optional) Timeout for the script
            exception_as_warning: (optional) whether the exception should be treated as warning

        Returns:
            String representing the output of the mysqlsh command
        """
        # prepend every shell command with
        # - set wizard to false. cannot be set on cmd line option as it conflicts with --passwords-from-stdin
        # - a separator to ease output parsing, as password prompt get printed to stdout
        prepend_cmd = "shell.options.set('useWizards', False)\nprint('###')\n"
        script = prepend_cmd + script  # prepend output separator to script

        command = [
            CHARMED_MYSQLSH,
            "--passwords-from-stdin",
            f"--uri={user}@{host}",
            "--python",
            "-c",
            script,
        ]

        try:
            output = subprocess.check_output(
                command,
                stderr=subprocess.PIPE,
                timeout=timeout,
                input=password,
                text=True,
            )
            # split output to clean mysqlsh garbage
            return output.split("###")[1].strip()
        except subprocess.CalledProcessError as e:
            if exception_as_warning:
                logger.warning("Failed to execute mysql-shell command")
            else:
                self.strip_off_passwords_from_exception(e)
                logger.exception("Failed to execute mysql-shell command")
            raise MySQLClientError
        except subprocess.TimeoutExpired as e:
            if exception_as_warning:
                logger.warning("MySQL shell command timed out")
            else:
                self.strip_off_passwords_from_exception(e)
                logger.exception("MySQL shell command timed out")
            raise TimeoutError

    def _run_mysqlcli_script(
        self,
        script: Union[Tuple[Any, ...], List[Any]],
        user: str = "root",
        password: Optional[str] = None,
        timeout: Optional[int] = None,
        exception_as_warning: bool = False,
    ) -> list:
        """Execute a MySQL script.

        Execute SQL script as instance root user.

        Raises:
            MySQLClientError if the script gets a non-zero return code.
            TimeoutError if the script times out.

        Args:
            script: raw SQL script string or string Iterable
            user: (optional) user to invoke the mysql cli script with (default is "root")
            password: (optional) password to invoke the mysql cli script with
            timeout: (optional) time before the query should timeout
            exception_as_warning: (optional) whether the exception should be treated as warning
        """
        command = [
            CHARMED_MYSQL,
            "-u",
            user,
            "-N",
            "-B",
            f"--socket={MYSQLD_SOCK_FILE}",
            "-e",
            ";".join(script),
        ]

        try:
            if password:
                command.insert(3, "-p")
                # need to contain SQL in quotes for pexpect
                command[-1] = f'"{command[-1]}"'
                process = pexpect.spawnu(" ".join(command), timeout=timeout)
                process.expect("Enter password:")
                process.sendline(password)

                stdout = process.readlines()

                if len(stdout) > 1 and "ERROR" in stdout[1]:
                    # some errors will not bubble up from spawned process
                    # but are reported in the stdout
                    logger.error(stdout[1].strip())
                    raise MySQLClientError

                # index 0 contains empty \r\n
                return [line.strip().split() for line in stdout[1:]] if stdout else []
            else:
                stdout = subprocess.check_output(command, timeout=timeout, text=True)
                return [line.split() for line in stdout.strip().split("\n")] if stdout else []

        except (pexpect.TIMEOUT, subprocess.TimeoutExpired) as e:
            if exception_as_warning:
                logger.warning("MySQL cli command timed out")
            else:
                self.strip_off_passwords_from_exception(e)
                logger.exception("MySQL cli command timed out")
            raise TimeoutError
        except (pexpect.exceptions.ExceptionPexpect, subprocess.CalledProcessError) as e:
            if exception_as_warning:
                logger.warning("Failed to execute MySQL cli command")
            else:
                self.strip_off_passwords_from_exception(e)
                logger.exception("Failed to execute MySQL cli command")
            raise MySQLClientError

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

    def _file_exists(self, path: str) -> bool:
        """Check if file exists."""
        return os.path.exists(path)

    def reconcile_binlogs_collection(self, force_restart: bool = False) -> bool:
        """Start or stop binlogs collecting service.

        Based on the "binlogs-collecting" app peer data value and unit leadership.

        Args:
            force_restart: whether to restart service even if it's already running.

        Returns: whether the operation was successful.
        """
        cache = snap.SnapCache()
        selected_snap = cache[CHARMED_MYSQL_SNAP_NAME]
        if not selected_snap.present:
            raise SnapServiceOperationError(f"Snap {CHARMED_MYSQL_SNAP_NAME} not installed")

        is_enabled = selected_snap.services[CHARMED_MYSQL_BINLOGS_COLLECTOR_SERVICE]["enabled"]
        is_active = selected_snap.services[CHARMED_MYSQL_BINLOGS_COLLECTOR_SERVICE]["active"]
        supposed_to_run = (
            self.charm.unit.is_leader() and "binlogs-collecting" in self.charm.app_peer_data
        )

        if supposed_to_run and is_enabled and not is_active:
            logger.error("Binlogs collector is enabled but not running")
            if force_restart:
                logger.error("Binlogs collector will be restarted due to force_restart option")
            else:
                logger.error("Restarting binlogs collector to reanimate unhealthy service")
                selected_snap.restart([CHARMED_MYSQL_BINLOGS_COLLECTOR_SERVICE])

        if is_enabled and (force_restart or not supposed_to_run):
            logger.debug("Disabling binlogs collector")
            selected_snap.stop([CHARMED_MYSQL_BINLOGS_COLLECTOR_SERVICE], disable=True)

        if supposed_to_run and (force_restart or not is_enabled):
            logger.debug("Enabling binlogs collector")
            if not self.charm.backups.update_binlogs_collector_config():
                return False
            selected_snap.start([CHARMED_MYSQL_BINLOGS_COLLECTOR_SERVICE], enable=True)

        return True

    def delete_binlogs_collector_config(self) -> None:
        """Delete binlogs collector config file."""
        logger.info("Deleting binlogs collector config")
        if os.path.exists(MYSQL_BINLOGS_COLLECTOR_CONFIG_FILE):
            os.remove(MYSQL_BINLOGS_COLLECTOR_CONFIG_FILE)

    def get_cluster_members(self) -> list[str]:
        """Get cluster members in MySQL MEMBER_HOST format.

        Returns: list of cluster members in MySQL MEMBER_HOST format.
        """
        return [host.names[1] for host in self.charm.hostname_resolution._get_host_details()]

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

    @staticmethod
    def fetch_error_log() -> Optional[str]:
        """Fetch the mysqld error log."""
        if os.path.exists(f"{CHARMED_MYSQL_COMMON_DIRECTORY}/var/log/mysql/error.log"):
            # can be empty if just rotated
            with open(f"{CHARMED_MYSQL_COMMON_DIRECTORY}/var/log/mysql/error.log", "r") as fd:
                return fd.read()

    @staticmethod
    def reset_data_dir() -> None:
        """Reset the data directory."""
        logger.warning(f"Resetting data directory: {MYSQL_DATA_DIR}")

        # Remove the data directory
        shutil.rmtree(MYSQL_DATA_DIR, ignore_errors=False)

        # Recreate the data directory
        os.makedirs(MYSQL_DATA_DIR)

        # Change ownership of the data directory
        shutil.chown(MYSQL_DATA_DIR, user=MYSQL_SYSTEM_USER, group="root")


def is_volume_mounted() -> bool:
    """Returns if data directory is attached."""
    try:
        for attempt in Retrying(stop=stop_after_attempt(10), wait=wait_fixed(12)):
            with attempt:
                subprocess.check_call(["mountpoint", "-q", CHARMED_MYSQL_COMMON_DIRECTORY])
    except RetryError:
        return False
    return True


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
