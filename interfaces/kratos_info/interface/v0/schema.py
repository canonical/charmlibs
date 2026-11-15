"""This file defines the schemas for the provider and requirer sides of this relation interface."""

from pydantic import AnyHttpUrl, BaseModel, Field


class ProviderAppData(BaseModel):
    admin_endpoint: AnyHttpUrl = Field(description="Kratos admin URL.")
    public_endpoint: AnyHttpUrl = Field(description="Kratos public URL.")
    login_browser_endpoint: AnyHttpUrl = Field(
        description="The Kratos endpoint that initializes a browser-based user login flow."
    )
    sessions_endpoint: AnyHttpUrl = Field(
        description="The Kratos endpoint to check who the current session belongs to."
    )
    providers_configmap_name: str = Field(
        description="The name of the ConfigMap that contains the providers configuration."
    )
    schemas_configmap_name: str = Field(
        description="The name of the ConfigMap that contains the identity schemas configuration."
    )
    configmaps_namespace: str = Field(
        description="The namespace where the ConfigMaps are located."
    )
    mfa_enabled: bool = Field(description="Whether MFA is enabled.")
    oidc_webauthn_sequencing_enabled: bool = Field(
        description="Whether OIDC WebAuthn sequencing is enabled."
    )


ProviderUnitData = None
RequirerAppData = None
RequirerUnitData = None
