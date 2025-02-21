# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Library containing logic pertaining to hostname resolutions in the VM charm."""

import json
import logging
import socket
import typing

from ops.framework import Object
from ops.model import Unit
from python_hosts import Hosts, HostsEntry

from constants import HOSTNAME_DETAILS, PEER
from ip_address_observer import IPAddressChangeCharmEvents, IPAddressObserver
from mysql_vm_helpers import MySQLFlushHostCacheError

logger = logging.getLogger(__name__)

if typing.TYPE_CHECKING:
    from charm import MySQLOperatorCharm

COMMENT = "Managed by mysql charm"


class MySQLMachineHostnameResolution(Object):
    """Encapsulation of the the machine hostname resolution."""

    on = (  # pyright: ignore [reportIncompatibleMethodOverride, reportAssignmentType
        IPAddressChangeCharmEvents()
    )

    def __init__(self, charm: "MySQLOperatorCharm"):
        super().__init__(charm, "hostname-resolution")

        self.charm = charm

        self.ip_address_observer = IPAddressObserver(charm)

        self.framework.observe(self.charm.on.config_changed, self._update_host_details_in_databag)
        self.framework.observe(self.charm.on.ip_address_change, self._on_ip_address_change)

        self.framework.observe(self.charm.on[PEER].relation_changed, self.update_etc_hosts)
        self.framework.observe(self.charm.on[PEER].relation_departed, self.update_etc_hosts)

        self.ip_address_observer.start_observer()

    def _update_host_details_in_databag(self, _) -> None:
        hostname = socket.gethostname()
        fqdn = socket.getfqdn()

        ip = str(self.model.get_binding(PEER).network.bind_address)

        host_details = {"names": [hostname, fqdn], "address": ip}

        self.charm.unit_peer_data[HOSTNAME_DETAILS] = json.dumps(host_details)

    def _on_ip_address_change(self, _) -> None:
        """Handle ip address changed.

        admin_address is bound to previous IP, requiring mysqld restart.
        """
        self._update_host_details_in_databag(None)
        self.charm._mysql.restart_mysqld()

    def _get_host_details(self) -> list[HostsEntry]:
        host_details = []

        if not self.charm.peers:
            return []

        for key, data in self.charm.peers.data.items():
            if isinstance(key, Unit) and data.get(HOSTNAME_DETAILS):
                unit_details = json.loads(data[HOSTNAME_DETAILS])

                if unit_details.get("address"):
                    entry = HostsEntry(comment=COMMENT, entry_type="ipv4", **unit_details)
                else:
                    # case when migrating from old format
                    entry = HostsEntry(
                        address=unit_details["ip"],
                        names=[unit_details["hostname"], unit_details["fqdn"]],
                        comment=COMMENT,
                        entry_type="ipv4",
                    )

                host_details.append(entry)

        return host_details

    def update_etc_hosts(self, _) -> bool:
        """Potentially update the /etc/hosts file with new hostname to IP for units.

        Returns: whether a loopback host entry exists in /etc/hosts
        """
        if not self.charm._is_peer_data_set:
            return False

        host_entries = self._get_host_details()
        if not host_entries:
            logger.debug("No hostnames in the peer databag. Skipping update of /etc/hosts")
            return False

        logger.debug("Updating /etc/hosts with new hostname to IP mappings")
        hosts = Hosts()

        if loopback_host_exists := hosts.exists(address="127.0.1.1", names=[socket.getfqdn()]):
            # remove MAAS injected entry
            logger.debug("Removing MAAS injected entry from /etc/hosts")
            hosts.remove_all_matching(address="127.0.1.1")

        hosts.remove_all_matching(comment=COMMENT)
        hosts.add(host_entries)
        hosts.write()

        try:
            self.charm._mysql.flush_host_cache()
        except MySQLFlushHostCacheError:
            logger.warning("Unable to flush MySQL host cache")

        return loopback_host_exists
