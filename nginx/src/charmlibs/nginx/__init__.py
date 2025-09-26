# Copyright 2025 Canonical Ltd.
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

r"""Nginx sidecar container management abstractions.

The ``nginx`` charm library provides:

- :class:`Nginx`: A class to manage a nginx sidecar container.
  Includes regular nginx config file generation, tls configuration, and reload logic.
- :class:`NginxPrometheusExpoerter`: A class to manage a nginx-prometheus-exporter
  sidecar container.
- :class:`NginxConfig`: A nginx config file generation wrapper.
"""

from __future__ import annotations

from pathlib import Path

from .config import (
    NginxConfig,
    NginxLocationConfig,
    NginxLocationModifier,
    NginxUpstream,
)
from .nginx import Nginx
from .nginx_prometheus_exporter import NginxPrometheusExporter
from .tls_config_mgr import TLSConfig, TLSConfigManager

__all__ = (
    'Nginx',
    'NginxConfig',
    'NginxLocationConfig',
    'NginxLocationModifier',
    'NginxPrometheusExporter',
    'NginxUpstream',
    'TLSConfig',
    'TLSConfigManager',
)

__version__ = "0.0.1"
