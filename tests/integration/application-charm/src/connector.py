#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.


import mysql.connector


class MysqlConnector:
    """Context manager for mysql connector."""

    def __init__(self, config: dict, commit=True):
        self.config = config
        self.commit = commit

    def __enter__(self):
        self.connection = mysql.connector.connect(**self.config)
        self.cursor = self.connection.cursor()
        return self.cursor

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.commit:
            self.connection.commit()
        self.cursor.close()
        self.connection.close()
