# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""SLO Provider and Requirer Library.

This library provides a way for charms to share SLO (Service Level Objective)
specifications with the Sloth charm, which will convert them into Prometheus
recording and alerting rules.

## Getting Started

### Provider Side (Charms providing SLO specs)

To provide SLO specifications to Sloth, use the `SLOProvider` class:

```python
from charmlibs.slo.slo import SLOProvider

class MyCharm(ops.CharmBase):
    def __init__(self, *args):
        super().__init__(*args)
        self.slo_provider = SLOProvider(self)

    def _provide_slos(self):
        # Provide SLO specs as a raw YAML string
        slo_config = '''
        version: prometheus/v1
        service: my-service
        labels:
          team: my-team
        slos:
          - name: requests-availability
            objective: 99.9
            description: "99.9% of requests should succeed"
            sli:
              events:
                error_query: 'sum(rate(http_requests_total{status=~"5.."}[{{.window}}]))'
                total_query: 'sum(rate(http_requests_total[{{.window}}]))'
            alerting:
              name: MyServiceHighErrorRate
              labels:
                severity: critical
        '''
        self.slo_provider.provide_slos(slo_config)

        # Multiple SLO specs (separated by YAML document separators)
        multi_slo_config = '''
        version: prometheus/v1
        service: my-service
        slos:
          - name: availability
            objective: 99.9
        ---
        version: prometheus/v1
        service: my-other-service
        slos:
          - name: latency
            objective: 99.5
        '''
        self.slo_provider.provide_slos(multi_slo_config)
```

### Requirer Side (Sloth charm)

The Sloth charm uses `SLORequirer` to collect SLO specifications.
Validation is performed on the requirer side:

```python
from charmlibs.slo.slo import SLORequirer

class SlothCharm(ops.CharmBase):
    def __init__(self, *args):
        super().__init__(*args)
        self.slo_requirer = SLORequirer(self)

    def _on_config_changed(self, event):
        # Get validated SLO specs from all related charms
        slos = self.slo_requirer.get_slos()
        # Process SLOs and generate rules
```

## Relation Data Format

SLO specifications are stored in the relation databag as YAML strings under the
`slo_spec` key. Each provider unit can provide one or more SLO specifications.

For a single service:
```yaml
slo_spec: |
  version: prometheus/v1
  service: my-service
  labels:
    team: my-team
  slos:
    - name: requests-availability
      objective: 99.9
      description: "99.9% of requests should succeed"
      sli:
        events:
          error_query: 'sum(rate(http_requests_total{status=~"5.."}[{{.window}}]))'
          total_query: 'sum(rate(http_requests_total[{{.window}}]))'
      alerting:
        name: MyServiceHighErrorRate
        labels:
          severity: critical
```

For multiple services (separated by YAML document separators):
```yaml
slo_spec: |
  version: prometheus/v1
  service: my-service
  slos:
    - name: requests-availability
      objective: 99.9
  ---
  version: prometheus/v1
  service: my-other-service
  slos:
    - name: requests-latency
      objective: 99.5
```
"""

import logging
import re
from typing import Any

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
    def replace_labels(match: re.Match[str]) -> str:
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
    query = re.sub(r'([a-zA-Z_:][a-zA-Z0-9_:]*)(\{[^}]*\})', replace_labels, query)

    # Second pass: inject into metrics with [time] but no labels yet
    def replace_time(match: re.Match[str]) -> str:
        metric_name = match.group(1)
        time_selector = match.group(2)

        # Check if metric_name already ends with } (labels were added in first pass)
        if not metric_name.endswith('}'):
            return f'{metric_name}{{{topology_labels}}}{time_selector}'

        return match.group(0)

    # Match metric_name[time]
    query = re.sub(r'([a-zA-Z_:][a-zA-Z0-9_:]*)(\[[^\]]*\])', replace_time, query)

    return query


class SLOSpec(BaseModel):
    """Pydantic model for SLO specification validation."""

    version: str = Field(description="Sloth spec version, e.g., 'prometheus/v1'")
    service: str = Field(description='Service name for the SLO')
    labels: dict[str, str] = Field(default_factory=dict, description='Labels for the SLO')
    slos: list[dict[str, Any]] = Field(description='List of SLO definitions')

    @field_validator('version')
    @classmethod
    def validate_version(cls, v: str) -> str:
        """Validate that version follows expected format."""
        if not v or '/' not in v:
            raise ValueError("Version must be in format 'prometheus/v1'")
        return v

    @field_validator('slos')
    @classmethod
    def validate_slos(cls, v: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
        self._relation_name = relation_name
        self._inject_topology = inject_topology

    def _get_topology_labels(self) -> dict[str, str]:
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

    def _inject_topology_into_slo(self, slo_spec: dict[str, Any]) -> dict[str, Any]:
        """Inject topology labels into SLO queries.

        Args:
            slo_spec: SLO specification dictionary

        Returns:
            SLO specification with topology labels injected into queries
        """
        if not self._inject_topology:
            return slo_spec

        topology_labels = self._get_topology_labels()

        # Deep copy to avoid modifying the original
        import copy

        slo_spec = copy.deepcopy(slo_spec)

        # Inject topology into each SLO's queries
        for slo in slo_spec.get('slos', []):
            if 'sli' in slo and 'events' in slo['sli']:
                events = slo['sli']['events']

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
        Multiple specs should be separated by YAML document separators (---).
        Validation is performed on the Sloth (requirer) side.

        Args:
            slo_config: Raw YAML string containing SLO specification(s) in Sloth format.
                Can contain multiple documents separated by ---.

        Example:
            ```python
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
            ---
            version: prometheus/v1
            service: my-other-service
            slos:
              - name: latency
                objective: 99.5
            '''
            self.slo_provider.provide_slos(slo_config)
            ```
        """
        relations = self._charm.model.relations.get(self._relation_name, [])
        if not relations:
            logger.warning('No %s relation found', self._relation_name)
            return

        if not slo_config:
            logger.warning('No SLO config provided')
            return

        # Parse the YAML config - it can contain multiple SLO documents (separated by ---)
        slo_specs = list(yaml.safe_load_all(slo_config))

        # Inject topology labels into queries if enabled
        if self._inject_topology:
            slo_specs = [self._inject_topology_into_slo(spec) for spec in slo_specs]

        # Merge multiple specs back into a single YAML with document separators
        slo_yaml_docs = [yaml.safe_dump(spec, default_flow_style=False) for spec in slo_specs]
        merged_yaml = '---\n'.join(slo_yaml_docs)

        for relation in relations:
            # Each unit provides its SLO spec in its own databag
            relation.data[self._charm.unit]['slo_spec'] = merged_yaml
            logger.info(
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
        self._relation_name = relation_name

    def get_slos(self) -> list[dict[str, Any]]:
        """Collect all SLO specifications from related charms.

        Returns:
            List of SLO specification dictionaries from all related units.
            Each unit may provide multiple SLO specs as a multi-document YAML.
            Only valid SLO specs are returned; invalid ones are logged and skipped.
        """
        slos: list[dict[str, Any]] = []
        relations = self._charm.model.relations.get(self._relation_name, [])

        for relation in relations:
            for unit in relation.units:
                try:
                    slo_yaml = relation.data[unit].get('slo_spec')
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
                                unit.name,
                            )
                        except ValidationError as e:
                            logger.error('Invalid SLO spec from %s: %s', unit.name, e)
                            continue

                except Exception as e:
                    logger.error('Failed to parse SLO spec from %s: %s', unit.name, e)
                    continue

        logger.info('Collected %d SLO specifications', len(slos))
        return slos
