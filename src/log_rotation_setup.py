# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Handler for log rotation setup in relation to COS."""

import logging
import typing
from pathlib import Path

import yaml
from ops.framework import Object

from constants import COS_AGENT_RELATION_NAME

if typing.TYPE_CHECKING:
    from charm import MySQLOperatorCharm

logger = logging.getLogger(__name__)

_POSITIONS_FILE = "/var/snap/grafana-agent/current/grafana-agent-positions/log_file_scraper.yml"
_LOGS_SYNCED = "logs_synced"


class LogRotationSetup(Object):
    """Configure logrotation settings in relation to COS integration."""

    def __init__(self, charm: "MySQLOperatorCharm"):
        super().__init__(charm, "log-rotation-setup")

        self.charm = charm

        self.framework.observe(self.charm.on.update_status, self._update_logs_rotation)
        self.framework.observe(
            self.charm.on[COS_AGENT_RELATION_NAME].relation_created, self._cos_relation_created
        )
        self.framework.observe(
            self.charm.on[COS_AGENT_RELATION_NAME].relation_broken, self._cos_relation_broken
        )

    @property
    def _logs_are_syncing(self):
        return self.charm.unit_peer_data.get(_LOGS_SYNCED) == "true"

    def setup(self):
        """Setup log rotation."""
        # retention setting
        if self.charm.config.logs_retention_period == "auto":
            retention_period = 1 if self._logs_are_syncing else 3
        else:
            retention_period = int(self.charm.config.logs_retention_period)

        # compression setting
        compress = self._logs_are_syncing or not self.charm.has_cos_relation

        self.charm._mysql.setup_logrotate_and_cron(
            retention_period, self.charm.text_logs, compress
        )

    def _update_logs_rotation(self, _):
        """Check for log rotation auto configuration handler.

        Reconfigure log rotation if promtail/gagent start sync.
        """
        if not self.model.get_relation(COS_AGENT_RELATION_NAME):
            return

        if self._logs_are_syncing:
            # reconfiguration done
            return

        positions_file = Path(_POSITIONS_FILE)

        not_started_msg = "Log syncing not yet started."
        if not positions_file.exists():
            logger.debug(not_started_msg)
            return

        with open(positions_file, "r") as pos_fd:
            positions = yaml.safe_load(pos_fd.read())

        if sync_files := positions.get("positions"):
            for log_file, line in sync_files.items():
                if "mysql" in log_file and int(line) > 0:
                    break
            else:
                logger.debug(not_started_msg)
                return
        else:
            logger.debug(not_started_msg)
            return

        logger.info("Reconfigure log rotation after logs upload started")
        self.charm.unit_peer_data[_LOGS_SYNCED] = "true"
        self.setup()

    def _cos_relation_created(self, event):
        """Handle relation created."""
        if not self.charm._is_peer_data_set:
            logger.debug("Charm not yet set up. Deferring log rotation setup.")
            event.defer()
            return
        logger.info("Reconfigure log rotation on cos relation created")
        self.setup()

    def _cos_relation_broken(self, _):
        """Unset auto value for log retention."""
        logger.info("Reconfigure log rotation after logs upload stops")

        del self.charm.unit_peer_data[_LOGS_SYNCED]
        self.setup()
