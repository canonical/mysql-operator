# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for MySQLConnector class."""

import signal
import unittest
from unittest.mock import MagicMock, patch

from connector import MySQLConnector, timeout_handler


class TestMySQLConnector(unittest.TestCase):
    @patch("mysql.connector.connect")
    def test_connector_no_timeout(self, mock_connect):
        """Test context manager without query timeout."""
        mock_connection = MagicMock()
        mock_connect.return_value = mock_connection
        config = {"user": "test_user", "password": "test_password"}

        with MySQLConnector(config, commit=True) as cursor:
            cursor.execute("SELECT 1")

        mock_connect.assert_called_once_with(**config)
        mock_connection.cursor.assert_called_once()
        mock_connection.commit.assert_called_once()
        mock_connection.close.assert_called_once()

    @patch("mysql.connector.connect")
    @patch("signal.signal")
    @patch("signal.alarm")
    def test_connector_with_timeout(self, mock_alarm, mock_signal, mock_connect):
        """Test context manager with query timeout."""
        mock_connection = MagicMock()
        mock_connect.return_value = mock_connection
        config = {"user": "test_user"}
        timeout = 5

        with MySQLConnector(config, query_timeout=timeout) as _:
            pass

        mock_signal.assert_called_once_with(signal.SIGALRM, timeout_handler)
        mock_alarm.assert_any_call(timeout)
        mock_alarm.assert_any_call(0)

    @patch("mysql.connector.connect")
    def test_connector_with_exception(self, mock_connect):
        """Test context manager with exception to ensure no commit."""
        mock_connection = MagicMock()
        mock_connect.return_value = mock_connection
        config = {"user": "test_user"}

        try:
            with MySQLConnector(config, commit=True) as cursor:
                cursor.execute("RAISE EXCEPTION")
                raise ValueError("Simulated error")
        except ValueError:
            pass

        mock_connection.commit.assert_not_called()
        mock_connection.close.assert_called_once()
