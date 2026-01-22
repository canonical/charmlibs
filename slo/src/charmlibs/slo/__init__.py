# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""The charmlibs.slo package.

This package provides SLO (Service Level Objective) management for Juju charms,
enabling integration with the Sloth operator for generating Prometheus recording
and alerting rules.
"""

from ._version import __version__ as __version__
from .slo import (
    SLOProvider,
    SLORequirer,
    SLOSpec,
    inject_topology_labels,
)

__all__ = [
    'SLOProvider',
    'SLORequirer',
    'SLOSpec',
    'inject_topology_labels',
]
