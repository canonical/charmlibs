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

from dpcharmlibs.interfaces import (
    RequirerCommonModel,
    ResourceCreatedEvent,
    ResourceEndpointsChangedEvent,
    ResourceProviderModel,
    ResourceRequirerEventHandler,
)
from ops import Relation
from ops.charm import (
    CharmBase,
    LeaderElectedEvent,
    RelationBrokenEvent,
    RelationChangedEvent,
    SecretChangedEvent,
)
from ops.framework import Object

from charmlibs.interfaces.tls_certificates import Certificate, TLSCertificatesError
from charmlibs.rollingops.common._exceptions import RollingOpsInvalidSecretContentError
from charmlibs.rollingops.etcd import _certificates as certificates
from charmlibs.rollingops.etcd import _etcdctl as etcdctl
from charmlibs.rollingops.etcd._models import SharedCertificate

logger = logging.getLogger(__name__)
CERT_SECRET_FIELD = 'rollingops-client-secret-id'  # noqa: S105
CERT_SECRET_LABEL = 'rollingops-client-cert'  # noqa: S105
CLIENT_CERT_FIELD = 'client-cert'
CLIENT_KEY_FIELD = 'client-key'
CLIENT_CA_FIELD = 'client-ca'


class SharedClientCertificateManager(Object):
    """Manage the shared rollingops client certificate via peer relation secret."""

    def __init__(self, charm: CharmBase, peer_relation_name: str) -> None:
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
        """Return the peer relation for this charm."""
        return self.model.get_relation(self.peer_relation_name)

    def _on_leader_elected(self, event: LeaderElectedEvent) -> None:
        """Handle the leader elected event.

        When this unit becomes the leader, it is responsible for generating
        and sharing the client certificate material with other units.
        """
        self.create_and_share_certificate()

    def _on_secret_changed(self, event: SecretChangedEvent) -> None:
        """Handle updates to secrets.

        This method is triggered when a secret changes. It ensures that
        the latest certificate material is synchronized to local files.
        """
        if event.secret.label == CERT_SECRET_LABEL:
            self.sync_to_local_files()

    def _on_peer_relation_changed(self, event: RelationChangedEvent) -> None:
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

        If the secret ID corresponding to the shared certificate already
        exists in the peer relation, it is not created again.
        """
        relation = self._peer_relation
        if relation is None or not self.model.unit.is_leader():
            return

        app_data = relation.data[self.model.app]

        if app_data.get(CERT_SECRET_FIELD):
            logger.info(
                'Shared certificate already exists in the databag. No new certificate is created.'
            )
            return

        common_name = f'rollingops-{self.model.uuid}-{self.model.app.name}'
        shared = certificates.generate(common_name)

        secret = self.model.app.add_secret(
            content={
                CLIENT_CERT_FIELD: shared.certificate.raw,
                CLIENT_KEY_FIELD: shared.key.raw,
                CLIENT_CA_FIELD: shared.ca.raw,
            },
            label=CERT_SECRET_LABEL,
        )

        app_data.update({CERT_SECRET_FIELD: secret.id})  # type: ignore[arg-type]
        logger.info('Shared certificate added to the databag.')

    def get_shared_certificate_from_peer_relation(self) -> SharedCertificate | None:
        """Return the client certificate, key and ca from peer app data.

        Returns:
            SharedCertificate or None if not yet available.

        Raises:
            RollingOpsInvalidSecretContent: if the content of the secret holding
                the certificates does not contain all the fields or they are empty.
        """
        if not (relation := self._peer_relation):
            logger.debug('Peer relation is not available yet.')
            return None

        if not (secret_id := relation.data[self.model.app].get(CERT_SECRET_FIELD)):
            logger.info('Shared certificate secret ID does not exist in the databag yet.')
            return None

        secret = self.model.get_secret(id=secret_id)
        content = secret.get_content(refresh=True)

        certificate = content.get(CLIENT_CERT_FIELD, '')
        key = content.get(CLIENT_KEY_FIELD, '')
        ca = content.get(CLIENT_CA_FIELD, '')

        if not certificate or not key or not ca:
            raise RollingOpsInvalidSecretContentError(
                'Invalid secret content: expected non-empty values for '
                f"'{CLIENT_CERT_FIELD}', '{CLIENT_KEY_FIELD}', and '{CLIENT_CA_FIELD}'. "
                'Missing or empty values are not allowed.'
            )

        try:
            return SharedCertificate.from_strings(
                certificate=certificate,
                key=key,
                ca=ca,
            )
        except (TLSCertificatesError, ValueError) as e:
            raise RollingOpsInvalidSecretContentError(
                'Invalid secret content: certificate material could not be parsed.'
            ) from e

    def sync_to_local_files(self) -> None:
        """Persist shared certificate locally if available."""
        shared = self.get_shared_certificate_from_peer_relation()
        if shared is None:
            logger.info('Shared rollingops etcd client certificate is not available yet.')
            return

        certificates.persist_client_cert_key_and_ca(shared)

    def get_local_request_cert(self) -> Certificate | None:
        """Return the cert to place in relation requests."""
        shared = self.get_shared_certificate_from_peer_relation()
        return None if shared is None else shared.certificate


class EtcdRequiresV1(Object):
    """EtcdRequires implementation for data interfaces version 1."""

    def __init__(
        self,
        charm: CharmBase,
        relation_name: str,
        cluster_id: str,
        shared_certificates: SharedClientCertificateManager,
    ) -> None:
        super().__init__(charm, f'requirer-{relation_name}')
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
        etcdctl.cleanup()

    def _on_endpoints_changed(
        self, event: ResourceEndpointsChangedEvent[ResourceProviderModel]
    ) -> None:
        """Handle updates to etcd endpoints from the provider.

        The method writes an environment configuration
        file used by etcdctl to connect securely to the cluster.

        If no endpoints are provided in the event, the update is skipped.
        """
        response = event.response

        if not response.endpoints:
            logger.error('Received a endpoints changed event but no etcd endpoints available.')
            return

        logger.info('etcd endpoints changed: %s', response.endpoints)

        etcdctl.write_config_file(
            endpoints=response.endpoints,
            client_cert_path=certificates.CLIENT_CERT_PATH,
            client_key_path=certificates.CLIENT_KEY_PATH,
        )

    def _on_resource_created(self, event: ResourceCreatedEvent[ResourceProviderModel]) -> None:
        """Handle provisioning of etcd connection resources.

        This method stores the trusted server CA locally and write the etcd client environment
        configuration file.
        """
        response = event.response

        if not response.tls_ca:
            logger.error(
                'Received a resource created event but no etcd server CA chain available.'
            )
            return

        etcdctl.write_trusted_server_ca(tls_ca_pem=response.tls_ca)

        if not response.endpoints:
            logger.error('Received a resource created event but no etcd endpoints available.')
            return

        etcdctl.write_config_file(
            endpoints=response.endpoints,
            client_cert_path=certificates.CLIENT_CERT_PATH,
            client_key_path=certificates.CLIENT_KEY_PATH,
        )

    def client_requests(self) -> list[RequirerCommonModel]:
        """Return the client requests for the etcd requirer interface."""
        cert = self.shared_certificates.get_local_request_cert()
        return [
            RequirerCommonModel(
                resource=self.cluster_id,
                mtls_cert=None if cert is None else cert.raw,
            )
        ]
