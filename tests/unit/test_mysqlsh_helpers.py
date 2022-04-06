# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import subprocess
import unittest
from unittest.mock import patch

from mysqlsh_helpers import MySQL, MySQLConfigureMySQLUsersError


class TestMySQL(unittest.TestCase):
    @patch("mysqlsh_helpers.MySQL._run_mysqlcli_script")
    def test_configure_mysql_users(self, _run_mysqlcli_script):
        """Test failed to configuring the MySQL users."""
        _run_mysqlcli_script.return_value = b""
        _expected_script = " ".join(
            (
                "SET @@SESSION.SQL_LOG_BIN=0;",
                "CREATE USER 'cadmin'@'10.1.1.1' IDENTIFIED BY 'test';",
                "GRANT ALL ON *.* TO 'cadmin'@'10.1.1.1' WITH GRANT OPTION;",
                "CREATE USER 'root'@'%' IDENTIFIED BY 'test';",
                "GRANT ALL ON *.* TO 'root'@'%' WITH GRANT OPTION;",
                "UPDATE mysql.user SET authentication_string=null WHERE User='root' and Host='localhost';",
                "ALTER USER 'root'@'localhost' IDENTIFIED WITH mysql_native_password BY 'test';",
                "REVOKE SYSTEM_USER ON *.* FROM root@'%';",
                "REVOKE SYSTEM_USER ON *.* FROM root@localhost;",
                "FLUSH PRIVILEGES;",
            )
        )

        _m = MySQL("test", "cadmin", "test", "10.1.1.1")

        _m.configure_mysql_users()
        _run_mysqlcli_script.assert_called_once_with(_expected_script)

    @patch("mysqlsh_helpers.MySQL._run_mysqlcli_script")
    def test_configure_mysql_users_fail(self, _run_mysqlcli_script):
        """Test failed to configuring the MySQL users."""
        _run_mysqlcli_script.side_effect = subprocess.CalledProcessError(
            cmd="mysqlsh", returncode=127
        )

        _m = MySQL("test", "test", "test", "10.1.1.1")
        with self.assertRaises(MySQLConfigureMySQLUsersError):
            _m.configure_mysql_users()

    @patch("os.path.exists")
    def test_mysqlsh_bin(self, _exists):
        """Test the mysqlsh_bin property."""
        _exists.return_value = True
        _m = MySQL("test", "test", "test", "10.0.1.1")

        self.assertEqual(_m.mysqlsh_bin, "/usr/bin/mysqlsh")

        _exists.return_value = False
        self.assertEqual(_m.mysqlsh_bin, "/snap/bin/mysql-shell")

    @patch("os.path.exists")
    def test_mysqlsh_common_dir(self, _exists):
        """Test the mysqlsh_common_dir property."""
        _exists.return_value = True
        _m = MySQL("test", "test", "test", "11.1.1.1")
        self.assertEqual(_m.mysqlsh_common_dir, "/root/snap/mysql-shell/common")
        _exists.return_value = False
        self.assertEqual(_m.mysqlsh_common_dir, "/tmp")
