# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.
"""This file defines the schemas for the provider and requirer sides.

Examples:
    Provider:
        unit: <empty>
        app: {
            "decisions_address": "https://oauth2-proxy-k8s-0.oauth2-proxy-k8s.namespace.svc.cluster.local",
            "app_names": ["charmed-app", "other-charmed-app"],
            "headers": ["X-User", "X-Some-Header"]
        }

    Requirer:
        unit: <empty>
        app: {
            "ingress_app_names": ["charmed-app", "other-charmed-app"]
        }
"""

from pydantic import BaseModel, Field


class ProviderAppData(BaseModel):
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


class RequirerAppData(BaseModel):
    """ForwardAuthRequirer model."""

    ingress_app_names: list[str] = Field(
        description='List of names of applications that are related via ingress.'
    )


ProviderUnitData = None
RequirerUnitData = None
