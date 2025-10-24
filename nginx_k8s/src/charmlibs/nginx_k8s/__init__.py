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

The ``nginx_k8s`` charm library provides:

- :class:`Nginx`: A class to manage a nginx sidecar container.
       Includes regular nginx config file generation, tls configuration, and reload logic.
- :class:`NginxPrometheusExporter`: A class to manage a nginx-prometheus-exporter
       sidecar container.
- :class:`NginxConfig`: A nginx config file generation wrapper.

"""

from __future__ import annotations

from ._config import (
    NginxConfig,
    NginxLocationConfig,
    NginxMapConfig,
    NginxTracingConfig,
    NginxUpstream,
)
from ._nginx import Nginx
from ._nginx_prometheus_exporter import NginxPrometheusExporter
from ._tls_config import TLSConfig, TLSConfigManager

__all__ = (
    'Nginx',
    'NginxConfig',
    'NginxLocationConfig',
    'NginxMapConfig',
    'NginxPrometheusExporter',
    'NginxTracingConfig',
    'NginxUpstream',
    'TLSConfig',
    'TLSConfigManager',
)

__version__ = '0.1.0'
