# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Library containing the implementation of the tls certificates relation."""


import logging
import os
import socket
from string import Template
from typing import Optional, List, Tuple

# from cryptography import x509
from cryptography.x509.extensions import ExtensionType
from ops.charm import CharmBase, ActionEvent

from charms.tls_certificates_interface.v1.tls_certificates import (
    generate_csr,
    generate_private_key,
)
from constants import (
    TLS_RELATION,
    TLS_SSL_CA_FILE,
    TLS_SSL_KEY_FILE,
    TLS_SSL_CERT_FILE,
    TLS_SSL_CA_PATH,
)
from mysqlsh_helpers import MYSQLD_CONFIG_DIRECTORY
from ops.framework import Object

logger = logging.getLogger(__name__)

SCOPE = "unit"


class MySQLTLS(Object):
    """TODO: class comment"""

    def __init__(self, charm: CharmBase):
        super().__init__(charm, "certificates")
        self.charm = charm

        self.framework.observe(
            self.charm.on.set_tls_private_key_action, self._on_set_tls_private_key
        )
        self.framework.observe(
            self.charm.on[TLS_RELATION].relation_joined, self._on_tls_relation_joined
        )

    def _on_set_tls_private_key(self, event: ActionEvent) -> None:
        """Action for setting a TLS private key"""
        self._request_certificate("app", event.params.get("private-key", None))

    def _request_certificate(self, param: Optional[str]):
        """Request a certificate to TLS Certificates Operator."""
        if param is None:
            key = generate_private_key()
        else:
            key = self._parse_tls_file(param)

        csr = generate_csr(
            private_key=key,
            subject=self.charm.get_hostname_by_unit(self.charm.unit.name),
            sans=self._get_sans(),
            additional_critical_extensions=self._get_tls_extensions(),
        )

        # store
        self.charm.set_secret(SCOPE, "key", key.decode("utf-8"))
        self.charm.set_secret(SCOPE, "csr", csr.decode("utf-8"))

        if self.charm.model.get_relation(TLS_RELATION):
            self.certs.request_certificate_creation(certificate_signing_request=csr)

    def _on_tls_relation_joined(self, _) -> None:
        """Request certificate when TLS relation joined."""
        self._request_certificate(None)

    def _get_sans(self) -> List[str]:
        """Create a list of DNS names for a unit.

        Returns:
            A list representing the hostnames of the unit.
        """
        unit_id = self.charm.unit.name.split("/")[1]
        return [
            f"{self.charm.app.name}-{unit_id}",
            socket.getfqdn(),
            str(self.charm.model.get_binding(self.peer_relation).network.bind_address),
        ]

    @staticmethod
    def _get_tls_extensions() -> Optional[List[ExtensionType]]:
        # TODO: verify extensions need
        return None

    def get_tls_content(self) -> Tuple[Optional[str], Optional[str]]:
        """Retrieve TLS files.

        #TODO: check mysql needs
        """
        ca = self.charm.get_secret(SCOPE, "ca")
        chain = self.charm.get_secret(SCOPE, "chain")
        ca_file = chain if chain else ca

        key = self.charm.get_secret(SCOPE, "key")
        cert = self.charm.get_secret(SCOPE, "cert")
        return key, ca_file, cert

    def push_tls_files_to_workload(self) -> None:
        """Push TLS files to unit."""
        ssl_key, ssl_ca, ssl_cert = self.get_tls_content()

        if ssl_key:
            self.charm._mysql._write_content_to_file(
                f"{MYSQLD_CONFIG_DIRECTORY}/{TLS_SSL_KEY_FILE}", ssl_key, permission=0o400
            )

        if ssl_ca:
            self.charm._mysql._write_content_to_file(
                f"{TLS_SSL_CA_PATH}/{TLS_SSL_CA_FILE}", ssl_ca, permission=0o400
            )

        if ssl_cert:
            self.charm._mysql._write_content_to_file(
                f"{MYSQLD_CONFIG_DIRECTORY}/{TLS_SSL_CERT_FILE}", ssl_cert, permission=0o400
            )

    def create_tls_config_file(self) -> None:
        """Render TLS template directly to file."""
        # TODO: error handling
        with open("templates/tls.cnf") as template_file:
            template = Template(template_file.read())
            config_string = template(
                tls_ssl_key_file=TLS_SSL_KEY_FILE,
                tls_ssl_ca_path=TLS_SSL_CA_PATH,
                tls_ssl_cert_file=TLS_SSL_CERT_FILE,
                tls_ssl_key_file=TLS_SSL_KEY_FILE,
            )

        self.charm._mysql.write_content_to_file(
            f"{MYSQLD_CONFIG_DIRECTORY}/z-custom-tls.cnf",
            config_string,
            owner="root",
            group="root",
        )

    def remove_tls_config_file(self) -> None:
        """Remove TLS configuration file."""
        # TODO: error handling
        os.remove(f"{MYSQLD_CONFIG_DIRECTORY}/z-custom-tls.cnf")
