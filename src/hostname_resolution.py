# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Library containing logic pertaining to hostname resolutions in the VM charm."""

import io
import logging
import socket

from ops.charm import CharmBase
from ops.framework import Object
from ops.model import Unit

from constants import HOSTNAME_TO_IP_KEY, PEER

logger = logging.getLogger(__name__)


class MySQLMachineHostnameResolution(Object):
    """Encapsulation of the the machine hostname resolution."""

    def __init__(self, charm: CharmBase):
        super().__init__(charm, "hostname-resolution")

        self.charm = charm

        self.framework.observe(self.charm.on.config_changed, self._update_hostname_ip_in_databag)

        self.framework.observe(
            self.charm.on[PEER].relation_changed, self._potentially_update_etc_hosts
        )

    def _update_hostname_ip_in_databag(self, _) -> None:
        with open("/etc/hostname", "r") as hostname_file:
            hostname = hostname_file.readline().strip()

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

        ip = _get_local_ip()

        self.charm.unit_peer_data[HOSTNAME_TO_IP_KEY] = f"{hostname}={ip}"

    def _get_hostname_ip_pairings(self) -> dict[str, str]:
        hostname_to_ips = {}

        for key, data in self.charm.peers.data.items():
            if isinstance(key, Unit) and data.get(HOSTNAME_TO_IP_KEY):
                hostname, ip = data[HOSTNAME_TO_IP_KEY].split("=")
                hostname_to_ips[hostname] = ip

        return hostname_to_ips

    def _does_etc_hosts_need_update(self, hostname_to_ips: dict[str, str]) -> bool:
        host_ip_needs_update = False
        hosts_in_file = []
        with open("/etc/hosts", "r") as hosts_file:
            for line in hosts_file:
                for hostname, ip in hostname_to_ips.items():
                    if line.strip() == "" or line.startswith("#"):
                        continue

                    if hostname == line.split()[1]:
                        hosts_in_file.append(hostname)

                    if hostname in line and ip not in line:
                        host_ip_needs_update = True

        for hostname in hostname_to_ips:
            if hostname not in hosts_in_file:
                return True

        return host_ip_needs_update

    def _potentially_update_etc_hosts(self, _) -> None:
        """Potentially update the /etc/hosts file with new hostname to IP for units."""
        hostname_to_ips = self._get_hostname_ip_pairings()
        if not hostname_to_ips:
            logger.debug("No hostnames in the peer databag. Skipping update to /etc/hosts")
            return

        if not self._does_etc_hosts_need_update(hostname_to_ips):
            logger.debug("No hostnames in /etc/hosts changed. Skipping update to /etc/hosts")
            return

        hosts_in_file = []
        with io.StringIO() as updated_hosts_file:
            with open("/etc/hosts", "r") as hosts_file:
                for line in hosts_file:
                    if line.strip() == "" or line.startswith("#"):
                        updated_hosts_file.write(line)
                        continue

                    line_contains_host = False

                    for hostname, ip in hostname_to_ips.items():
                        if hostname == line.split()[1]:
                            line_contains_host = True
                            hosts_in_file.append(hostname)

                            logger.info(f"Overwriting {hostname} with ip {ip} in /etc/hosts")
                            updated_hosts_file.write(f"{ip} {hostname}\n")
                            break

                    if not line_contains_host:
                        updated_hosts_file.write(line)

            logger.error(f"{hosts_in_file=}")
            for hostname, ip in hostname_to_ips.items():
                if hostname not in hosts_in_file:
                    logger.info(f"Adding {hostname} with ip {ip} to /etc/hosts")
                    updated_hosts_file.write(f"{ip} {hostname}\n")

            with open("/etc/hosts", "w") as hosts_file:
                hosts_file.write(updated_hosts_file.getvalue())
