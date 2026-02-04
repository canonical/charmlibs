# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for the SLO library."""

from typing import Any, Dict

import pytest
import yaml
from ops.charm import CharmBase
from ops.testing import Context, Relation, State
from pydantic import ValidationError

from charmlibs.interfaces.sloth import (
    SLOProvider,
    SLORequirer,
    SLOSpec,
    SLOValidationError,
)

# Test SLO specifications as YAML strings
VALID_SLO_CONFIG = """
version: prometheus/v1
service: test-service
labels:
  team: test-team
slos:
  - name: requests-availability
    objective: 99.9
    description: "99.9% of requests should succeed"
    sli:
      events:
        error_query: 'sum(rate(http_requests_total{status=~"5.."}[{{.window}}]))'
        total_query: 'sum(rate(http_requests_total[{{.window}}]))'
    alerting:
      name: TestServiceHighErrorRate
      labels:
        severity: critical
"""

VALID_SLO_CONFIG_2 = """
version: prometheus/v1
service: another-service
labels:
  team: another-team
slos:
  - name: latency
    objective: 95.0
    description: "95% of requests should be fast"
    sli:
      events:
        error_query: 'sum(rate(http_request_duration_seconds_bucket{le="0.5"}[{{.window}}]))'
        total_query: 'sum(rate(http_request_duration_seconds_count[{{.window}}]))'
"""

MULTI_SLO_CONFIG = """
version: prometheus/v1
service: test-service
slos:
  - name: requests-availability
    objective: 99.9
---
version: prometheus/v1
service: another-service
slos:
  - name: latency
    objective: 95.0
"""

# Test SLO specifications as dicts (for validation testing)
VALID_SLO_SPEC = {
    'version': 'prometheus/v1',
    'service': 'test-service',
    'labels': {'team': 'test-team'},
    'slos': [
        {
            'name': 'requests-availability',
            'objective': 99.9,
            'description': '99.9% of requests should succeed',
            'sli': {
                'events': {
                    'error_query': 'sum(rate(http_requests_total{status=~"5.."}[{{.window}}]))',
                    'total_query': 'sum(rate(http_requests_total[{{.window}}]))',
                }
            },
            'alerting': {
                'name': 'TestServiceHighErrorRate',
                'labels': {'severity': 'critical'},
            },
        }
    ],
}

VALID_SLO_SPEC_2 = {
    'version': 'prometheus/v1',
    'service': 'another-service',
    'labels': {'team': 'another-team'},
    'slos': [
        {
            'name': 'latency',
            'objective': 95.0,
            'description': '95% of requests should be fast',
            'sli': {
                'events': {
                    'error_query': (
                        'sum(rate(http_request_duration_seconds_bucket{le="0.5"}[{{.window}}]))'
                    ),
                    'total_query': 'sum(rate(http_request_duration_seconds_count[{{.window}}]))',
                }
            },
        }
    ],
}

INVALID_SLO_SPEC_NO_VERSION = {
    'service': 'test-service',
    'slos': [{'name': 'test', 'objective': 99.9}],
}

INVALID_SLO_SPEC_BAD_VERSION = {
    'version': 'invalid',
    'service': 'test-service',
    'slos': [{'name': 'test', 'objective': 99.9}],
}

INVALID_SLO_SPEC_EMPTY_SLOS: Dict[str, Any] = {
    'version': 'prometheus/v1',
    'service': 'test-service',
    'slos': [],
}


class ProviderCharm(CharmBase):
    """Test charm that provides SLOs."""

    def __init__(self, *args: Any):
        super().__init__(*args)
        self.slo_provider = SLOProvider(self, relation_name='sloth')


class RequirerCharm(CharmBase):
    """Test charm that requires SLOs."""

    def __init__(self, *args: Any):
        super().__init__(*args)
        self.slo_requirer = SLORequirer(self, relation_name='sloth')


class TestSLOSpec:
    """Tests for the SLOSpec pydantic model."""

    def test_valid_slo_spec(self):
        """Test that a valid SLO spec is accepted."""
        spec = SLOSpec(
            version=VALID_SLO_SPEC['version'],  # type: ignore[arg-type]
            service=VALID_SLO_SPEC['service'],  # type: ignore[arg-type]
            labels=VALID_SLO_SPEC.get('labels', {}),  # type: ignore[arg-type]
            slos=VALID_SLO_SPEC['slos'],  # type: ignore[arg-type]
        )
        assert spec.version == 'prometheus/v1'
        assert spec.service == 'test-service'
        assert len(spec.slos) == 1
        assert spec.labels == {'team': 'test-team'}

    def test_valid_slo_spec_without_labels(self):
        """Test that SLO spec without labels is accepted."""
        spec_no_labels: Dict[str, Any] = VALID_SLO_SPEC.copy()
        spec_no_labels.pop('labels')
        spec = SLOSpec(**spec_no_labels)
        assert spec.labels == {}

    def test_invalid_version_format(self):
        """Test that invalid version format is rejected."""
        invalid_spec: Dict[str, Any] = {
            'version': 'invalid',
            'service': 'test-service',
            'slos': [{'name': 'test', 'objective': 99.9}],
        }
        with pytest.raises(ValidationError) as exc_info:
            SLOSpec(**invalid_spec)
        assert 'Version must be in format' in str(exc_info.value)

    def test_missing_version(self):
        """Test that missing version is rejected."""
        invalid_spec: Dict[str, Any] = {
            'service': 'test-service',
            'slos': [{'name': 'test', 'objective': 99.9}],
        }
        with pytest.raises(ValidationError):
            SLOSpec(**invalid_spec)

    def test_empty_slos_list(self):
        """Test that empty SLOs list is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            SLOSpec(**INVALID_SLO_SPEC_EMPTY_SLOS)
        assert 'At least one SLO must be defined' in str(exc_info.value)

    def test_missing_required_fields(self):
        """Test that missing required fields are rejected."""
        incomplete_spec: Dict[str, Any] = {'version': 'prometheus/v1'}
        with pytest.raises(ValidationError):
            SLOSpec(**incomplete_spec)


class TestSLOProvider:
    """Tests for the SLOProvider class."""

    def test_provide_slos_with_relation(self):
        """Test providing SLO YAML when relation exists."""
        context = Context(
            ProviderCharm,
            meta={'name': 'provider', 'requires': {'sloth': {'interface': 'sloth'}}},
        )
        slo_relation = Relation('sloth')
        state = State(relations=[slo_relation], leader=True)  # Need leadership for app databag

        # Trigger start and provide SLO
        with context(context.on.start(), state) as mgr:
            charm = mgr.charm
            charm.slo_provider.provide_slos(VALID_SLO_CONFIG)
            state_out = mgr.run()

        # Check that SLO was set in relation data
        relation_out = state_out.get_relation(slo_relation.id)
        slo_yaml = relation_out.local_app_data.get('slo_spec')
        assert slo_yaml is not None
        slo_data = yaml.safe_load(slo_yaml)
        assert slo_data['service'] == 'test-service'
        assert slo_data['version'] == 'prometheus/v1'

    def test_provide_slos_without_relation(self):
        """Test providing SLO YAML when no relation exists."""
        context = Context(
            ProviderCharm,
            meta={'name': 'provider', 'requires': {'sloth': {'interface': 'sloth'}}},
        )
        state = State()

        # Should not raise error, just log warning
        with context(context.on.start(), state) as mgr:
            charm = mgr.charm
            charm.slo_provider.provide_slos(VALID_SLO_CONFIG)
            _ = mgr.run()

    def test_provide_slos_to_multiple_relations(self):
        """Test providing SLO YAML to multiple relations."""
        context = Context(
            ProviderCharm,
            meta={'name': 'provider', 'requires': {'sloth': {'interface': 'sloth'}}},
        )
        sloth_relation_1 = Relation('sloth')
        sloth_relation_2 = Relation('sloth')
        state = State(
            relations=[sloth_relation_1, sloth_relation_2], leader=True
        )  # Need leadership

        with context(context.on.start(), state) as mgr:
            charm = mgr.charm
            charm.slo_provider.provide_slos(VALID_SLO_CONFIG)
            state_out = mgr.run()

        # Both relations should have the SLO spec
        for rel in [sloth_relation_1, sloth_relation_2]:
            relation_out = state_out.get_relation(rel.id)
            slo_yaml = relation_out.local_app_data.get('slo_spec')
            assert slo_yaml is not None
            slo_data = yaml.safe_load(slo_yaml)
            assert slo_data['service'] == 'test-service'

    def test_provide_slos_with_multi_document_yaml(self):
        """Test providing multiple SLO specs as multi-document YAML."""
        context = Context(
            ProviderCharm,
            meta={'name': 'provider', 'requires': {'sloth': {'interface': 'sloth'}}},
        )
        slo_relation = Relation('sloth')
        state = State(relations=[slo_relation], leader=True)  # Need leadership

        with context(context.on.start(), state) as mgr:
            charm = mgr.charm
            charm.slo_provider.provide_slos(MULTI_SLO_CONFIG)
            state_out = mgr.run()

        # Check that both SLOs were set in relation data as multi-document YAML
        relation_out = state_out.get_relation(slo_relation.id)
        slo_yaml = relation_out.local_app_data.get('slo_spec')
        assert slo_yaml is not None

        # Parse multi-document YAML
        slo_docs = list(yaml.safe_load_all(slo_yaml))
        assert len(slo_docs) == 2

        services = {doc['service'] for doc in slo_docs}
        assert services == {'test-service', 'another-service'}

    def test_provide_slos_with_empty_string(self):
        """Test that providing empty string logs warning."""
        context = Context(
            ProviderCharm,
            meta={'name': 'provider', 'requires': {'sloth': {'interface': 'sloth'}}},
        )
        slo_relation = Relation('sloth')
        state = State(relations=[slo_relation])

        # Should not raise error, just log warning
        with context(context.on.start(), state) as mgr:
            charm = mgr.charm
            charm.slo_provider.provide_slos('')
            state_out = mgr.run()

        # Relation data should be empty
        relation_out = state_out.get_relation(slo_relation.id)
        slo_yaml = relation_out.local_app_data.get('slo_spec')
        assert slo_yaml is None

    def test_provide_slos_with_invalid_yaml(self):
        """Test that providing invalid YAML raises SLOValidationError."""
        context = Context(
            ProviderCharm,
            meta={'name': 'provider', 'requires': {'sloth': {'interface': 'sloth'}}},
        )
        slo_relation = Relation('sloth')
        state = State(relations=[slo_relation], leader=True)

        invalid_yaml = 'invalid: yaml: {{{['

        with context(context.on.start(), state) as mgr:
            charm = mgr.charm
            with pytest.raises(SLOValidationError) as exc_info:
                charm.slo_provider.provide_slos(invalid_yaml)
            assert 'Invalid YAML' in str(exc_info.value)
            _ = mgr.run()


class TestSLORequirer:
    """Tests for the SLORequirer class."""

    def test_get_slos_no_relations(self):
        """Test getting SLOs when no relations exist."""
        context = Context(
            RequirerCharm,
            meta={'name': 'requirer', 'provides': {'sloth': {'interface': 'sloth'}}},
        )
        state = State()

        with context(context.on.start(), state) as mgr:
            charm = mgr.charm
            slos = charm.slo_requirer.get_slos()
            _ = mgr.run()

        assert slos == []

    def test_get_slos_with_valid_data(self):
        """Test getting SLOs from relation with valid data."""
        slo_relation = Relation(
            'sloth',
            remote_app_name='provider',
            remote_app_data={'slo_spec': VALID_SLO_CONFIG},
        )

        context = Context(
            RequirerCharm,
            meta={'name': 'requirer', 'provides': {'sloth': {'interface': 'sloth'}}},
        )
        state = State(relations=[slo_relation])

        with context(context.on.start(), state) as mgr:
            charm = mgr.charm
            slos = charm.slo_requirer.get_slos()
            _ = mgr.run()

        assert len(slos) == 1
        assert slos[0]['service'] == 'test-service'
        assert slos[0]['version'] == 'prometheus/v1'

    def test_get_slos_from_multiple_units(self):
        """Test getting SLOs from multiple applications."""
        sloth_relation_1 = Relation(
            'sloth',
            remote_app_name='provider1',
            remote_app_data={'slo_spec': VALID_SLO_CONFIG},
        )
        sloth_relation_2 = Relation(
            'sloth',
            remote_app_name='provider2',
            remote_app_data={'slo_spec': VALID_SLO_CONFIG_2},
        )

        context = Context(
            RequirerCharm,
            meta={'name': 'requirer', 'provides': {'sloth': {'interface': 'sloth'}}},
        )
        state = State(relations=[sloth_relation_1, sloth_relation_2])

        with context(context.on.start(), state) as mgr:
            charm = mgr.charm
            slos = charm.slo_requirer.get_slos()
            _ = mgr.run()

        assert len(slos) == 2
        services = {slo['service'] for slo in slos}
        assert services == {'test-service', 'another-service'}

    def test_get_slos_from_unit_with_multi_document_yaml(self):
        """Test getting multiple SLOs from a single app (multi-document YAML)."""
        slo_relation = Relation(
            'sloth',
            remote_app_name='provider',
            remote_app_data={'slo_spec': MULTI_SLO_CONFIG},
        )

        context = Context(
            RequirerCharm,
            meta={'name': 'requirer', 'provides': {'sloth': {'interface': 'sloth'}}},
        )
        state = State(relations=[slo_relation])

        with context(context.on.start(), state) as mgr:
            charm = mgr.charm
            slos = charm.slo_requirer.get_slos()
            _ = mgr.run()

        # Should get both SLOs from the single app
        assert len(slos) == 2
        services = {slo['service'] for slo in slos}
        assert services == {'test-service', 'another-service'}

    def test_get_slos_from_multiple_relations(self):
        """Test getting SLOs from multiple relations."""
        sloth_relation_1 = Relation(
            'sloth',
            remote_app_name='provider1',
            remote_app_data={'slo_spec': VALID_SLO_CONFIG},
        )
        sloth_relation_2 = Relation(
            'sloth',
            remote_app_name='provider2',
            remote_app_data={'slo_spec': VALID_SLO_CONFIG_2},
        )

        context = Context(
            RequirerCharm,
            meta={'name': 'requirer', 'provides': {'sloth': {'interface': 'sloth'}}},
        )
        state = State(relations=[sloth_relation_1, sloth_relation_2])

        with context(context.on.start(), state) as mgr:
            charm = mgr.charm
            slos = charm.slo_requirer.get_slos()
            _ = mgr.run()

        assert len(slos) == 2
        services = {slo['service'] for slo in slos}
        assert services == {'test-service', 'another-service'}

    def test_get_slos_validates_and_skips_invalid_data(self):
        """Test that invalid SLO specs are skipped with validation."""
        invalid_yaml = yaml.safe_dump(INVALID_SLO_SPEC_BAD_VERSION)
        sloth_relation_1 = Relation(
            'sloth',
            remote_app_name='provider1',
            remote_app_data={'slo_spec': VALID_SLO_CONFIG},
        )
        sloth_relation_2 = Relation(
            'sloth',
            remote_app_name='provider2',
            remote_app_data={'slo_spec': invalid_yaml},
        )

        context = Context(
            RequirerCharm,
            meta={'name': 'requirer', 'provides': {'sloth': {'interface': 'sloth'}}},
        )
        state = State(relations=[sloth_relation_1, sloth_relation_2])

        with context(context.on.start(), state) as mgr:
            charm = mgr.charm
            slos = charm.slo_requirer.get_slos()
            _ = mgr.run()

        # Only valid SLO should be returned
        assert len(slos) == 1
        assert slos[0]['service'] == 'test-service'

    def test_get_slos_skips_malformed_yaml(self):
        """Test that malformed YAML is skipped."""
        sloth_relation_1 = Relation(
            'sloth',
            remote_app_name='provider1',
            remote_app_data={'slo_spec': VALID_SLO_CONFIG},
        )
        sloth_relation_2 = Relation(
            'sloth',
            remote_app_name='provider2',
            remote_app_data={'slo_spec': 'invalid: yaml: {{{'},
        )

        context = Context(
            RequirerCharm,
            meta={'name': 'requirer', 'provides': {'sloth': {'interface': 'sloth'}}},
        )
        state = State(relations=[sloth_relation_1, sloth_relation_2])

        with context(context.on.start(), state) as mgr:
            charm = mgr.charm
            slos = charm.slo_requirer.get_slos()
            _ = mgr.run()

        # Only valid SLO should be returned
        assert len(slos) == 1
        assert slos[0]['service'] == 'test-service'

    def test_get_slos_skips_empty_data(self):
        """Test that empty SLO data is skipped."""
        sloth_relation_1 = Relation(
            'sloth',
            remote_app_name='provider1',
            remote_app_data={'slo_spec': VALID_SLO_CONFIG},
        )
        sloth_relation_2 = Relation(
            'sloth',
            remote_app_name='provider2',
            remote_app_data={},  # No slo_spec key
        )
        sloth_relation_3 = Relation(
            'sloth',
            remote_app_name='provider3',
            remote_app_data={'slo_spec': ''},  # Empty string
        )

        context = Context(
            RequirerCharm,
            meta={'name': 'requirer', 'provides': {'sloth': {'interface': 'sloth'}}},
        )
        state = State(relations=[sloth_relation_1, sloth_relation_2, sloth_relation_3])

        with context(context.on.start(), state) as mgr:
            charm = mgr.charm
            slos = charm.slo_requirer.get_slos()
            _ = mgr.run()

        # Only valid SLO should be returned
        assert len(slos) == 1
        assert slos[0]['service'] == 'test-service'


class TestSLOIntegration:
    """Integration tests for provider and requirer working together."""

    def test_full_lifecycle(self):
        """Test full lifecycle: provide SLO → relation → requirer gets SLO."""
        # Provider provides SLO
        provider_context = Context(
            ProviderCharm,
            meta={'name': 'provider', 'requires': {'sloth': {'interface': 'sloth'}}},
        )
        provider_relation = Relation('sloth')
        provider_state = State(relations=[provider_relation], leader=True)  # Need leadership

        with provider_context(provider_context.on.start(), provider_state) as mgr:
            provider_charm = mgr.charm
            provider_charm.slo_provider.provide_slos(VALID_SLO_CONFIG)
            provider_state_out = mgr.run()

        # Get the relation data from provider
        provider_relation_out = provider_state_out.get_relation(provider_relation.id)
        slo_yaml = provider_relation_out.local_app_data.get('slo_spec')

        # Requirer receives SLO
        requirer_context = Context(
            RequirerCharm,
            meta={'name': 'requirer', 'provides': {'sloth': {'interface': 'sloth'}}},
        )
        requirer_relation = Relation(
            'sloth',
            remote_app_name='provider',
            remote_app_data={'slo_spec': slo_yaml or ''},
        )
        requirer_state = State(relations=[requirer_relation])

        with requirer_context(requirer_context.on.start(), requirer_state) as mgr:
            requirer_charm = mgr.charm
            slos = requirer_charm.slo_requirer.get_slos()
            _ = mgr.run()

        # Verify the SLO was successfully transmitted
        assert len(slos) == 1
        assert slos[0]['service'] == 'test-service'
        assert slos[0]['version'] == 'prometheus/v1'


class TestTopologyInjection:
    """Tests for Juju topology label injection."""

    def test_inject_topology_simple_metric(self):
        """Test injecting topology into a simple metric query."""
        from charmlibs.interfaces.sloth import inject_topology_labels

        query = 'sum(rate(http_requests_total[5m]))'
        topology: Dict[str, str] = {'juju_application': 'my-app'}

        result = inject_topology_labels(query, topology)

        assert 'juju_application="my-app"' in result
        assert 'http_requests_total{' in result

    def test_inject_topology_with_existing_labels(self):
        """Test injecting topology when labels already exist."""
        from charmlibs.interfaces.sloth import inject_topology_labels

        query = 'sum(rate(http_requests_total{status="5.."}[5m]))'
        topology: Dict[str, str] = {'juju_application': 'my-app'}

        result = inject_topology_labels(query, topology)

        assert 'juju_application="my-app"' in result
        assert 'status="5.."' in result
        # Both labels should be present
        assert result.count('{') >= 1

    def test_inject_topology_multiple_metrics(self):
        """Test injecting topology into query with multiple metrics."""
        from charmlibs.interfaces.sloth import inject_topology_labels

        query = 'sum(rate(metric1[5m])) - sum(rate(metric2[5m]))'
        topology: Dict[str, str] = {'juju_application': 'my-app'}

        result = inject_topology_labels(query, topology)

        # Should inject into both metrics
        assert result.count('juju_application="my-app"') == 2

    def test_inject_topology_empty_topology(self):
        """Test that empty topology doesn't modify query."""
        from charmlibs.interfaces.sloth import inject_topology_labels

        query = 'sum(rate(http_requests_total[5m]))'
        topology: Dict[str, str] = {}

        result = inject_topology_labels(query, topology)

        assert result == query

    def test_inject_topology_multiple_labels(self):
        """Test injecting multiple topology labels."""
        from charmlibs.interfaces.sloth import inject_topology_labels

        query = 'sum(rate(metric[5m]))'
        topology: Dict[str, str] = {
            'juju_application': 'my-app',
            'juju_model': 'my-model',
            'juju_unit': 'my-app/0',
        }

        result = inject_topology_labels(query, topology)

        assert 'juju_application="my-app"' in result
        assert 'juju_model="my-model"' in result
        assert 'juju_unit="my-app/0"' in result

    def test_provider_injects_topology_by_default(self):
        """Test that SLOProvider injects topology by default."""
        context = Context(
            ProviderCharm,
            meta={'name': 'provider', 'requires': {'sloth': {'interface': 'sloth'}}},
        )
        slo_relation = Relation('sloth')
        state = State(relations=[slo_relation], leader=True)  # Need leadership

        # SLO config without topology labels in queries
        slo_config = """
version: prometheus/v1
service: test-service
slos:
  - name: availability
    objective: 99.9
    description: "Test SLO"
    sli:
      events:
        error_query: 'sum(rate(metric[5m]))'
        total_query: 'sum(rate(metric[5m]))'
"""

        with context(context.on.start(), state) as mgr:
            charm = mgr.charm
            charm.slo_provider.provide_slos(slo_config)
            state_out = mgr.run()

        # Check that topology was injected
        relation_out = state_out.get_relation(slo_relation.id)
        slo_yaml = relation_out.local_app_data.get('slo_spec')
        assert slo_yaml is not None

        # Parse and check
        slo_data = yaml.safe_load(slo_yaml)
        error_query = slo_data['slos'][0]['sli']['events']['error_query']

        # Should have juju_application injected
        assert 'juju_application' in error_query

    def test_provider_can_disable_topology_injection(self):
        """Test that topology injection can be disabled."""

        # Create a charm with topology injection disabled
        class NoTopologyProviderCharm(CharmBase):
            def __init__(self, *args: Any):
                super().__init__(*args)
                self.slo_provider = SLOProvider(self, relation_name='sloth', inject_topology=False)

        context = Context(
            NoTopologyProviderCharm,
            meta={'name': 'provider', 'requires': {'sloth': {'interface': 'sloth'}}},
        )
        slo_relation = Relation('sloth')
        state = State(relations=[slo_relation], leader=True)  # Need leadership

        slo_config = """
version: prometheus/v1
service: test-service
slos:
  - name: availability
    objective: 99.9
    description: "Test SLO"
    sli:
      events:
        error_query: 'sum(rate(metric[5m]))'
        total_query: 'sum(rate(metric[5m]))'
"""

        with context(context.on.start(), state) as mgr:
            charm = mgr.charm
            charm.slo_provider.provide_slos(slo_config)
            state_out = mgr.run()

        # Check that topology was NOT injected
        relation_out = state_out.get_relation(slo_relation.id)
        slo_yaml = relation_out.local_app_data.get('slo_spec')
        assert slo_yaml is not None

        slo_data = yaml.safe_load(slo_yaml)
        error_query = slo_data['slos'][0]['sli']['events']['error_query']

        # Should NOT have juju_application
        assert 'juju_application' not in error_query
        assert error_query == 'sum(rate(metric[5m]))'

    def test_topology_injection_preserves_sloth_templates(self):
        """Test that topology injection preserves Sloth's {{.window}} template."""
        from charmlibs.interfaces.sloth import inject_topology_labels

        query = 'sum(rate(metric[{{.window}}]))'
        topology: Dict[str, str] = {'juju_application': 'my-app'}

        result = inject_topology_labels(query, topology)

        # Should preserve the {{.window}} template
        assert '{{.window}}' in result
        assert 'juju_application="my-app"' in result
