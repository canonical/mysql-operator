#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""MySQL opinionated context manager."""

import signal
from typing import Optional

import mysql.connector as connector


def timeout_handler(signum, frame):
    """Handle the timeout signal."""
    del signum, frame
    raise TimeoutError("Query timed out")


class MySQLConnector:
    """Context manager for mysql connector."""

    def __init__(self, config: dict, commit: bool = True, query_timeout: Optional[int] = None):
        """Initialize the context manager.

        Args:
            config: Configuration dict for the mysql connector, like:
                config = {
                    "user": user,
                    "password": remote_data["password"],
                    "host": host,
                    "unix_socket": socket,
                    "database": database,
                    "raise_on_warnings": False,
                }
            commit: Commit the transaction after the context is exited.
            query_timeout: Timeout for the query in seconds.
        """
        self.config = config
        self.commit = commit
        self.query_timeout = query_timeout

    def __enter__(self):
        """Create the connection and return a cursor."""
        self.connection = connector.connect(**self.config)
        self.cursor = self.connection.cursor()
        if self.query_timeout:
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(self.query_timeout)
        return self.cursor

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Handle transaction and connection close."""
        del exc_val, exc_tb
        if self.commit and exc_type is None:
            self.connection.commit()
        self.cursor.close()
        self.connection.close()
        if self.query_timeout:
            signal.alarm(0)
