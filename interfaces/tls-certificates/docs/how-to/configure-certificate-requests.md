# Configure certificate requests

Each certificate your charm needs is described by a `CertificateRequestAttributes` object. This page covers two decisions you need to make when you build that object:

1. What values to put in the common name and Subject Alternative Name (SAN) fields.
2. How to let operators set those values at deploy time, rather than hard-coding them.

## Choose values for the common name and SANs

There is no single correct answer; the right values depend on what the certificate is used for. The guidance below covers the most common cases.

The appropriate SANs depend on the type of communication: internal unit-to-unit communication, or external client-to-server API communication.

### Internal communication

Different applications can use different mechanisms for one unit to access another. If units communicate with each other using IP addresses, then the IP address provided by Juju for connecting to that unit (accessible through the `ingress_address` attribute of the `Network` class in Ops) should be included in the certificate's IP SANs. For Kubernetes charms, it is often sufficient to include the Kubernetes Service DNS name (for example, `myapp-endpoints.myapp.svc.cluster.local`). If internal communication relies on externally resolvable names, the charm should allow those names to be configured and must provide a mechanism to resolve them to the corresponding IP addresses.

### External communication

When a unit is accessed directly by a client (either a user or another application), the certificate should cover all possible ways the API can be reached. If clients are expected to connect using an IP address, that IP should be included in the IP SANs. If they connect using a domain name, that name should be included in the DNS SANs. The domain name should be configurable in the requirer charm.

A better approach is to offload TLS termination to a load balancer or proxy, and have the API accessed from behind it. In that case, TLS termination occurs at the load-balancer level, and backend units do not need to manage individual certificates for external clients.

## Expose certificate attributes as charm config

For charms that serve **public HTTPS endpoints**, certificate attributes should be decided at deployment time by the charm's user, not hard-coded in the charm. Expose them as Juju configuration options and read them when building the `CertificateRequestAttributes`.

The recommended set of configuration options is:

- `common-name`
- `sans-dns`
- `organization`
- `organizational-unit`
- `email-address`
- `country-name`
- `state-or-province-name`
- `locality-name`

Read each option from the charm config and pass it to `CertificateRequestAttributes`:

```python
from typing import Optional

import ops
from charmlibs.interfaces.tls_certificates import (
    CertificateRequestAttributes,
    Mode,
    TLSCertificatesRequiresV4,
)


class TLSRequirerExample(ops.CharmBase):

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.certificates = TLSCertificatesRequiresV4(
            charm=self,
            relationship_name="certificates",
            certificate_requests=[self._get_certificate_request()],
            mode=Mode.UNIT,
        )

    def _get_certificate_request(self) -> CertificateRequestAttributes:
        return CertificateRequestAttributes(
            common_name=self._get_config_common_name(),
            sans_dns=self._get_sans_dns(),
            organization=self._get_config_organization(),
            organizational_unit=self._get_config_organizational_unit(),
            email_address=self._get_config_email_address(),
            country_name=self._get_config_country_name(),
            state_or_province_name=self._get_config_state_or_province_name(),
            locality_name=self._get_config_locality_name(),
        )

    def _get_config_common_name(self) -> str:
        return self.model.config["common-name"]

    def _get_sans_dns(self) -> Optional[list[str]]:
        return self.model.config.get("sans-dns")

    def _get_config_organization(self) -> str:
        return self.model.config["organization"]

    def _get_config_organizational_unit(self) -> str:
        return self.model.config["organizational-unit"]

    def _get_config_email_address(self) -> str:
        return self.model.config["email-address"]

    def _get_config_country_name(self) -> str:
        return self.model.config["country-name"]

    def _get_config_state_or_province_name(self) -> str:
        return self.model.config["state-or-province-name"]

    def _get_config_locality_name(self) -> str:
        return self.model.config["locality-name"]
```
