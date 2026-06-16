"""This file defines the schemas for the provider and requirer sides of the `tls-certificates` interface.

It exposes two interfaces.schema_base.DataBagSchema subclasses called:
- ProviderSchema
- RequirerSchema

Examples:
    ProviderSchema:
        unit: <empty>
        app: {
            "certificates": [
                {
                    "ca": "-----BEGIN CERTIFICATE----- ...",
                    "chain": [
                        "-----BEGIN CERTIFICATE----- ...",
                        "-----BEGIN CERTIFICATE----- ..."
                    ],
                    "certificate_signing_request": "-----BEGIN CERTIFICATE REQUEST----- ...",
                    "certificate": "-----BEGIN CERTIFICATE----- ..."
                }
            ],
            "request_errors": [
                {
                    "certificate_signing_request": "-----BEGIN CERTIFICATE REQUEST----- ...",
                    "error": {
                        "code": 101,
                        "name": "ip_not_allowed",
                        "message": "IP addresses are not allowed",
                        "reason": "ip in san",
                        "provider": "letsencrypt",
                        "endpoint": "https://acme-staging-v02.api.letsencrypt.org/directory"
                    }
                }
            ],
            "capabilities": {
                "supports_ip_sans": false,
                "supports_wildcard_dns": true,
                "supports_subdomain": false,
                "supports_ca_certificates": false,
                "allowed_domains": ["mydomain.com"],
                "provider_type": "acme"
            }
        }
    RequirerSchema:
        unit: {
            "certificate_signing_requests": [
                {
                    "certificate_signing_request": "-----BEGIN CERTIFICATE REQUEST----- ...",
                    "ca": true
                }
            ]
        }
        app:  <empty>
"""

from interface_tester.schema_base import DataBagSchema
from pydantic import BaseModel, Field, Json


class Certificate(BaseModel):
    """Certificate model."""

    ca: str = Field(description="The signing certificate authority.")
    certificate_signing_request: str = Field(description="Certificate signing request.")
    certificate: str = Field(description="Certificate.")
    chain: list[str] | None = Field(description="List of certificates in the chain.")
    recommended_expiry_notification_time: int | None = Field(
        description="Recommended expiry notification time in seconds."
    )
    revoked: bool | None = Field(description="Whether the certificate is revoked.")


class CertificateSigningRequest(BaseModel):
    """Certificate signing request model."""

    certificate_signing_request: str = Field(description="Certificate signing request.")
    ca: bool | None = Field(description="Whether the certificate is a CA.")


class ProviderError(BaseModel):
    """Provider error model."""

    code: int = Field(
        description="Numeric error code (e.g., 101, 102, 201). 1XX for CSR errors, 2XX for server errors, 9XX for other."
    )
    name: str = Field(
        description="Machine-readable error name (e.g., 'ip_not_allowed', 'domain_not_allowed', 'server_not_available')."
    )
    message: str = Field(description="Error message set by the provider charm.")
    reason: str | None = Field(
        default=None,
        description="Optional further explanation of the error, such as backend error messages.",
    )
    provider: str | None = Field(
        default=None,
        description="Optional field to specify the provider (e.g., charm name or backend like 'vault').",
    )
    endpoint: str | None = Field(
        default=None,
        description="Optional field to specify the server URL (e.g., 'https://acme-staging-v02.api.letsencrypt.org/directory').",
    )


class RequestError(BaseModel):
    """Request error model representing a failed certificate signing request."""

    certificate_signing_request: str = Field(
        description="Certificate signing request that failed."
    )
    error: ProviderError = Field(description="Error details.")


class Capabilities(BaseModel):
    """Provider capabilities model.

    Best-effort description of what the provider's certificate server supports. Every
    attribute is independently optional; an omitted attribute means "unspecified /
    unknown" and must not be treated as an assumed default.
    """

    supports_ip_sans: bool | None = Field(
        default=None, description="Whether IP addresses are accepted in SANs."
    )
    supports_wildcard_dns: bool | None = Field(
        default=None, description="Whether wildcard DNS entries are accepted."
    )
    supports_subdomain: bool | None = Field(
        default=None, description="Whether subdomain certificates can be issued."
    )
    supports_ca_certificates: bool | None = Field(
        default=None, description="Whether CA certificates can be issued."
    )
    allowed_domains: list[str] | None = Field(
        default=None, description="Optional list of allowed DNS domains."
    )
    provider_type: str | None = Field(
        default=None, description="Optional provider-type hint (e.g. 'acme', 'vault')."
    )


class ProviderApplicationData(BaseModel):
    """Provider application data model."""

    certificates: Json[list[Certificate]] = Field(description="List of certificates.")
    request_errors: Json[list[RequestError]] | None = Field(
        default=None, description="List of request errors."
    )
    capabilities: Json[Capabilities] | None = Field(
        default=None, description="Best-effort provider capabilities."
    )


class RequirerData(BaseModel):
    """Requirer data model.

    The same model is used for the unit and application data.
    """

    certificate_signing_requests: Json[list[CertificateSigningRequest]] = Field(
        description="List of certificate signing requests."
    )


class ProviderSchema(DataBagSchema):
    """Provider schema for TLS Certificates."""

    app: ProviderApplicationData  # pyright: ignore[reportGeneralTypeIssues,reportIncompatibleVariableOverride]


class RequirerSchema(DataBagSchema):
    """Requirer schema for TLS Certificates."""

    app: RequirerData  # pyright: ignore[reportGeneralTypeIssues,reportIncompatibleVariableOverride]
    unit: RequirerData  # pyright: ignore[reportGeneralTypeIssues,reportIncompatibleVariableOverride]
