# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Handler for log rotation setup on relation to COS."""

import logging
import os
import subprocess
import typing

from ops.charm import CharmEvents
from ops.framework import EventBase, EventSource, Object

from constants import COS_AGENT_RELATION_NAME

if typing.TYPE_CHECKING:
    from charm import MySQLOperatorCharm

logger = logging.getLogger(__name__)


class LogSyncing(EventBase):
    """Custom event for the start of log syncing."""


class LogSyncingEvents(CharmEvents):
    """Charm event for log syncing init."""

    log_syncing = EventSource(LogSyncing)


class LogRotationSetup(Object):
    """TODO: Proper comment"""

    def __init__(self, charm: "MySQLOperatorCharm"):
        super().__init__(charm, "log-rotation-setup")

        self.charm = charm

        self.framework.observe(self.charm.on.log_syncing, self._log_syncing)
        self.framework.observe(
            self.charm.on[COS_AGENT_RELATION_NAME].relation_created, self._cos_relation_created
        )
        self.framework.observe(
            self.charm.on[COS_AGENT_RELATION_NAME].relation_broken, self._cos_relation_broken
        )

    def _cos_relation_created(self, _):
        script_path = f"{self.charm.charm_dir}/scripts/wait_for_log_sync.sh"

        new_env = os.environ.copy()
        if "JUJU_CONTEXT_ID" in new_env:
            new_env.pop("JUJU_CONTEXT_ID")

        subprocess.Popen([script_path], env=new_env)
        logger.info("Started log sync wait script")

    def _log_syncing(self, _):
        """LogSyncing event handler.

        Reconfigure log rotation after promtail start sync.
        """
        if self.charm.config.logs_retention_period != "auto":
            return

        logger.info("Reconfigure log rotation after logs upload started")
        self.charm._mysql.setup_logrotate_and_cron(
            logs_retention_period="1",
            enabled_log_files=self.charm.text_logs,
            logs_compression=True,
        )

        self.charm.unit_peer_data["logs_synced"] = "true"

    def _cos_relation_broken(self, _):
        if self.charm.config.logs_retention_period != "auto":
            return
        logger.info("Reconfigure log rotation after logs upload stops")
        self.charm._mysql.setup_logrotate_and_cron(
            logs_retention_period="3",
            enabled_log_files=self.charm.text_logs,
            logs_compression=True,
        )

        del self.charm.unit_peer_data["logs_synced"]
