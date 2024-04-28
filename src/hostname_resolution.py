# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Library containing logic pertaining to hostname resolutions in the VM charm."""

import json
import logging
import socket
import typing

from charms.mysql.v0.async_replication import PRIMARY_RELATION, REPLICA_RELATION
from ops import Relation
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
# relations that contain hostname details
PEER_RELATIONS = [PEER, PRIMARY_RELATION, REPLICA_RELATION]


class MySQLMachineHostnameResolution(Object):
    """Encapsulation of the the machine hostname resolution."""

    on = (  # pyright: ignore [reportIncompatibleMethodOverride, reportAssignmentType]
        IPAddressChangeCharmEvents()
    )

    def __init__(self, charm: "MySQLOperatorCharm"):
        super().__init__(charm, "hostname-resolution")

        self.charm = charm

        self.ip_address_observer = IPAddressObserver(charm)

        self.framework.observe(self.charm.on.config_changed, self._update_host_details_in_databag)
        self.framework.observe(self.on.ip_address_change, self._update_host_details_in_databag)
        self.framework.observe(self.charm.on.upgrade_charm, self._update_host_details_in_databag)

        for relation in PEER_RELATIONS:
            self.framework.observe(self.charm.on[relation].relation_changed, self.update_etc_hosts)
            self.framework.observe(
                self.charm.on[relation].relation_departed, self.update_etc_hosts
            )

        self.ip_address_observer.start_observer()

    @property
    def _relations_with_peers(self) -> list[Relation]:
        """Return list of Relation that have hostname details."""
        relations = []
        for rel_name in PEER_RELATIONS:
            relations.extend(self.charm.model.relations[rel_name])

        return relations

    @property
    def is_unit_in_hosts(self) -> bool:
        """Check if the unit is in the /etc/hosts file."""
        hosts = Hosts()
        return hosts.exists(names=[self.charm.unit_host_alias])

    def _update_host_details_in_databag(self, _) -> None:
        """Update the hostname details in the peer databag."""
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

        #host_details = {"names": [hostname, fqdn, self.charm.unit_host_alias], "address": ip}
        host_details = {"names": [self.charm.unit_host_alias], "address": ip}

        logger.debug("Updating hostname details for relations")

        for relation in self._relations_with_peers:
            relation.data[self.charm.unit][HOSTNAME_DETAILS] = json.dumps(host_details)

    def _get_peer_host_details(self) -> list[HostsEntry]:
        """Return a list of HostsEntry instances for peer units."""
        host_entries = list()

        # iterate over all relations that contain hostname details
        for relation in self._relations_with_peers:
            for key, data in relation.data.items():
                if isinstance(key, Unit) and data.get(HOSTNAME_DETAILS):
                    unit_details = json.loads(data[HOSTNAME_DETAILS])
                    if unit_details.get("address"):
                        entry = HostsEntry(comment=COMMENT, entry_type="ipv4", **unit_details)
                    else:
                        # case when migrating from old format
                        unit_alias = f"{key.name.replace('/', '-')}.{self.model.uuid}"
                        entry = HostsEntry(
                            address=unit_details["ip"],
                            #names=[unit_details["hostname"], unit_details["fqdn"], unit_alias],
                            names=[unit_alias],
                            comment=COMMENT,
                            entry_type="ipv4",
                        )

                    host_entries.append(entry)

        return host_entries

    def get_hostname_mapping(self) -> list[dict]:
        """Return a list of hostname to IP mapping for all units."""
        host_details = self._get_peer_host_details()
        return [{"names": entry.names, "address": entry.address} for entry in host_details]

    def update_etc_hosts(self, _) -> None:
        """Potentially update the /etc/hosts file with new hostname to IP for units."""
        if not self.charm._is_peer_data_set:
            return

        host_details = self._get_peer_host_details()
        if not host_details:
            logger.debug("No hostnames in the peer databag. Skipping update of /etc/hosts")
            return

        self._update_host_details_in_databag(None)
        logger.debug("Updating /etc/hosts with new hostname to IP mappings")
        hosts = Hosts()

        # clean managed entries
        hosts.remove_all_matching(comment=COMMENT)

        # Add all host entries
        # (force is required to overwrite existing 127.0.1.1 on MAAS)
        hosts.add(host_details, force=True, allow_address_duplication=True, merge_names=True)
        hosts.write()

        try:
            self.charm._mysql.flush_host_cache()
        except MySQLFlushHostCacheError:
            logger.warning("Unable to flush MySQL host cache.")
