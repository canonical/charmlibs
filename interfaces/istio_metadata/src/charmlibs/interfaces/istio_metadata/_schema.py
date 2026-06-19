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

"""Schema models for the istio_metadata interface.

This module is the source of truth for the databag wire format of the
``istio_metadata`` interface, and is symlinked from
``interface/v0/schema.py`` so it can be discovered as the canonical schema
on Charmhub.

Its only third-party dependency is Pydantic.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class IstioMetadataAppData(BaseModel):
    """Data model for the istio_metadata interface."""

    root_namespace: str = Field(
        description='The root namespace for the Istio installation.',
        examples=['istio-system'],
    )
