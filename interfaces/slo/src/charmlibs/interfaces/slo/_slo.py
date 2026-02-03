# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Internal implementation of the SLO Provider and Requirer library.

This module contains the core implementation classes for the SLO interface.
For user-facing documentation, see the package-level docstring in __init__.py.
"""

import copy
import logging
import re
from typing import Any, Dict, List, Match

import ops
import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator

try:
    from cosl import JujuTopology
except ImportError:
    # Fallback if cosl is not available
    JujuTopology = None

logger = logging.getLogger(__name__)

DEFAULT_RELATION_NAME = 'slos'

# Pre-compiled regex patterns for topology injection
_METRIC_WITH_LABELS = re.compile(r'([a-zA-Z_:][a-zA-Z0-9_:]*)(\{[^}]*\})')
_METRIC_WITH_TIME = re.compile(r'([a-zA-Z_:][a-zA-Z0-9_:]*)(\[[^\]]*\])')


class SLOError(Exception):
    """Base exception for SLO library errors."""


class SLOValidationError(SLOError):
    """Validation error for SLO specifications."""


def inject_topology_labels(query: str, topology: Dict[str, str]) -> str:
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
    def replace_labels(match: Match[str]) -> str:
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

    # Match metric_name{labels} - greedy match captures all content including {{.window}}
    query = _METRIC_WITH_LABELS.sub(replace_labels, query)

    # Second pass: inject into metrics with [time] but no labels yet
    def replace_time(match: Match[str]) -> str:
        metric_name = match.group(1)
        time_selector = match.group(2)

        # Check if metric_name already ends with } (labels were added in first pass)
        if not metric_name.endswith('}'):
            return f'{metric_name}{{{topology_labels}}}{time_selector}'

        return match.group(0)

    # Match metric_name[time]
    query = _METRIC_WITH_TIME.sub(replace_time, query)

    return query


class SLOSpec(BaseModel):
    """Pydantic model for SLO specification validation."""

    version: str = Field(description="Sloth spec version, e.g., 'prometheus/v1'")
    service: str = Field(description='Service name for the SLO')
    labels: Dict[str, str] = Field(default_factory=dict, description='Labels for the SLO')
    slos: List[Dict[str, Any]] = Field(description='List of SLO definitions')

    @field_validator('version')
    @classmethod
    def validate_version(cls, v: str) -> str:
        """Validate that version follows expected format."""
        if not v or '/' not in v:
            raise ValueError("Version must be in format 'prometheus/v1'")
        return v

    @field_validator('slos')
    @classmethod
    def validate_slos(cls, v: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Validate that at least one SLO is defined."""
        if not v:
            raise ValueError('At least one SLO must be defined')
        return v


class SLOProvider(ops.Object):
    """Provider side of the SLO relation.

    Charms should use this class to provide SLO specifications to Sloth.

    Args:
        charm: The charm instance.
        relation_name: Name of the relation (default: "slos").
        inject_topology: Whether to automatically inject Juju topology labels
            into Prometheus queries (default: True). When enabled, labels like
            juju_application, juju_model, etc. are added to metric selectors.
    """

    def __init__(
        self,
        charm: ops.CharmBase,
        relation_name: str = DEFAULT_RELATION_NAME,
        inject_topology: bool = True,
    ):
        super().__init__(charm, relation_name)
        self._charm = charm
        self.relation_name = relation_name
        self._inject_topology = inject_topology

    def _get_topology_labels(self) -> Dict[str, str]:
        """Get Juju topology labels for this charm.

        Returns:
            Dictionary of topology labels (juju_application, juju_model, etc.)
        """
        if JujuTopology is None:
            # Fallback to basic topology if cosl is not available
            return {'juju_application': self._charm.app.name}

        try:
            topology = JujuTopology.from_charm(self._charm)
            return topology.label_matcher_dict
        except Exception as e:
            logger.warning('Failed to get full topology, using app name only: %s', e)
            return {'juju_application': self._charm.app.name}

    def _inject_topology_into_slo(self, slo_spec: Dict[str, Any]) -> Dict[str, Any]:
        """Inject topology labels into SLO queries.

        This method performs a deep copy of the input SLO specification and
        injects Juju topology labels into all Prometheus queries found in the
        SLO definitions.

        Args:
            slo_spec: SLO specification dictionary

        Returns:
            New SLO specification with topology labels injected into queries
        """
        if not self._inject_topology:
            return slo_spec

        topology_labels = self._get_topology_labels()

        # Deep copy to avoid modifying the original
        slo_spec = copy.deepcopy(slo_spec)

        # Inject topology into each SLO's queries
        for slo in slo_spec.get('slos', []):
            sli = slo.get('sli')
            if not sli:
                continue

            events = sli.get('events')
            if not events:
                continue

            if 'error_query' in events:
                events['error_query'] = inject_topology_labels(
                    events['error_query'], topology_labels
                )

            if 'total_query' in events:
                events['total_query'] = inject_topology_labels(
                    events['total_query'], topology_labels
                )

        return slo_spec

    def provide_slos(self, slo_config: str) -> None:
        """Provide SLO specifications to Sloth as a raw YAML string.

        This method accepts a raw YAML string containing one or more SLO specifications.
        Multiple specs should be separated by YAML document separators (three dashes).
        The YAML is validated for parseability but full validation happens on the
        requirer side.

        Args:
            slo_config: Raw YAML string containing SLO specification(s) in Sloth format.
                Can contain multiple documents separated by three dashes.

        Raises:
            SLOValidationError: If the YAML cannot be parsed or is invalid.

        Example::

            slo_config = '''
            version: prometheus/v1
            service: my-service
            labels:
              team: my-team
            slos:
              - name: requests-availability
                objective: 99.9
                sli:
                  events:
                    error_query: 'sum(rate(http_requests_total{status=~"5.."}[{{.window}}]))'
                    total_query: 'sum(rate(http_requests_total[{{.window}}]))'
            '''
            self.slo_provider.provide_slos(slo_config)
        """
        relations = self._charm.model.relations.get(self.relation_name, [])
        if not relations:
            logger.debug('No %s relation found', self.relation_name)
            return

        if not slo_config:
            logger.debug('No SLO config provided')
            return

        # Parse the YAML config - it can contain multiple SLO documents (separated by ---)
        try:
            slo_specs = list(yaml.safe_load_all(slo_config))
        except yaml.YAMLError as e:
            logger.warning('Failed to parse SLO config as YAML: %s', e)
            raise SLOValidationError(f'Invalid YAML in slo_config: {e}') from e

        # Inject topology labels into queries if enabled
        if self._inject_topology:
            slo_specs = [self._inject_topology_into_slo(spec) for spec in slo_specs]

        # Merge multiple specs back into a single YAML with document separators
        slo_yaml_docs = [yaml.safe_dump(spec, default_flow_style=False) for spec in slo_specs]
        merged_yaml = '---\n'.join(slo_yaml_docs)

        for relation in relations:
            # Write SLO spec to app databag so it's shared across all units
            relation.data[self._charm.app]['slo_spec'] = merged_yaml
            logger.debug(
                'Provided SLO config to relation %s',
                relation.id,
            )


class SLORequirer(ops.Object):
    """Requirer side of the SLO relation.

    The Sloth charm uses this class to collect SLO specifications from
    related charms. Validation of SLO specs is performed on this side.

    Args:
        charm: The charm instance.
        relation_name: Name of the relation (default: "slos").
    """

    def __init__(
        self,
        charm: ops.CharmBase,
        relation_name: str = DEFAULT_RELATION_NAME,
    ):
        super().__init__(charm, relation_name)
        self._charm = charm
        self.relation_name = relation_name

    def get_slos(self) -> List[Dict[str, Any]]:
        """Collect all SLO specifications from related charms.

        Returns:
            List of SLO specification dictionaries from all related applications.
            Each application may provide multiple SLO specs as a multi-document YAML.
            Only valid SLO specs are returned; invalid ones are logged and skipped.
        """
        slos: List[Dict[str, Any]] = []
        relations = self._charm.model.relations.get(self.relation_name, [])

        for relation in relations:
            # Read from remote app databag instead of unit databags
            remote_app = relation.app
            if not remote_app:
                continue

            try:
                slo_yaml = relation.data[remote_app].get('slo_spec')
                if not slo_yaml:
                    continue

                # Parse as multi-document YAML (supports both single and multiple docs)
                slo_specs = list(yaml.safe_load_all(slo_yaml))

                # Validate and collect each SLO spec
                for slo_spec in slo_specs:
                    if not slo_spec:  # Skip empty documents
                        continue

                    try:
                        SLOSpec(**slo_spec)
                        slos.append(slo_spec)
                        logger.debug(
                            "Collected SLO spec for service '%s' from %s",
                            slo_spec['service'],
                            remote_app.name,
                        )
                    except ValidationError as e:
                        logger.warning('Invalid SLO spec from %s: %s', remote_app.name, e)
                        continue

            except Exception as e:
                logger.warning('Failed to parse SLO spec from %s: %s', remote_app.name, e)
                continue

        logger.info('Collected %d SLO specifications', len(slos))
        return slos
