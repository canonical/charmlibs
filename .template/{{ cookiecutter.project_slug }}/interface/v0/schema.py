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

"""Schema for the databags of the `{{ cookiecutter.project_slug }}` interface.

Each of `ProviderAppData`, `ProviderUnitData`, `RequirerAppData` and `RequirerUnitData`
is a Pydantic model for that databag, or `None` if nothing is written to it.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ProviderAppData(BaseModel):
    """The provider's application databag."""

    model_config = ConfigDict(json_schema_extra={'examples': [{'url': 'https://example.com'}]})

    url: str = Field(
        description='The URL that the requirer connects to.',
        examples=['https://example.com'],
    )


class RequirerAppData(BaseModel):
    """The requirer's application databag."""

    model_config = ConfigDict(json_schema_extra={'examples': [{'name': 'my-app'}]})

    name: str = Field(
        description='The name that the provider uses for the requirer.',
        examples=['my-app'],
    )


ProviderUnitData = None
RequirerUnitData = None
