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

"""The charmlibs.interfaces.slo package.

This package provides SLO (Service Level Objective) management for Juju charms,
enabling integration with the Sloth operator for generating Prometheus recording
and alerting rules.
"""

from ._version import __version__ as __version__
from .slo import (
    SLOError,
    SLOProvider,
    SLORequirer,
    SLOSpec,
    SLOValidationError,
    inject_topology_labels,
)

__all__ = [
    'SLOError',
    'SLOProvider',
    'SLORequirer',
    'SLOSpec',
    'SLOValidationError',
    'inject_topology_labels',
]
