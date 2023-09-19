# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Custom event for flushing mysql logs to be called from a logrotate script."""

import os
import typing

from ops.charm import CharmEvents
from ops.framework import EventBase, EventSource, Object

if typing.TYPE_CHECKING:
    from charm import MySQLOperatorCharm


class FlushMySQLLogsEvent(EventBase):
    """A custom event to flush logs."""


class FlushMySQLLogsCharmEvents(CharmEvents):
    """A CharmEvent extension for flush logs.

    Includes :class:`FlushMySQLLogsEvent` in those that can be handled.
    """

    flush_mysql_logs = EventSource(FlushMySQLLogsEvent)


class MySQLLogs(Object):
    """Encapsulates the handling of MySQL logs (including flushing them)."""

    def __init__(self, charm: "MySQLOperatorCharm"):
        super().__init__(charm, "mysql-logs")

        self.charm = charm

    def _flush_mysql_logs(self, _) -> None:
        """Flush the specified (via LOGS_TYPE env var) mysql logs."""
        logs_type = os.environ.get("LOGS_TYPE")
        if logs_type not in ["error", "general", "slowquery"]:
            logger.debug(f"Invalid flush of logs type: { logs_type }")
            return

        self.charm._mysql.flush_mysql_logs(logs_type)
