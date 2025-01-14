# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Set up IP address changes observer."""

import logging
import os
import signal
import subprocess
import typing

from ops.charm import CharmEvents
from ops.framework import EventBase, EventSource, Object
from ops.model import ActiveStatus

logger = logging.getLogger(__name__)

# File path for the spawned ip address observer process to write logs.
LOG_FILE_PATH = "/var/log/ip_address_observer.log"


if typing.TYPE_CHECKING:
    from charm import MySQLOperatorCharm


class IPAddressChangeEvent(EventBase):
    """A custom event for IP address change."""


class IPAddressChangeCharmEvents(CharmEvents):
    """A CharmEvents extension for IP address changes.

    Includes :class:`IPAddressChangeEvent` in those that can be handled.
    """

    ip_address_change = EventSource(IPAddressChangeEvent)


class IPAddressObserver(Object):
    """Observes changes in the unit's IP address.

    Observed IP address changes cause :class:`IPAddressChangeEvent` to be emitted.
    """

    def __init__(self, charm: "MySQLOperatorCharm"):
        super().__init__(charm, "ip-address-observer")

        self.charm = charm

    def start_observer(self):
        """Start the IP address observer running in a new process."""
        if not isinstance(self.charm.unit.status, ActiveStatus) or self.charm.peers is None:
            return

        if pid := self.charm.unit_peer_data.get("observer-pid"):
            if check_pid(int(pid)):
                return

        logger.info("Starting IP address observer process")

        juju_command = (
            os.path.exists("/usr/bin/juju-run") and "/usr/bin/juju-run" or "/usr/bin/juju-exec"
        )

        # We need to trick Juju into thinking that we are not running
        # in a hook context, as Juju will disallow use of juju-run.
        new_env = os.environ.copy()
        if "JUJU_CONTEXT_ID" in new_env:
            new_env.pop("JUJU_CONTEXT_ID")

        process = subprocess.Popen(
            [
                "/usr/bin/python3",
                "scripts/ip_address_dispatcher.py",
                juju_command,
                self.charm.unit.name,
                self.charm.charm_dir,
            ],
            stdout=open(LOG_FILE_PATH, "a"),
            stderr=subprocess.STDOUT,
            env=new_env,
        )

        self.charm.unit_peer_data.update({"observer-pid": f"{process.pid}"})
        logging.info(f"Started IP address observer process with PID {process.pid}")

    def stop_observer(self):
        """Stop running the observer if it is indeed running."""
        if self.charm.peers is None or "observer-pid" not in self.charm.unit_peer_data:
            return

        observer_pid = int(self.charm.unit_peer_data["observer-pid"])

        try:
            os.kill(observer_pid, signal.SIGTERM)
            logger.info(f"Stopped running IP address observer process with PID {observer_pid}")
            del self.charm.unit_peer_data["observer-pid"]
        except OSError:
            pass


def check_pid(pid: int) -> bool:
    """Check if pid exists."""
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    else:
        return True
