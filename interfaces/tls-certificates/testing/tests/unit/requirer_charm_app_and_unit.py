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

"""Example requirer charm holding a certificate in each of the library's two scopes."""

import typing

import ops

from charmlibs.interfaces import tls_certificates

if typing.TYPE_CHECKING:
    _Scope: typing.TypeAlias = typing.Literal[
        tls_certificates.Mode.APP, tls_certificates.Mode.UNIT
    ]

META = {
    "name": "requirer",
    "requires": {"certificates": {"interface": "tls-certificates"}},
}
APP_REQUEST = tls_certificates.CertificateRequestAttributes(common_name="app.example.com")
UNIT_REQUEST = tls_certificates.CertificateRequestAttributes(common_name="unit.example.com")
# Annotated because the library's parameter is keyed on the two-value Literal, and dict keys
# are invariant -- an inferred dict[Mode, ...] isn't assignable to it.
REQUESTS_BY_MODE: "dict[_Scope, list[tls_certificates.CertificateRequestAttributes]]" = {
    tls_certificates.Mode.APP: [APP_REQUEST],
    tls_certificates.Mode.UNIT: [UNIT_REQUEST],
}


class AppAndUnitRequirerCharm(ops.CharmBase):
    """A requirer charm holding one application certificate and one unit certificate."""

    app_certs: list[tls_certificates.Certificate] | None = None
    unit_certs: list[tls_certificates.Certificate] | None = None

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.certificates = tls_certificates.TLSCertificatesRequiresV4(
            charm=self,
            relationship_name="certificates",
            mode=tls_certificates.Mode.APP_AND_UNIT,
            certificate_requests_by_mode=REQUESTS_BY_MODE,
        )
        framework.observe(self.on.update_status, self._reconcile)
        framework.observe(self.certificates.on.certificate_available, self._reconcile)

    def _reconcile(self, _event: ops.EventBase) -> None:
        unit_certs, _ = self.certificates.get_assigned_certificates(tls_certificates.Mode.UNIT)
        self.unit_certs = [c.certificate for c in unit_certs] or None
        if self.unit.is_leader():
            app_certs, _ = self.certificates.get_assigned_certificates(tls_certificates.Mode.APP)
            self.app_certs = [c.certificate for c in app_certs] or None
        if not self.unit_certs or (self.unit.is_leader() and not self.app_certs):
            self.unit.status = ops.BlockedStatus("TLS certificates not available")
            return
        self.unit.status = ops.ActiveStatus("TLS ready")
