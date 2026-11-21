"""This file defines the schemas for the provider and requirer sides of the kratos_external_idp interface.

It defines models `ProviderAppData` and `RequirerAppData`.

Examples:
    Provider:
        unit: <empty>
        app: {
                    "providers": [
                        {
                            "client_id": "client_id",
                            "client_secret": "cl1ent-s3cRet",
                            "secret_backend": "relation",
                            "scope": "profile email address phone",
                            "tenant_id": "4242424242424242",
                            "provider": "microsoft"
                        }
          ]
        }

    Requirer:
        unit: <empty>
        app: {
          "providers": [
                        {
                            "redirect_uri": "https://example.kratos.com/self-service/methods/oidc/callback/microsoft",
                            "provider_id": "microsoft"
                        }
          ]
        }
"""

import textwrap
from enum import Enum

from pydantic import AnyHttpUrl, BaseModel, Field, model_validator


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
    client_secret: str | None = None
    secret_backend: SecretBackend
    provider: Provider
    scope: str | None = None
    provider_id: str | None = None
    label: str | None = None
    jsonnet_mapper: str | None = Field(
        default=None,
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
    tenant_id: str | None = None
    private_key: str | None = None
    private_key_id: str | None = None
    team_id: str | None = None
    issuer_url: str | None = None

    @model_validator(mode="after")
    def validate_provider_fields(self) -> "ExternalIdpProvider":
        if self.provider != Provider.apple and not self.client_secret:
            raise ValueError(f"`client_secret` is required with provider {self.provider.value}")

        for fields, providers in (
            (("tenant_id",), (Provider.microsoft,)),
            (("private_key", "private_key_id", "team_id"), (Provider.apple,)),
            (("issuer_url",), (Provider.generic, Provider.auth0)),
        ):
            for field in fields:
                value = getattr(self, field)
                if value and self.provider not in providers:
                    raise ValueError(f"`{field}` not allowed with provider: {self.provider.value}")
                if not value and self.provider in providers:
                    raise ValueError(f"`{field}` is required with provider {self.provider.value}")
        return self


class ProviderAppData(BaseModel):
    providers: list[ExternalIdpProvider] = Field(
        examples=[
            [
                {
                    "client_id": "client_id",
                    "client_secret": "cl1ent-s3cRet",
                    "secret_backend": "relation",
                    "provider": "microsoft",
                    "scope": "profile email address phone",
                    "provider_id": "microsoft",
                    "label": "Microsoft",
                    "tenant_id": "4242424242424242",
                }
            ],
            [
                {
                    "client_id": "client_id",
                    "secret_backend": "relation",
                    "provider": "apple",
                    "scope": "profile email address phone",
                    "team_id": "team_id",
                    "private_key_id": "private_key_id",
                    "private_key": "private_key",
                }
            ],
            [
                {
                    "client_id": "client_id",
                    "client_secret": "cl1ent-s3cRet",
                    "secret_backend": "relation",
                    "provider": "generic",
                    "scope": "profile email address phone",
                    "issuer_url": "https://idp.example.com",
                }
            ],
            [
                {
                    "client_id": "client_id",
                    "client_secret": "cl1ent-s3cRet",
                    "secret_backend": "relation",
                    "provider": "auth0",
                    "scope": "profile email address phone",
                    "issuer_url": "https://example.auth0.com",
                }
            ],
            [
                {
                    "client_id": "client_id",
                    "client_secret": "cl1ent-s3cRet",
                    "secret_backend": "relation",
                    "provider": "google",
                    "scope": "profile email address phone",
                }
            ],
        ],
    )


class ExternalIdpRequirer(BaseModel):
    redirect_uri: AnyHttpUrl
    provider_id: str


class RequirerAppData(BaseModel):
    providers: list[ExternalIdpRequirer] = Field(
        examples=[
            [
                {
                    "redirect_uri": "https://example.kratos.com/self-service/methods/oidc/callback/microsoft",
                    "provider_id": "microsoft",
                }
            ]
        ],
    )


ProviderUnitData = None
RequirerUnitData = None
