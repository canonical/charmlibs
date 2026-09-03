# Copyright 2023 Canonical
# See LICENSE file for licensing details.
"""This file defines the schema for the provider side of the smtp interface.

It defines one model, `ProviderAppData`.

Examples:
    Provider:
        unit: <empty>
        app: {"smtp":
                 {
                    "host": "example.com",
                    "port": "587",
                    "user": "example_user",
                    "password_id": "secret:123213123123123123123",
                    "auth_type": "plain",
                    "transport_security": "tls",
                    "domain": "example.com",
                }
             }
"""

from enum import Enum

from pydantic import BaseModel, Field


class TransportSecurity(str, Enum):
    """Represent the transport security values."""

    NONE = "none"
    STARTTLS = "starttls"
    TLS = "tls"


class AuthType(str, Enum):
    """Represent the auth type values."""

    NONE = "none"
    NOT_PROVIDED = "not_provided"
    PLAIN = "plain"


class ProviderAppData(BaseModel):
    host: str = Field(
        min_length=1,
        description="SMTP host.",
        title="Host",
        examples=["example.com"],
    )
    port: int = Field(
        ge=1,
        le=65536,
        description="SMTP port.",
        title="Port",
        examples=[25, 587, 465],
    )
    user: str | None = Field(
        description="SMTP user.",
        title="User",
        examples=["some_user"],
    )
    password: str | None = Field(
        description="SMTP password. Populated instead of password_id when secrets are not supported.",
        title="Password",
        examples=["somepasswd"],
    )
    password_id: str | None = Field(
        description="Juju secret ID for the SMTP password. Populated instead of password when secrets are supported.",
        title="Password ID",
        examples=["secret:123213123123123123123"],
    )
    auth_type: AuthType = Field(
        description="The type used to authenticate with the SMTP relay.",
        title="Auth type",
        examples=[AuthType.NONE],
    )
    transport_security: TransportSecurity = Field(
        description="The security protocol to use for the SMTP relay.",
        title="Transport security",
        examples=[TransportSecurity.NONE],
    )
    domain: str | None = Field(
        description="The MAIL FROM domain for the outgoing email.",
        title="Domain",
        examples=["example.com"],
    )


ProviderUnitData = None
RequirerAppData = None
RequirerUnitData = None
