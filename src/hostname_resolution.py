# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Library containing logic pertaining to hostname resolutions in the VM charm."""

import io
import json
import logging
import socket

from ops.charm import CharmBase, RelationDepartedEvent
from ops.framework import Object
from ops.model import BlockedStatus, Unit

from constants import HOSTNAME_DETAILS, PEER
from ip_address_observer import IPAddressChangeCharmEvents, IPAddressObserver
from mysql_vm_helpers import MySQLFlushHostCacheError

logger = logging.getLogger(__name__)


class MySQLMachineHostnameResolution(Object):
    """Encapsulation of the the machine hostname resolution."""

    on = IPAddressChangeCharmEvents()

    def __init__(self, charm: CharmBase):
        super().__init__(charm, "hostname-resolution")

        self.charm = charm

        self.ip_address_observer = IPAddressObserver(charm)

        self.framework.observe(self.charm.on.config_changed, self._update_host_details_in_databag)
        self.framework.observe(self.on.ip_address_change, self._update_host_details_in_databag)

        self.framework.observe(
            self.charm.on[PEER].relation_changed, self._potentially_update_etc_hosts
        )
        self.framework.observe(
            self.charm.on[PEER].relation_departed, self._remove_host_from_etc_hosts
        )

        self.ip_address_observer.start_observer()

    def _update_host_details_in_databag(self, _) -> None:
        hostname = socket.gethostname()
        fqdn = socket.getfqdn()

        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0)
        try:
            s.connect(("10.10.10.10", 1))
            ip = s.getsockname()[0]
        except Exception:
            logger.exception("Unable to get local IP address")
            ip = "127.0.0.1"

        host_details = {
            "hostname": hostname,
            "fqdn": fqdn,
            "ip": ip,
        }

        self.charm.unit_peer_data[HOSTNAME_DETAILS] = json.dumps(host_details)

    def _get_host_details(self) -> dict[str, str]:
        host_details = {}

        for key, data in self.charm.peers.data.items():
            if isinstance(key, Unit) and data.get(HOSTNAME_DETAILS):
                unit_details = json.loads(data[HOSTNAME_DETAILS])
                unit_details["unit"] = key.name
                host_details[unit_details["hostname"]] = unit_details

        return host_details

    def _does_etc_hosts_need_update(self, host_details: dict[str, str]) -> bool:
        outdated_hosts = host_details.copy()

        with open("/etc/hosts", "r") as hosts_file:
            for line in hosts_file:
                if "# unit=" not in line:
                    continue

                ip, fqdn, hostname = line.split("#")[0].strip().split()
                if outdated_hosts.get(hostname).get("ip") == ip:
                    outdated_hosts.pop(hostname)

        return bool(outdated_hosts)

    def _potentially_update_etc_hosts(self, _) -> None:
        """Potentially update the /etc/hosts file with new hostname to IP for units."""
        host_details = self._get_host_details()
        if not host_details:
            logger.debug("No hostnames in the peer databag. Skipping update of /etc/hosts")

        if not self._does_etc_hosts_need_update(host_details):
            logger.debug("No hostnames in /etc/hosts changed. Skipping update to /etc/hosts")

        hosts_in_file = []

        with io.StringIO() as updated_hosts_file:
            with open("/etc/hosts", "r") as hosts_file:
                for line in hosts_file:
                    if "# unit=" not in line:
                        updated_hosts_file.write(line)
                        continue

                    for hostname, details in host_details.items():
                        if hostname == line.split()[2]:
                            hosts_in_file.append(hostname)

                            fqdn, ip, unit = details["fqdn"], details["ip"], details["unit"]

                            logger.info(
                                f"Overwriting {hostname} ({unit=}) with {ip=}, {fqdn=} in /etc/hosts"
                            )
                            updated_hosts_file.write(f"{ip} {fqdn} {hostname} # unit={unit}\n")
                            break

            for hostname, details in host_details.items():
                if hostname not in hosts_in_file:
                    fqdn, ip, unit = details["fqdn"], details["ip"], details["unit"]

                    logger.info(f"Adding {hostname} ({unit=} with {ip=}, {fqdn=} in /etc/hosts")
                    updated_hosts_file.write(f"{ip} {fqdn} {hostname} # unit={unit}\n")

            with open("/etc/hosts", "w") as hosts_file:
                hosts_file.write(updated_hosts_file.getvalue())

        try:
            self.charm._mysql.flush_host_cache()
        except MySQLFlushHostCacheError:
            self.unit.status = BlockedStatus("Unable to flush MySQL host cache")

    def _remove_host_from_etc_hosts(self, event: RelationDepartedEvent) -> None:
        departing_unit_name = event.unit.name

        with io.StringIO() as updated_hosts_file:
            with open("/etc/hosts", "r") as hosts_file:
                for line in hosts_file:
                    if f"# unit={departing_unit_name}" not in line:
                        updated_hosts_file.write(line)

            with open("/etc/hosts", "w") as hosts_file:
                hosts_file.write(updated_hosts_file.getvalue())

        try:
            self.charm._mysql.flush_host_cache()
        except MySQLFlushHostCacheError:
            self.unit.status = BlockedStatus("Unable to flush MySQL host cache")
