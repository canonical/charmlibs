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

"""Example requirer charm for unit tests.

Collects the CA certificates it has been given, as a charm writing a trust store does, so
that a test can watch it receive what a ``RemoteProvider`` transfers. Its endpoint has no
``limit``, so it aggregates over every provider it is related to.
"""

from __future__ import annotations

import typing

import ops

from charmlibs.interfaces import certificate_transfer

META = {
    'name': 'requirer',
    'requires': {
        'certificates': {'interface': 'certificate_transfer'},
        # A second, unrelated endpoint, so that tests can check the rest of the state is
        # preserved. ops.testing rejects a relation whose endpoint isn't in the metadata.
        'other-endpoint': {'interface': 'something-else'},
    },
}


class RequirerCharm(ops.CharmBase):
    """A minimal requirer charm for testing the certificate_transfer interface."""

    certificates: set[str] | None = None

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.ct = certificate_transfer.CertificateTransferRequires(self, 'certificates')
        framework.observe(self.on.update_status, self._on_update_status)
        # certificate_set_updated is emitted on every relation-changed, whether or not the
        # set has actually changed -- it is level-triggered, not a change signal.
        framework.observe(self.ct.on.certificate_set_updated, self._on_certificate_set_updated)
        framework.observe(self.ct.on.certificates_removed, self._on_certificates_removed)

    def _on_certificate_set_updated(
        self, event: certificate_transfer.CertificatesAvailableEvent
    ) -> None:
        # The event carries what the library has just read for this relation, so use that
        # rather than reading again -- which is also what the library's own docstring does.
        # It matters on the v0 wire format, where get_all_certificates() takes the remote
        # unit out of ops' cached `relation.units`, leaving a second read in the same hook
        # with nothing to find.
        #
        # The cast is because the event shares one snapshot type with its relation ID, which
        # widens the attribute; what it carries is always the set of certificates.
        self._store(typing.cast('set[str]', event.certificates))

    def _on_certificates_removed(self, _: certificate_transfer.CertificatesRemovedEvent) -> None:
        self._store(self.ct.get_all_certificates())

    def _on_update_status(self, _: ops.EventBase) -> None:
        self._store(self.ct.get_all_certificates())

    def _store(self, certificates: set[str]) -> None:
        # imagine we write these to a trust store
        self.certificates = certificates or None
        if not certificates:
            self.unit.status = ops.BlockedStatus('waiting for CA certificates')
            return
        self.unit.status = ops.ActiveStatus(f'{len(certificates)} CA certificate(s)')
