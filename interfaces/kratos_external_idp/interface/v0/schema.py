"""This file defines the schemas for the provider and requirer sides of the kratos_external_idp interface.

It defines models `ProviderAppData` and `RequirerAppData`.

Examples:
    Provider:
        unit: <empty>
        app: {
          "providers":[
            "client_id": "client_id"
            "client_secret": "cl1ent-s3cRet"
            "secret_backend": "relation"
            "tenant_id": "4242424242424242"
            "provider": "microsoft"
          ]
        }

    Requirer:
        unit: <empty>
        app: {
          "providers": [
            "redirect_uri": "https://example.kratos.com/self-service/methods/oidc/callback/microsoft"
            "provider_id": "microsoft"
          ]
        }
"""

import textwrap
from enum import Enum

from pydantic import AnyHttpUrl, BaseModel, Field, field_validator


class Url(BaseModel):
    url: AnyHttpUrl


class Provider(Enum):
    microsoft = "microsoft"
    apple = "apple"
    generic = "generic"
    auth0 = "auth0"
    google = "google"
    facebook = "facebook"
    github = "github"
    gitlab = "gitlab"
    slack = "slack"
    spotify = "spotify"
    discord = "discord"
    twitch = "twitch"
    netid = "netid"
    yandex = "yandex"
    vk = "vk"
    dingtalk = "dingtalk"


class SecretBackend(Enum):
    relation = "relation"
    secret = "secret"
    vault = "vault"


class ExternalIdpProvider(BaseModel):
    client_id: str
    client_secret: str
    secret_backend: SecretBackend = "relation"
    provider: Provider
    scope: str | None
    provider_id: str | None
    jsonnet_mapper: str | None = Field(
        description=(
            "A jsonnet file that will be used to map the external claims to Kratos' claims. "
            "For more info see https://www.ory.sh/docs/kratos/reference/jsonnet."
        ),
        examples=[
            textwrap.dedent(
                """
        local claims = {
            email_verified: false,
        } + std.extVar('claims');

        {
            identity: {
            traits: {
                [if 'email' in claims && claims.email_verified then 'email' else null]: claims.email,
                [if 'name' in claims then 'name' else null]: claims.name,
                [if 'given_name' in claims then 'given_name' else null]: claims.given_name,
                [if 'family_name' in claims then 'family_name' else null]: claims.family_name,
            },
            },
        }
        """
            )
        ],
    )
    tenant_id: str | None
    private_key: str | None
    private_key_id: str | None
    team_id: str | None
    issuer_url: str | None

    @field_validator("tenant_id")
    def provider_must_be_microsoft(cls, v, info):
        if v and info.data.get("provider") != Provider.microsoft:
            raise ValueError("Provider must be microsoft to use key: `tenant_id`")
        elif not v and info.data.get("provider") == Provider.microsoft:
            raise ValueError("`tenant_id` is required with provider microsoft")
        return v

    @field_validator("private_key", "private_key_id", "team_id")
    def provider_must_be_apple(cls, v, info):
        if v and info.data.get("provider") != Provider.apple:
            raise ValueError(f"Provider must be apple to use key: `{info.field_name}`")
        elif not v and info.data.get("provider") == Provider.apple:
            raise ValueError(f"`{info.field_name}` is required with apple provider")
        return v

    @field_validator("issuer_url")
    def issuer_url_allowed(cls, v, info):
        provider = info.data.get("provider")
        if provider is None:  # `provider` itself failed validation.
            return v
        if v and provider not in (Provider.generic, Provider.auth0):
            raise ValueError(f"`issuer_url` not allowed with provider: {provider.value}")
        elif not v and provider in (Provider.generic, Provider.auth0):
            raise ValueError(f"`issuer_url` is required with provider {provider.value}")
        return v


class ProviderAppData(BaseModel):
    providers: list[ExternalIdpProvider] = Field(
        examples=[
            [
                {
                    "client_id": "client_id",
                    "client_secret": "cl1ent-s3cRet",
                    "secret_backend": "relation",
                    "provider": "microsoft",
                    "scope": "profile email",
                    "provider_id": "microsoft",
                    "jsonnet_mapper": None,
                    "tenant_id": "4242424242424242",
                    "private_key": None,
                    "private_key_id": None,
                    "team_id": None,
                    "issuer_url": None,
                }
            ]
        ],
    )


class ExternalIdpRequirer(BaseModel):
    redirect_uri: Url
    provider_id: str


class RequirerAppData(BaseModel):
    providers: list[ExternalIdpRequirer]


ProviderUnitData = None
RequirerUnitData = None
