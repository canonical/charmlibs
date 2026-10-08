"""This file defines the schemas for the provider and requirer sides of the auth_proxy interface.

Examples:
    Requirer:
        unit: <empty>
        app: {
          "providers": [
            "protected_urls": ["https://example.com", "https://other-example.com"],
            "allowed_endpoints": ["about/app", "welcome"],
            "headers": ["X-User", "X-Some-Header"]
          ]
        }

    Provider:
        unit: <empty>
        app: <empty>
"""

from pydantic import AnyHttpUrl, BaseModel, Field


class RequirerAppData(BaseModel):
    protected_urls: list[AnyHttpUrl] = Field(
        description="List of urls to be protected by Identity and Access Proxy."
    )
    allowed_endpoints: list[str] | None = Field(
        description="List of endpoints that are allowed to bypass authentication."
    )
    headers: list[str] | None = Field(
        description="List of headers to be returned upon a successful authentication."
    )


ProviderAppData = None
ProviderUnitData = None
RequirerUnitData = None
