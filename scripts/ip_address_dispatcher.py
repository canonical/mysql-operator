# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Dispatch event if IP address changes."""

import subprocess
import logging
import socket
import sys
import time

logger = logging.getLogger(__name__)

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
