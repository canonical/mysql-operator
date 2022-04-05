# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import subprocess
import unittest
from unittest.mock import patch

from mysqlsh_helpers import MySQL, MySQLCreateUserError


class TestMySQLHelpers(unittest.TestCase):
    def setUp(self):
        pass

    # def test_mysqlsh_bin(self):

    @patch("mysqlsh_helpers.MySQL.run_mysqlsh_script")
    def test_configure_mysql_users(self, _run_mysqlsh_script):
        """Test failed to configuring the MySQL users."""
        _run_mysqlsh_script.return_value = b""
        _expected_script = "\n".join(
            (
                'shell.connect("root:test@localhost")',
                "dba.session.run_sql(\"CREATE USER 'test'@'%' IDENTIFIED BY 'test' ;\")",
                "dba.session.run_sql(\"GRANT ALL ON *.* TO 'test'@'%' WITH GRANT OPTION ;\")",
                'dba.session.run_sql("REVOKE SYSTEM_USER ON *.* FROM root ;")',
            )
        )

        _m = MySQL("test", "test", "test")

        self.assertEqual(_m.configure_mysql_users(), "")
        _run_mysqlsh_script.assert_called_once_with(_expected_script)

    @patch("mysqlsh_helpers.MySQL.run_mysqlsh_script")
    def test_configure_mysql_users_fail(self, _run_mysqlsh_script):
        """Test failed to configuring the MySQL users."""
        _run_mysqlsh_script.side_effect = subprocess.CalledProcessError(
            cmd="mysqlsh", returncode=127
        )

        _m = MySQL("test", "test", "test")
        with self.assertRaises(MySQLCreateUserError):
            _m.configure_mysql_users()
