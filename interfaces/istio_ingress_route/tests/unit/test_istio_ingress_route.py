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

"""Unit tests for the istio-ingress-route interface library."""

import ops
import pytest
from ops.charm import CharmBase
from scenario import Context, Relation, State

from charmlibs.interfaces.istio_ingress_route import (
    BackendRef,
    GRPCMethodMatch,
    GRPCRoute,
    GRPCRouteMatch,
    HTTPMethod,
    HTTPPathMatch,
    HTTPPathMatchType,
    HTTPRoute,
    HTTPRouteMatch,
    IstioIngressRouteConfig,
    IstioIngressRouteProvider,
    IstioIngressRouteRequirer,
    Listener,
    PathModifier,
    PathModifierType,
    ProtocolType,
    RequestRedirectFilter,
    RequestRedirectSpec,
    URLRewriteFilter,
    URLRewriteSpec,
    to_gateway_protocol,
)

PROVIDER_META = {
    'name': 'provider-charm',
    'provides': {'istio-ingress-route': {'interface': 'istio_ingress_route'}},
}

REQUIRER_META = {
    'name': 'requirer-charm',
    'requires': {'ingress': {'interface': 'istio_ingress_route'}},
}


def _sample_config() -> IstioIngressRouteConfig:
    http_listener = Listener(port=8080, protocol=ProtocolType.HTTP)
    grpc_listener = Listener(port=9090, protocol=ProtocolType.GRPC)
    return IstioIngressRouteConfig(
        model='my-model',
        listeners=[http_listener, grpc_listener],
        http_routes=[
            HTTPRoute(
                name='http-route',
                listener=http_listener,
                matches=[
                    HTTPRouteMatch(
                        path=HTTPPathMatch(type=HTTPPathMatchType.PathPrefix, value='/api'),
                        method=HTTPMethod.GET,
                    )
                ],
                backends=[BackendRef(service='my-app', port=8080)],
            ),
        ],
        grpc_routes=[
            GRPCRoute(
                name='grpc-route',
                listener=grpc_listener,
                matches=[
                    GRPCRouteMatch(
                        method=GRPCMethodMatch(service='myapp.MyService', method='GetData')
                    )
                ],
                backends=[BackendRef(service='my-app', port=9090)],
            ),
        ],
    )


SAMPLE_CONFIG = _sample_config()


class ProviderCharm(CharmBase):
    META = PROVIDER_META

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.ingress_route = IstioIngressRouteProvider(self)


class RequirerCharm(CharmBase):
    META = REQUIRER_META

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self.ingress = IstioIngressRouteRequirer(self, relation_name='ingress')
        self.framework.observe(self.on['ingress'].relation_joined, self._on_relation_joined)

    def _on_relation_joined(self, _: ops.EventBase) -> None:
        self.ingress.submit_config(SAMPLE_CONFIG)


# -------------------------------------------------------------------
# Config serialization round-trip
# -------------------------------------------------------------------


def test_config_roundtrip_preserves_all_fields():
    """Config survives JSON serialization through the databag."""
    parsed = IstioIngressRouteConfig.model_validate_json(SAMPLE_CONFIG.model_dump_json())
    assert parsed.model == 'my-model'
    assert len(parsed.listeners) == 2

    http_matches = parsed.http_routes[0].matches
    assert http_matches is not None
    assert http_matches[0].method is not None
    assert http_matches[0].method == HTTPMethod.GET

    grpc_matches = parsed.grpc_routes[0].matches
    assert grpc_matches is not None
    assert grpc_matches[0].method is not None
    assert grpc_matches[0].method.service == 'myapp.MyService'


def test_path_modifier_serializes_to_k8s_format():
    """PathModifier uses K8s-style keys (replacePrefixMatch) not the internal 'value' field."""
    pm = PathModifier(type=PathModifierType.ReplacePrefixMatch, value='/new')
    dumped = pm.model_dump()
    assert 'replacePrefixMatch' in dumped
    assert 'value' not in dumped


def test_path_modifier_deserializes_from_k8s_format():
    """PathModifier can be constructed from K8s-style dict."""
    pm = PathModifier.model_validate({'replaceFullPath': '/full'})
    assert pm.type == PathModifierType.ReplaceFullPath
    assert pm.value == '/full'


def test_url_rewrite_filter_roundtrip():
    """URLRewriteFilter survives serialization inside a config."""
    listener = Listener(port=80, protocol=ProtocolType.HTTP)
    config = IstioIngressRouteConfig(
        model='ns',
        listeners=[listener],
        http_routes=[
            HTTPRoute(
                name='r',
                listener=listener,
                backends=[BackendRef(service='svc', port=80)],
                filters=[
                    URLRewriteFilter(
                        urlRewrite=URLRewriteSpec(
                            path=PathModifier(
                                type=PathModifierType.ReplacePrefixMatch, value='/v2'
                            )
                        )
                    )
                ],
            )
        ],
    )
    parsed = IstioIngressRouteConfig.model_validate_json(config.model_dump_json())
    filters = parsed.http_routes[0].filters
    assert filters is not None
    f = filters[0]
    assert isinstance(f, URLRewriteFilter)
    assert f.urlRewrite.path is not None
    assert f.urlRewrite.path.value == '/v2'


def test_request_redirect_filter_roundtrip():
    """RequestRedirectFilter survives serialization inside a config."""
    listener = Listener(port=80, protocol=ProtocolType.HTTP)
    config = IstioIngressRouteConfig(
        model='ns',
        listeners=[listener],
        http_routes=[
            HTTPRoute(
                name='r',
                listener=listener,
                backends=[BackendRef(service='svc', port=80)],
                filters=[
                    RequestRedirectFilter(
                        requestRedirect=RequestRedirectSpec(scheme='https', statusCode=301)
                    )
                ],
            )
        ],
    )
    parsed = IstioIngressRouteConfig.model_validate_json(config.model_dump_json())
    filters = parsed.http_routes[0].filters
    assert filters is not None
    f = filters[0]
    assert isinstance(f, RequestRedirectFilter)
    assert f.requestRedirect.scheme == 'https'
    assert f.requestRedirect.statusCode == 301


def test_listener_name_derived_from_protocol_and_port():
    """Listener.name is protocol-port (used as Gateway listener name)."""
    assert Listener(port=8080, protocol=ProtocolType.HTTP).name == 'http-8080'
    assert Listener(port=9090, protocol=ProtocolType.GRPC).name == 'grpc-9090'


def test_to_gateway_protocol_maps_tls():
    """Both HTTP and GRPC map to HTTPS when TLS is enabled."""
    assert to_gateway_protocol(ProtocolType.HTTP, tls_enabled=False) == 'HTTP'
    assert to_gateway_protocol(ProtocolType.HTTP, tls_enabled=True) == 'HTTPS'
    assert to_gateway_protocol(ProtocolType.GRPC, tls_enabled=False) == 'HTTP'
    assert to_gateway_protocol(ProtocolType.GRPC, tls_enabled=True) == 'HTTPS'


# -------------------------------------------------------------------
# Provider
# -------------------------------------------------------------------


def test_provider_reads_config_from_requirer():
    """Provider can parse a valid config from the requirer's databag."""
    relation = Relation(
        endpoint='istio-ingress-route',
        interface='istio_ingress_route',
        remote_app_name='requirer-app',
        remote_app_data={'config': SAMPLE_CONFIG.model_dump_json()},
    )
    ctx = Context(ProviderCharm, meta=PROVIDER_META)
    with ctx(
        ctx.on.relation_changed(relation=relation),
        State(relations=[relation], leader=True),
    ) as mgr:
        ops_relation = mgr.charm.model.relations['istio-ingress-route'][0]
        config = mgr.charm.ingress_route.get_config(ops_relation)
        assert config is not None
        assert config.model == 'my-model'
        assert len(config.http_routes) == 1
        assert len(config.grpc_routes) == 1


def test_provider_returns_none_for_empty_databag():
    """Provider returns None when requirer hasn't sent config yet."""
    relation = Relation(
        endpoint='istio-ingress-route',
        interface='istio_ingress_route',
        remote_app_name='requirer-app',
        remote_app_data={},
    )
    ctx = Context(ProviderCharm, meta=PROVIDER_META)
    with ctx(
        ctx.on.relation_changed(relation=relation),
        State(relations=[relation], leader=True),
    ) as mgr:
        ops_relation = mgr.charm.model.relations['istio-ingress-route'][0]
        assert mgr.charm.ingress_route.get_config(ops_relation) is None


def test_provider_returns_none_for_malformed_config():
    """Provider gracefully returns None on invalid JSON."""
    relation = Relation(
        endpoint='istio-ingress-route',
        interface='istio_ingress_route',
        remote_app_name='requirer-app',
        remote_app_data={'config': 'not-valid-json'},
    )
    ctx = Context(ProviderCharm, meta=PROVIDER_META)
    with ctx(
        ctx.on.relation_changed(relation=relation),
        State(relations=[relation], leader=True),
    ) as mgr:
        ops_relation = mgr.charm.model.relations['istio-ingress-route'][0]
        assert mgr.charm.ingress_route.get_config(ops_relation) is None


def test_provider_publishes_ingress_data_on_ready():
    """Provider auto-publishes tls_enabled when requirer config is ready."""
    relation = Relation(
        endpoint='istio-ingress-route',
        interface='istio_ingress_route',
        remote_app_name='requirer-app',
        remote_app_data={'config': SAMPLE_CONFIG.model_dump_json()},
    )
    ctx = Context(ProviderCharm, meta=PROVIDER_META)
    state_out = ctx.run(
        ctx.on.relation_changed(relation=relation),
        State(relations=[relation], leader=True),
    )
    rel_out = state_out.get_relation(relation.id)
    assert 'tls_enabled' in rel_out.local_app_data


def test_provider_wipe_clears_databag():
    """wipe_ingress_data removes external_host and tls_enabled from the databag."""
    relation = Relation(
        endpoint='istio-ingress-route',
        interface='istio_ingress_route',
        remote_app_name='requirer-app',
        local_app_data={'external_host': 'gw.example.com', 'tls_enabled': 'True'},
        remote_app_data={'config': SAMPLE_CONFIG.model_dump_json()},
    )
    ctx = Context(ProviderCharm, meta=PROVIDER_META)
    with ctx(
        ctx.on.relation_changed(relation=relation),
        State(relations=[relation], leader=True),
    ) as mgr:
        ops_relation = mgr.charm.model.relations['istio-ingress-route'][0]
        mgr.charm.ingress_route.wipe_ingress_data(ops_relation)


# -------------------------------------------------------------------
# Requirer
# -------------------------------------------------------------------


def test_requirer_submits_config_to_databag():
    """Requirer writes serialized config to the app databag."""
    relation = Relation(endpoint='ingress', interface='istio_ingress_route')
    ctx = Context(RequirerCharm, meta=REQUIRER_META)
    state_out = ctx.run(
        ctx.on.relation_joined(relation=relation),
        State(relations=[relation], leader=True),
    )
    rel_out = state_out.get_relation(relation.id)
    parsed = IstioIngressRouteConfig.model_validate_json(rel_out.local_app_data['config'])
    assert parsed.model == 'my-model'


def test_requirer_submit_raises_when_not_leader():
    """Non-leader units cannot submit config."""
    from scenario.errors import UncaughtCharmError

    relation = Relation(endpoint='ingress', interface='istio_ingress_route')
    ctx = Context(RequirerCharm, meta=REQUIRER_META)
    with pytest.raises(UncaughtCharmError):
        ctx.run(
            ctx.on.relation_joined(relation=relation),
            State(relations=[relation], leader=False),
        )


def test_requirer_reads_external_host_from_provider():
    """Requirer exposes external_host and tls_enabled from provider databag."""
    relation = Relation(
        endpoint='ingress',
        interface='istio_ingress_route',
        remote_app_name='provider-app',
        remote_app_data={'external_host': 'gw.example.com', 'tls_enabled': 'True'},
    )
    ctx = Context(RequirerCharm, meta=REQUIRER_META)
    with ctx(
        ctx.on.relation_changed(relation=relation),
        State(relations=[relation], leader=True),
    ) as mgr:
        assert mgr.charm.ingress.external_host == 'gw.example.com'
        assert mgr.charm.ingress.tls_enabled is True


def test_requirer_defaults_when_no_provider_data():
    """Requirer returns empty host and tls=False when provider hasn't written yet."""
    relation = Relation(
        endpoint='ingress',
        interface='istio_ingress_route',
        remote_app_name='provider-app',
        remote_app_data={},
    )
    ctx = Context(RequirerCharm, meta=REQUIRER_META)
    with ctx(
        ctx.on.relation_changed(relation=relation),
        State(relations=[relation], leader=True),
    ) as mgr:
        assert mgr.charm.ingress.external_host == ''
        assert mgr.charm.ingress.tls_enabled is False


def test_requirer_is_ready_when_relation_exists():
    """Requirer.is_ready reflects whether a relation exists."""
    relation = Relation(endpoint='ingress', interface='istio_ingress_route')
    ctx = Context(RequirerCharm, meta=REQUIRER_META)
    with ctx(
        ctx.on.relation_changed(relation=relation),
        State(relations=[relation], leader=True),
    ) as mgr:
        assert mgr.charm.ingress.is_ready() is True


def test_requirer_not_ready_without_relation():
    """Requirer.is_ready is False when no relation exists."""
    ctx = Context(RequirerCharm, meta=REQUIRER_META)
    with ctx(ctx.on.start(), State(leader=True)) as mgr:
        assert mgr.charm.ingress.is_ready() is False
