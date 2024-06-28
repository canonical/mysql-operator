# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Custom event for flushing mysql logs to be called from a logrotate script."""

import logging
import os
import typing

from charms.mysql.v0.mysql import MySQLTextLogs
from ops.charm import CharmEvents
from ops.framework import EventBase, EventSource, Object

if typing.TYPE_CHECKING:
    from charm import MySQLOperatorCharm

logger = logging.getLogger(__name__)


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

        self.framework.observe(self.charm.on.flush_mysql_logs, self._flush_mysql_logs)

    def _flush_mysql_logs(self, _) -> None:
        """Flush the specified (via LOGS_TYPE env var) mysql logs."""
        if (
            self.charm.peers is None
            or self.charm.unit_peer_data.get("unit-initialized") != "True"
            or not self.charm.upgrade.idle
            or not self.charm._mysql.is_mysqld_running()
        ):
            # skip when not initialized, during an upgrade, or when mysqld is not running
            return

        logs_type = os.environ.get("LOGS_TYPE", "")

        try:
            text_logs = MySQLTextLogs[logs_type]
        except KeyError:
            logger.debug(f"Invalid flush of logs type: {logs_type}")
            return

        self.charm._mysql.flush_mysql_logs(text_logs)
