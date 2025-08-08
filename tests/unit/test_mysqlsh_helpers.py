# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for MySQL class."""

import os
import subprocess
import unittest
from unittest.mock import MagicMock, call, mock_open, patch

from charms.mysql.v0.mysql import (
    MySQLClientError,
    MySQLExecError,
    MySQLGetAutoTuningParametersError,
    MySQLGetAvailableMemoryError,
    MySQLStartMySQLDError,
    MySQLStopMySQLDError,
)

from constants import (
    CHARMED_MYSQL_SNAP_NAME,
    CHARMED_MYSQLD_SERVICE,
    MYSQLD_CONFIG_DIRECTORY,
    MYSQLD_CUSTOM_CONFIG_FILE,
    MYSQLD_SOCK_FILE,
)
from mysql_vm_helpers import (
    MySQL,
    MySQLCreateCustomMySQLDConfigError,
    MySQLResetRootPasswordAndStartMySQLDError,
    MySQLServiceNotRunningError,
    SnapServiceOperationError,
    snap_service_operation,
)


class StubConfig:
    def __init__(self):
        self.plugin_audit_enabled = True
        self.profile = "production"
        self.profile_limit_memory = None
        self.experimental_max_connections = None
        self.plugin_audit_strategy = "async"
        self.binlog_retention_days = 7
        self.logs_audit_policy = "logins"


class StubCharm:
    def __init__(self):
        self.config = StubConfig()


class TestMySQL(unittest.TestCase):
    def setUp(self):
        self.mysql = MySQL(
            "127.0.0.1",
            MYSQLD_SOCK_FILE,
            "test_cluster",
            "test_cluster_set",
            "password",
            "serverconfig",
            "serverconfigpassword",
            "clusteradmin",
            "clusteradminpassword",
            "monitoring",
            "monitoringpassword",
            "backups",
            "backupspassword",
            StubCharm(),  # type: ignore
        )

    @patch("subprocess.check_output")
    def test_run_mysqlsh_script(self, _check_output):
        """Test a successful execution of run_mysqlsh_script."""
        _check_output.return_value = "###stdout"

        self.mysql._run_mysqlsh_script(
            "script",
            user="serverconfig",
            password="serverconfigpassword",
            host="127.0.0.1",
        )

        _check_output.assert_called_once()

    @patch("subprocess.check_output")
    def test_run_mysqlsh_script_exception(self, _check_output):
        """Test a failed execution of run_mysqlsh_script."""
        _check_output.side_effect = subprocess.CalledProcessError(cmd="", returncode=1)

        with self.assertRaises(MySQLClientError):
            self.mysql._run_mysqlsh_script(
                "script",
                user="serverconfig",
                password="serverconfigpassword",
                host="127.0.0.1",
            )

    @patch("subprocess.check_output")
    @patch("pexpect.spawnu")
    def test_run_mysqlcli_script(self, _spawnu, _check_output):
        """Test a successful execution of run_mysqlcli_script."""
        mock_process = MagicMock()
        _spawnu.return_value = mock_process
        mock_process.readlines.return_value = ["\r\n", "result1\r\n", "result2\r\n"]

        # Test with password
        result = self.mysql._run_mysqlcli_script(
            ("script",),
            user="root",
            password="password",
            timeout=10,
        )

        _spawnu.assert_called_once_with(
            'charmed-mysql.mysql -u root -p -N -B --socket=/var/snap/charmed-mysql/common/var/run/mysqld/mysqld.sock -e "script"',
            timeout=10,
        )
        mock_process.expect.assert_called_once_with("Enter password:")
        mock_process.sendline.assert_called_once_with("password")
        self.assertEqual(result, [["result1"], ["result2"]])

        # Test without password
        _check_output.return_value = "result1\nresult2"
        result = self.mysql._run_mysqlcli_script(
            ("script",),
            user="root",
            timeout=10,
        )

        _check_output.assert_called_once_with(
            [
                "charmed-mysql.mysql",
                "-u",
                "root",
                "-N",
                "-B",
                "--socket=/var/snap/charmed-mysql/common/var/run/mysqld/mysqld.sock",
                "-e",
                "script",
            ],
            timeout=10,
            text=True,
        )
        self.assertEqual(result, [["result1"], ["result2"]])

    @patch("subprocess.check_output")
    def test_run_mysqlcli_script_exception(self, _check_output):
        """Test a failed execution of run_mysqlsh_script."""
        _check_output.side_effect = subprocess.CalledProcessError(
            cmd="", returncode=-1, stderr="Test error message"
        )

        sql_script = ("CREATE USER 'test_user'@'localhost' IDENTIFIED BY 'password';",)
        with self.assertRaises(MySQLClientError):
            self.mysql._run_mysqlcli_script(sql_script)

    @patch("mysql_vm_helpers.MySQL.wait_until_mysql_connection.retry.stop", return_value=1)
    @patch("os.path.exists", return_value=False)
    def test_wait_until_mysql_connection(self, _exists, _stop):
        """Test a failed execution of wait_until_mysql_connection."""
        with self.assertRaises(MySQLServiceNotRunningError):
            self.mysql.wait_until_mysql_connection()

    @patch("tempfile.NamedTemporaryFile")
    @patch("subprocess.check_output")
    @patch("mysql_vm_helpers.snap_service_operation")
    @patch("mysql_vm_helpers.MySQL.wait_until_mysql_connection")
    def test_reset_root_password_and_start_mysqld(
        self,
        _wait_until_mysql_connection,
        _snap_service_operation,
        _check_output,
        _named_temporary_file,
    ):
        """Test a successful execution of reset_root_password_and_start_mysqld."""
        self.mysql.reset_root_password_and_start_mysqld()

        self.assertEqual(2, _named_temporary_file.call_count)
        self.assertEqual(2, _check_output.call_count)
        self.assertEqual(1, _snap_service_operation.call_count)
        self.assertEqual(1, _wait_until_mysql_connection.call_count)

    @patch("tempfile.NamedTemporaryFile")
    @patch("subprocess.check_output")
    @patch("mysql_vm_helpers.snap_service_operation")
    @patch("mysql_vm_helpers.MySQL.wait_until_mysql_connection")
    def test_reset_root_password_and_start_mysqld_exception(
        self,
        _wait_until_mysql_connection,
        _snap_service_operation,
        _check_output,
        _named_temporary_file,
    ):
        """Test a failed execution of reset_root_password_and_start_mysqld."""
        _check_output.side_effect = subprocess.CalledProcessError(cmd="", returncode=-1)

        with self.assertRaises(MySQLResetRootPasswordAndStartMySQLDError):
            self.mysql.reset_root_password_and_start_mysqld()

        self.assertEqual(2, _named_temporary_file.call_count)
        self.assertEqual(1, _check_output.call_count)
        self.assertEqual(0, _snap_service_operation.call_count)
        self.assertEqual(0, _wait_until_mysql_connection.call_count)

        _named_temporary_file.reset_mock()
        _check_output.reset_mock()
        _snap_service_operation.reset_mock()
        _wait_until_mysql_connection.reset_mock()

        _check_output.side_effect = None
        _snap_service_operation.side_effect = SnapServiceOperationError()

        with self.assertRaises(MySQLResetRootPasswordAndStartMySQLDError):
            self.mysql.reset_root_password_and_start_mysqld()

        self.assertEqual(2, _named_temporary_file.call_count)
        self.assertEqual(2, _check_output.call_count)
        self.assertEqual(1, _snap_service_operation.call_count)
        self.assertEqual(0, _wait_until_mysql_connection.call_count)

        _named_temporary_file.reset_mock()
        _check_output.reset_mock()
        _snap_service_operation.reset_mock()
        _wait_until_mysql_connection.reset_mock()

        _check_output.side_effect = None
        _snap_service_operation.side_effect = None
        _wait_until_mysql_connection.side_effect = MySQLServiceNotRunningError()

        with self.assertRaises(MySQLResetRootPasswordAndStartMySQLDError):
            self.mysql.reset_root_password_and_start_mysqld()

        self.assertEqual(2, _named_temporary_file.call_count)
        self.assertEqual(2, _check_output.call_count)
        self.assertEqual(1, _snap_service_operation.call_count)
        self.assertEqual(1, _wait_until_mysql_connection.call_count)

    @patch("mysql_vm_helpers.snap.SnapCache")
    def test_snap_service_operation(self, _snap_cache):
        """Test a successful execution of function snap_service_operation."""
        _charmed_mysql_mock = MagicMock()
        _cache = {CHARMED_MYSQL_SNAP_NAME: _charmed_mysql_mock}
        _snap_cache.return_value.__getitem__.side_effect = _cache.__getitem__

        # Test start operation
        snap_service_operation(CHARMED_MYSQL_SNAP_NAME, CHARMED_MYSQLD_SERVICE, "start")

        _snap_cache.assert_called_once()
        _charmed_mysql_mock.start.assert_called_once()
        _charmed_mysql_mock.restart.assert_not_called()
        _charmed_mysql_mock.stop.assert_not_called()

        # Test restart operation
        _snap_cache.reset_mock()
        _charmed_mysql_mock.reset_mock()

        snap_service_operation(CHARMED_MYSQL_SNAP_NAME, CHARMED_MYSQLD_SERVICE, "restart")

        _snap_cache.assert_called_once()
        _charmed_mysql_mock.start.assert_not_called()
        _charmed_mysql_mock.restart.assert_called_once()
        _charmed_mysql_mock.stop.assert_not_called()

        # Test stop operation
        _snap_cache.reset_mock()
        _charmed_mysql_mock.reset_mock()

        snap_service_operation(CHARMED_MYSQL_SNAP_NAME, CHARMED_MYSQLD_SERVICE, "stop")

        _snap_cache.assert_called_once()
        _charmed_mysql_mock.start.assert_not_called()
        _charmed_mysql_mock.restart.assert_not_called()
        _charmed_mysql_mock.stop.assert_called_once()

    @patch("mysql_vm_helpers.snap.SnapCache")
    def test_snap_service_operation_exception(self, _snap_cache):
        """Test failure in execution of function snap_service_operation."""
        _charmed_mysql_mock = MagicMock()
        _cache = {CHARMED_MYSQL_SNAP_NAME: _charmed_mysql_mock}
        _snap_cache.return_value.__getitem__.side_effect = _cache.__getitem__

        with self.assertRaises(SnapServiceOperationError):
            snap_service_operation(CHARMED_MYSQL_SNAP_NAME, CHARMED_MYSQLD_SERVICE, "nonsense")

        _snap_cache.assert_not_called()

    @patch("shutil.chown")
    @patch("os.chmod")
    @patch("mysql_vm_helpers.MySQL.get_available_memory", return_value=16475447296)
    @patch(
        "mysql_vm_helpers.MySQL.get_innodb_buffer_pool_parameters",
        return_value=(1234, 5678, None),
    )
    @patch("mysql_vm_helpers.MySQL.get_max_connections", return_value=111)
    @patch("pathlib.Path")
    @patch("builtins.open")
    def test_write_mysqld_config(
        self,
        _open,
        _path,
        _get_innodb_buffer_pool_parameters,
        _get_max_connections,
        _get_available_memory,
        _chmod,
        _chown,
    ):
        """Test successful execution of create_custom_mysqld_config."""
        self.maxDiff = None
        _path_mock = MagicMock()
        _path.return_value = _path_mock

        _open_mock = unittest.mock.mock_open()
        _open.side_effect = _open_mock

        self.mysql.write_mysqld_config()

        config = "\n".join((
            "[mysqld]",
            "bind-address = 0.0.0.0",
            "mysqlx-bind-address = 0.0.0.0",
            "admin_address = 127.0.0.1",
            "report_host = 127.0.0.1",
            "max_connections = 111",
            "innodb_buffer_pool_size = 1234",
            "log_error_services = log_filter_internal;log_sink_internal",
            "log_error = /var/snap/charmed-mysql/common/var/log/mysql/error.log",
            "general_log = OFF",
            "general_log_file = /var/snap/charmed-mysql/common/var/log/mysql/general.log",
            "loose-group_replication_paxos_single_leader = ON",
            "slow_query_log_file = /var/snap/charmed-mysql/common/var/log/mysql/slow.log",
            "binlog_expire_logs_seconds = 604800",
            "loose-audit_log_policy = LOGINS",
            "loose-audit_log_file = /var/snap/charmed-mysql/common/var/log/mysql/audit.log",
            "gtid_mode = ON",
            "enforce_gtid_consistency = ON",
            "loose-audit_log_format = JSON",
            "loose-audit_log_strategy = ASYNCHRONOUS",
            "innodb_buffer_pool_chunk_size = 5678",
            "\n",
        ))

        _get_max_connections.assert_called_once()
        _get_innodb_buffer_pool_parameters.assert_called_once()
        _path_mock.mkdir.assert_called_once_with(mode=0o755, parents=True, exist_ok=True)
        _open.assert_called_once_with(MYSQLD_CUSTOM_CONFIG_FILE, "w", encoding="utf-8")
        _get_available_memory.assert_called_once()

        assert call().write(config) in _open_mock.mock_calls

        # Test `testing` profile
        self.mysql.charm.config.profile = "testing"
        _open_mock.reset_mock()
        self.mysql.write_mysqld_config()

        config = "\n".join((
            "[mysqld]",
            "bind-address = 0.0.0.0",
            "mysqlx-bind-address = 0.0.0.0",
            "admin_address = 127.0.0.1",
            "report_host = 127.0.0.1",
            "max_connections = 100",
            "innodb_buffer_pool_size = 20971520",
            "log_error_services = log_filter_internal;log_sink_internal",
            "log_error = /var/snap/charmed-mysql/common/var/log/mysql/error.log",
            "general_log = OFF",
            "general_log_file = /var/snap/charmed-mysql/common/var/log/mysql/general.log",
            "loose-group_replication_paxos_single_leader = ON",
            "slow_query_log_file = /var/snap/charmed-mysql/common/var/log/mysql/slow.log",
            "binlog_expire_logs_seconds = 604800",
            "loose-audit_log_policy = LOGINS",
            "loose-audit_log_file = /var/snap/charmed-mysql/common/var/log/mysql/audit.log",
            "gtid_mode = ON",
            "enforce_gtid_consistency = ON",
            "loose-audit_log_format = JSON",
            "loose-audit_log_strategy = ASYNCHRONOUS",
            "innodb_buffer_pool_chunk_size = 1048576",
            "performance-schema-instrument = 'memory/%=OFF'",
            "loose-group_replication_message_cache_size = 134217728",
            "\n",
        ))

        self.assertTrue(
            call(
                f"{MYSQLD_CONFIG_DIRECTORY}/z-custom-mysqld.cnf",
                "w",
                encoding="utf-8",
            )
            in _open_mock.mock_calls
        )

    @patch(
        "mysql_vm_helpers.MySQL.get_innodb_buffer_pool_parameters",
        return_value=(1234, 5678),
    )
    @patch("pathlib.Path")
    @patch("builtins.open")
    def test_create_custom_mysqld_config_exception(
        self, _open, _path, _get_innodb_buffer_pool_parameters
    ):
        """Test failure in execution of create_custom_mysqld_config."""
        _get_innodb_buffer_pool_parameters.side_effect = MySQLGetAutoTuningParametersError

        _path_mock = MagicMock()
        _path.return_value = _path_mock

        _open_mock = unittest.mock.mock_open()
        _open.side_effect = _open_mock

        self.mysql.charm.config = MagicMock()  # type: ignore

        with self.assertRaises(MySQLCreateCustomMySQLDConfigError):
            self.mysql.write_mysqld_config()

    @patch("subprocess.Popen")
    def test_execute_commands(self, _popen):
        """Test a successful execution of _execute_commands."""
        process = MagicMock()
        _popen.return_value = process
        process.wait.return_value = 0
        self.mysql._execute_commands(
            ["ls", "-la", "|", "wc", "-l"],
            bash=True,
            user="test_user",
            group="test_group",
            env_extra={"envA": "valueA"},
        )
        env = os.environ.copy()
        env.update({"envA": "valueA"})
        _popen.assert_called_once_with(
            ["bash", "-c", "set -o pipefail; ls -la | wc -l"],
            user="test_user",
            group="test_group",
            env=env,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    @patch("subprocess.Popen")
    def test_execute_commands_exception(self, _popen):
        """Test a failure in execution of _execute_commands."""
        process = MagicMock()
        _popen.return_value = process
        process.wait.return_value = -1

        with self.assertRaises(MySQLExecError):
            self.mysql._execute_commands(
                ["ls", "-la"],
                bash=True,
                user="test_user",
                group="test_group",
                env_extra={"envA": "valueA"},
            )

    @patch("os.path.exists", return_value=True)
    def test_is_mysqld_running(self, _path_exists):
        """Test execution of is_mysqld_running()."""
        self.assertTrue(self.mysql.is_mysqld_running())

        _path_exists.return_value = False
        self.assertFalse(self.mysql.is_mysqld_running())

    @patch("mysql_vm_helpers.snap_service_operation")
    def test_stop_mysqld(self, _snap_service_operation):
        """Test execution of stop_mysqld()."""
        self.mysql.stop_mysqld()

        _snap_service_operation.assert_called_once_with(
            CHARMED_MYSQL_SNAP_NAME, CHARMED_MYSQLD_SERVICE, "stop"
        )

    @patch("mysql_vm_helpers.MySQL.kill_client_sessions")
    @patch("mysql_vm_helpers.snap_service_operation")
    def test_stop_mysqld_failure(self, _snap_service_operation, _):
        """Test failure of stop_mysqld()."""
        _snap_service_operation.side_effect = SnapServiceOperationError("failure")

        with self.assertRaises(MySQLStopMySQLDError):
            self.mysql.stop_mysqld()

    @patch("mysql_vm_helpers.snap_service_operation")
    @patch("mysql_vm_helpers.MySQL.wait_until_mysql_connection")
    def test_start_mysqld(
        self,
        _wait_until_mysql_connection,
        _snap_service_operation,
    ):
        """Test execution of start_mysqld()."""
        self.mysql.start_mysqld()

        _snap_service_operation.assert_called_once_with(
            CHARMED_MYSQL_SNAP_NAME, CHARMED_MYSQLD_SERVICE, "start"
        )
        _wait_until_mysql_connection.assert_called_once()

    @patch("mysql_vm_helpers.snap_service_operation")
    @patch("mysql_vm_helpers.MySQL.wait_until_mysql_connection")
    def test_start_mysqld_failure(
        self,
        _wait_until_mysql_connection,
        _snap_service_operation,
    ):
        """Test failure of start_mysqld()."""
        _snap_service_operation.side_effect = SnapServiceOperationError("failure")

        with self.assertRaises(MySQLStartMySQLDError):
            self.mysql.start_mysqld()

        _snap_service_operation.reset_mock()
        _wait_until_mysql_connection.side_effect = MySQLServiceNotRunningError

        with self.assertRaises(MySQLStartMySQLDError):
            self.mysql.start_mysqld()

    @patch("os.system")
    @patch("pathlib.Path.touch")
    @patch("pathlib.Path.owner")
    @patch("pathlib.Path.exists")
    @patch("subprocess.check_call")
    @patch("subprocess.run")
    @patch("os.path.exists", return_value=True)
    @patch("mysql_vm_helpers.snap.SnapCache")
    def test_install_snap(
        self,
        _cache,
        _path_exists,
        _run,
        _check_call,
        _pathlib_exists,
        _pathlib_owner,
        _touch,
        _system,
    ):
        """Test execution of install_snap()."""
        _mysql_snap = MagicMock()
        _cache.return_value = {CHARMED_MYSQL_SNAP_NAME: _mysql_snap}

        _mysql_snap.present = False
        _path_exists.return_value = False
        _pathlib_exists.return_value = False
        _pathlib_owner.return_value = None

        self.mysql.install_and_configure_mysql_dependencies()

        _check_call.assert_called_once_with(
            ["/snap/bin/charmed-mysql.mysqlsh", "--help"], stderr=-1
        )

        assert _mysql_snap.alias.call_count == 7
        _mysql_snap.alias.assert_any_call("mysql")
        _mysql_snap.alias.assert_any_call("mysqlrouter")
        _mysql_snap.alias.assert_any_call("mysqlsh")
        _mysql_snap.alias.assert_any_call("xbcloud")
        _mysql_snap.alias.assert_any_call("xbstream")
        _mysql_snap.alias.assert_any_call("xtrabackup")
        _mysql_snap.alias.assert_any_call("mysqlbinlog")

    def test_get_available_memory(self):
        meminfo = (
            "MemTotal:       16089488 kB"
            "MemFree:          799284 kB"
            "MemAvailable:    3926924 kB"
            "Buffers:          187232 kB"
            "Cached:          4445936 kB"
            "SwapCached:       156012 kB"
            "Active:         11890336 kB"
        )

        with patch("builtins.open", mock_open(read_data=meminfo)):
            self.assertEqual(self.mysql.get_available_memory(), 16475635712)

        with (
            patch("builtins.open", mock_open(read_data="")),
            self.assertRaises(MySQLGetAvailableMemoryError),
        ):
            self.mysql.get_available_memory()

    @patch("shutil.rmtree")
    @patch("os.makedirs")
    @patch("shutil.chown")
    def test_reset_data_dir(self, _chown, _makedirs, _rmtree):
        self.mysql.reset_data_dir()
        _chown.assert_called_once()
        _makedirs.assert_called_once()
        _rmtree.assert_called_once()
