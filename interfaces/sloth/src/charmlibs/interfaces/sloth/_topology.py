# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Helper utilities for topology label injection into Prometheus queries.

This module provides utilities for injecting Juju topology labels into
Prometheus queries, supporting the Sloth SLO specification format.
"""

import re
from re import Match

# Pre-compiled regex patterns for topology injection
_METRIC_WITH_LABELS = re.compile(r'([a-zA-Z_:][a-zA-Z0-9_:]*)(\{[^}]*\})')
_METRIC_WITH_TIME = re.compile(r'([a-zA-Z_:][a-zA-Z0-9_:]*)(\[[^\]]*\])')


def _replace_labels(match: Match[str], topology_labels: str) -> str:
    """Replace label selectors in a metric with topology-injected labels.

    Args:
        match: Regex match object containing metric name and labels
        topology_labels: Formatted topology labels string (e.g., 'juju_app="myapp"')

    Returns:
        Metric with topology labels injected
    """
    metric_name = match.group(1)
    labels_with_braces = match.group(2)

    # Strip the braces to get just the label content
    labels_content = labels_with_braces[1:-1] if len(labels_with_braces) > 2 else ''

    if labels_content:
        # Has existing labels, append topology
        new_labels = f'{{{labels_content},{topology_labels}}}'
    else:
        # Empty labels, add topology
        new_labels = f'{{{topology_labels}}}'

    return f'{metric_name}{new_labels}'


def _replace_time(match: Match[str], topology_labels: str) -> str:
    """Replace time selectors in a metric with topology-injected labels.

    Args:
        match: Regex match object containing metric name and time selector
        topology_labels: Formatted topology labels string (e.g., 'juju_app="myapp"')

    Returns:
        Metric with topology labels injected if not already present
    """
    metric_name = match.group(1)
    time_selector = match.group(2)

    # Check if metric_name already ends with } (labels were added in first pass)
    if not metric_name.endswith('}'):
        return f'{metric_name}{{{topology_labels}}}{time_selector}'

    return match.group(0)


def inject_topology_labels(query: str, topology: dict[str, str]) -> str:
    """Inject Juju topology labels into a Prometheus query.

    This function adds Juju topology labels (juju_application, juju_model, etc.)
    to all metric selectors in a PromQL query that don't already have them.

    Only metrics with explicit selectors (either {labels} or [time]) are modified.
    Function names like sum(), rate(), etc. are not modified.

    Args:
        query: The Prometheus query string
        topology: Dictionary of label names to values (e.g., {"juju_application": "my-app"})

    Returns:
        Query with topology labels injected

    Examples:
        >>> inject_topology_labels(
        ...     'sum(rate(metric[5m]))',
        ...     {"juju_application": "my-app"}
        ... )
        'sum(rate(metric{juju_application="my-app"}[5m]))'

        >>> inject_topology_labels(
        ...     'sum(rate(metric{existing="label"}[5m]))',
        ...     {"juju_application": "my-app"}
        ... )
        'sum(rate(metric{existing="label",juju_application="my-app"}[5m]))'
    """
    if not topology:
        return query

    # Build the label matcher string
    topology_labels = ','.join([f'{k}="{v}"' for k, v in sorted(topology.items())])

    # First pass: inject into metrics with {labels}
    query = _METRIC_WITH_LABELS.sub(lambda match: _replace_labels(match, topology_labels), query)

    # Second pass: inject into metrics with [time] but no labels yet
    query = _METRIC_WITH_TIME.sub(lambda match: _replace_time(match, topology_labels), query)

    return query
