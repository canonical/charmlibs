# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""This file defines the schemas for the provider and requirer sides.

It exposes two interfaces.schema_base.DataBagSchema subclasses called:
- ProviderSchema
- RequirerSchema

Examples:
    ProviderSchema:
        unit: <empty>
        app: {
            "decisions_address": "https://oauth2-proxy-k8s-0.oauth2-proxy-k8s.namespace.svc.cluster.local",
            "app_names": ["charmed-app", "other-charmed-app"],
            "headers": ["X-User", "X-Some-Header"]
        }

    RequirerSchema:
        unit: <empty>
        app: {
            "ingress_app_names": ["charmed-app", "other-charmed-app"]
        }
"""

from interface_tester.schema_base import DataBagSchema
from pydantic import BaseModel, Field


class ForwardAuthProvider(BaseModel):
    """ForwardAuthProvider model."""

    decisions_address: str = Field(description='The internal decisions endpoint address.')
    app_names: list[str] = Field(
        description=(
            'List of names of applications requesting to be protected '
            'by Identity and Access Proxy.'
        )
    )
    headers: list[str] | None = Field(
        description=(
            'List of headers to copy from the authentication server '
            'response and set on forwarded requests.'
        )
    )


class ForwardAuthRequirer(BaseModel):
    """ForwardAuthRequirer model."""

    ingress_app_names: list[str] = Field(
        description='List of names of applications that are related via ingress.'
    )


class ProviderSchema(DataBagSchema):
    """Provider schema for forward_auth."""

    app: ForwardAuthProvider


class RequirerSchema(DataBagSchema):
    """Requirer schema for forward_auth."""

    app: ForwardAuthRequirer
