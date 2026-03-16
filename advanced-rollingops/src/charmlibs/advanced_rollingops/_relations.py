# Copyright 2026 Canonical Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging

from ops import Relation
from ops.charm import RelationBrokenEvent
from ops.framework import Object

from charmlibs.advanced_rollingops._certificates import CertificatesManager
from charmlibs.advanced_rollingops._dp_interfaces_v1 import (
    RequirerCommonModel,
    ResourceCreatedEvent,
    ResourceEndpointsChangedEvent,
    ResourceProviderModel,
    ResourceRequirerEventHandler,
)
from charmlibs.advanced_rollingops._etcdctl import EtcdCtl
from charmlibs.advanced_rollingops._models import SECRET_FIELD

logger = logging.getLogger(__name__)


class SharedClientCertificateManager(Object):
    """Manage the shared rollingops client certificate via peer relation secret."""

    def __init__(self, charm, peer_relation_name: str) -> None:
        super().__init__(charm, 'shared-client-certificate')
        self.charm = charm
        self.peer_relation_name = peer_relation_name

        self.framework.observe(charm.on.leader_elected, self._on_leader_elected)
        self.framework.observe(
            charm.on[peer_relation_name].relation_changed,
            self._on_peer_relation_changed,
        )
        self.framework.observe(charm.on.secret_changed, self._on_secret_changed)

    @property
    def _peer_relation(self) -> Relation | None:
        return self.model.get_relation(self.peer_relation_name)

    def _on_leader_elected(self, event) -> None:
        self.create_and_share_certificate()

    def _on_secret_changed(self, event):
        # if event.secret.label == "rollingops-client-cert":
        #    self._sync_client_certificate()
        self.sync_to_local_files()

    def _on_peer_relation_changed(self, event) -> None:
        """React to peer relation changes.

        The leader ensures the shared certificate exists.
        All units try to persist the shared certificate locally if available.
        """
        self.create_and_share_certificate()
        self.sync_to_local_files()

    def create_and_share_certificate(self) -> None:
        """Ensure the application client certificate exists.

        Only the leader generates the certificate and writes it to the peer
        relation application databag.
        """
        relation = self._peer_relation
        if relation is None or not self.model.unit.is_leader():
            return

        app_data = relation.data[self.model.app]
        secret_id = app_data.get(SECRET_FIELD)
        if secret_id:
            return

        common_name = f'rollingops-{self.model.uuid}-{self.model.app.name}'
        cert_pem, key_pem, ca_pem = CertificatesManager.generate(common_name)

        secret = self.model.app.add_secret({
            'client-cert': cert_pem,
            'client-key': key_pem,
            'client-ca': ca_pem,
        })
        app_data[SECRET_FIELD] = secret.id

    def get_shared_certificate(self) -> tuple[str, str, str] | None:
        """Return the client certificate, key and ca from peer app data.

        Returns:
            A tuple of (certificate_pem, key_pem, ca_pem), or None if not yet available.
        """
        relation = self._peer_relation
        if relation is None:
            return None

        secret_id = relation.data[self.model.app].get(SECRET_FIELD)
        if not secret_id:
            return None

        secret = self.model.get_secret(id=secret_id)
        content = secret.get_content(refresh=True)
        return content['client-cert'], content['client-key'], content['client-ca']

    def sync_to_local_files(self) -> None:
        """Persist shared certificate locally if available."""
        shared = self.get_shared_certificate()
        if shared is None:
            logger.debug('Shared rollingops client certificate is not available yet')
            return False

        cert_pem, key_pem, ca_pem = shared
        if CertificatesManager.has_client_cert_key_and_ca(cert_pem, key_pem, ca_pem):
            return

        CertificatesManager.persist_client_cert_key_and_ca(cert_pem, key_pem, ca_pem)

    def get_local_request_cert(self) -> str:
        """Return the cert to place in relation requests."""
        shared = self.get_shared_certificate()
        return '' if shared is None else shared[0]


class EtcdRequiresV1(Object):
    """EtcdRequires implementation for data interfaces version 1."""

    def __init__(
        self,
        charm,
        relation_name: str,
        cluster_id: str,
        shared_certificates: SharedClientCertificateManager,
    ) -> None:
        super().__init__(charm, 'requirer-etcd')
        self.charm = charm
        self.cluster_id = cluster_id
        self.shared_certificates = shared_certificates

        self.etcd_interface = ResourceRequirerEventHandler(
            self.charm,
            relation_name=relation_name,
            requests=self.client_requests(),
            response_model=ResourceProviderModel,
        )

        self.framework.observe(
            self.etcd_interface.on.endpoints_changed, self._on_endpoints_changed
        )
        self.framework.observe(charm.on[relation_name].relation_broken, self._on_relation_broken)
        self.framework.observe(self.etcd_interface.on.resource_created, self._on_resource_created)

    @property
    def etcd_relation(self) -> Relation | None:
        """Return the etcd relation if present."""
        relations = self.etcd_interface.relations
        return relations[0] if relations else None

    def _on_relation_broken(self, event: RelationBrokenEvent) -> None:
        """Remove the stored information about the etcd server."""
        EtcdCtl.cleanup()

    def _on_endpoints_changed(
        self, event: ResourceEndpointsChangedEvent[ResourceProviderModel]
    ) -> None:
        """Handle etcd client relation data changed event."""
        response = event.response
        logger.info('etcd endpoints changed: %s', response.endpoints)

        if not response.endpoints:
            logger.error('No etcd endpoints available')
            return

        self.shared_certificates.sync_to_local_files()
        cert_path, key_path = CertificatesManager.client_paths()
        EtcdCtl.write_env_file(
            endpoints=response.endpoints,
            client_cert_path=cert_path,
            client_key_path=key_path,
        )

    def _on_resource_created(self, event: ResourceCreatedEvent[ResourceProviderModel]) -> None:
        """Handle resource created event."""
        response = event.response

        if not response.tls_ca:
            logger.error('No etcd server CA chain available')
            return

        EtcdCtl.write_trusted_server_ca(tls_ca_pem=response.tls_ca)

        if response.endpoints:
            cert_path, key_path = CertificatesManager.client_paths()
            EtcdCtl.write_env_file(
                endpoints=response.endpoints, client_cert_path=cert_path, client_key_path=key_path
            )
        else:
            logger.error('No etcd endpoints available')

        self.shared_certificates.sync_to_local_files()

    def client_requests(self) -> list[RequirerCommonModel]:
        """Return the client requests for the etcd requirer interface."""
        return [
            RequirerCommonModel(
                resource=self.cluster_id,
                mtls_cert=self.shared_certificates.get_local_request_cert(),
            )
        ]
