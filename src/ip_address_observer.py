# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""IP address changes observer."""

import logging
import os
import signal
import socket
import subprocess
import sys
import time
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
        if (
            not isinstance(self.charm.unit.status, ActiveStatus)
            or self.charm.peers is None
            or "observer-pid" in self.charm.unit_peer_data
        ):
            return

        logger.info("Starting IP address observer process")

        # We need to trick Juju into thinking that we are not running
        # in a hook context, as Juju will disallow use of juju-run.
        new_env = os.environ.copy()
        if "JUJU_CONTEXT_ID" in new_env:
            new_env.pop("JUJU_CONTEXT_ID")

        process = subprocess.Popen(
            [
                "/usr/bin/python3",
                "src/ip_address_observer.py",
                "/usr/bin/juju-run",
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


def dispatch(run_command, unit, charm_directory):
    """Use the juju-run command to dispatch :class:`IPAddressChangeEvent`."""
    dispatch_sub_command = "JUJU_DISPATCH_PATH=hooks/ip_address_change {}/dispatch"
    subprocess.run([run_command, "-u", unit, dispatch_sub_command.format(charm_directory)])


def main():
    """Main watch and dispatch loop.

    Determine the host IP address every 30 seconds, and dispatch and event if it
    changes.
    """
    run_command, unit, charm_directory = sys.argv[1:]

    def _get_local_ip():
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0)

        try:
            s.connect(("10.10.10.10", 1))
            ip = s.getsockname()[0]
        except Exception:
            logger.exception("Unable to get local IP address")
            ip = "127.0.0.1"

        return ip

    previous_ip_address = None
    while True:
        ip_address = _get_local_ip()

        if not previous_ip_address:
            print(f"Setting initial ip address to {ip_address}")
            sys.stdout.flush()
            previous_ip_address = ip_address
        elif ip_address != previous_ip_address:
            print(f"Detected ip address change from {previous_ip_address} to {ip_address}")
            sys.stdout.flush()
            previous_ip_address = ip_address
            dispatch(run_command, unit, charm_directory)

        time.sleep(30)


if __name__ == "__main__":
    main()
