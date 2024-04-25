# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Library containing logic pertaining to hostname resolutions in the VM charm."""

import json
import logging
import socket
import typing

from charms.mysql.v0.async_replication import PRIMARY_RELATION, REPLICA_RELATION
from ops import Relation
from ops.charm import RelationDepartedEvent
from ops.framework import Object
from ops.model import BlockedStatus, Unit
from python_hosts import Hosts, HostsEntry

from constants import HOSTNAME_DETAILS, PEER
from ip_address_observer import IPAddressChangeCharmEvents, IPAddressObserver
from mysql_vm_helpers import MySQLFlushHostCacheError

logger = logging.getLogger(__name__)

if typing.TYPE_CHECKING:
    from charm import MySQLOperatorCharm

COMMENT_PREFIX = "unit="
# relations that contain hostname details
PEER_RELATIONS = [PEER, PRIMARY_RELATION, REPLICA_RELATION]


class SearchableHosts(Hosts):
    """Extended Hosts class with find_by_comment method."""

    def find_by_comment(self, comment: str) -> typing.Optional[HostsEntry]:
        """Returns HostsEntry instances from the Hosts object where the supplied comment matches.

        Args:
            comment: The comment line to search for
        Returns:
            HostEntry instance
        """
        if not self.entries:
            return None

        for entry in self.entries:
            if not entry.is_real_entry():
                # skip comments and blank lines
                continue
            if entry.comment and comment in entry.comment:
                # return the first match, we assume no duplication
                return entry


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
            self.framework.observe(
                self.charm.on[relation].relation_changed, self._potentially_update_etc_hosts
            )
            self.framework.observe(
                self.charm.on[relation].relation_departed, self._remove_host_from_etc_hosts
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

        host_details = {"names": [hostname, fqdn, self.charm.unit_host_alias], "address": ip}

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
                        entry = HostsEntry(
                            address=unit_details["address"],
                            names=unit_details["names"],
                            comment=f"{COMMENT_PREFIX}{unit_details['names'][2]}",
                            entry_type="ipv4",
                        )
                    else:
                        # case when migrating from old format
                        unit_name = f"{key.name.replace('/', '-')}.{self.model.uuid}"
                        entry = HostsEntry(
                            address=unit_details["ip"],
                            names=[unit_details["hostname"], unit_details["fqdn"], unit_name],
                            comment=f"{COMMENT_PREFIX}{unit_name}",
                            entry_type="ipv4",
                        )

                    host_entries.append(entry)

        return host_entries

    def _does_etc_hosts_need_update(self, hosts_entries: list[HostsEntry]) -> bool:
        # load host file
        hosts = SearchableHosts()

        for host_entry in hosts_entries:
            assert host_entry.comment, "Host entries should have comments"
            if current_entry := hosts.find_by_comment(host_entry.comment):
                if current_entry.address != host_entry.address:
                    # need update if the IP address is different
                    return True
            else:
                # need update if a new entry is found
                return True
        return False

    def _potentially_update_etc_hosts(self, _) -> None:
        """Potentially update the /etc/hosts file with new hostname to IP for units."""
        if not self.charm._is_peer_data_set:
            return

        host_details = self._get_peer_host_details()
        if not host_details:
            logger.debug("No hostnames in the peer databag. Skipping update of /etc/hosts")
            return

        if not self._does_etc_hosts_need_update(host_details):
            logger.debug("No changes in /etc/hosts changed. Skipping update to /etc/hosts")
            return

        logger.debug("Updating /etc/hosts with new hostname to IP mappings")
        hosts = Hosts()

        # Add all host entries
        # (force is required to overwrite existing 127.0.1.1 on MAAS)
        hosts.add(host_details, force=True)
        hosts.write()

        try:
            self.charm._mysql.flush_host_cache()
        except MySQLFlushHostCacheError:
            self.charm.unit.status = BlockedStatus("Unable to flush MySQL host cache")

    def _remove_host_from_etc_hosts(self, event: RelationDepartedEvent) -> None:
        """Remove the departing unit from the /etc/hosts file."""
        departing_unit_name = f"{event.unit.name.replace('/', '-')}.{self.model.uuid}"
        logger.debug(f"Checking if an entry for {departing_unit_name} is in /etc/hosts")

        hosts = Hosts()
        if not hosts.exists(names=[departing_unit_name]):
            logger.debug(f"Entry {departing_unit_name} not found in /etc/hosts. Skipping removal.")
            return

        logger.debug(f"Entry {departing_unit_name} found in /etc/hosts. Removing it.")
        hosts.remove_all_matching(name=departing_unit_name)
        hosts.write()

        try:
            self.charm._mysql.flush_host_cache()
        except MySQLFlushHostCacheError:
            self.charm.unit.status = BlockedStatus("Unable to flush MySQL host cache")

    def init_hosts(self, _) -> None:
        """Initialize the /etc/hosts file with the unit's hostname."""
        logger.debug("Initializing /etc/hosts with the unit data")
        self._update_host_details_in_databag(None)
        self._potentially_update_etc_hosts(None)
