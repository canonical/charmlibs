# Copyright 2025 Canonical
# See LICENSE file for licensing details.

import logging
import tempfile
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock, patch

import ops
import pytest
from ops import pebble, testing

from charmlibs.nginx_k8s import (
    Nginx,
    NginxConfig,
    NginxLocationConfig,
    NginxMapConfig,
    NginxPrometheusExporter,
    NginxTracingConfig,
    NginxUpstream,
)

sample_dns_ip = '198.18.0.0'

logger = logging.getLogger(__name__)


@pytest.fixture
def certificate_mounts(tmp_path):
    mounts = {}

    for path, tmpname in (
        (Nginx.KEY_PATH, 'key'),
        (Nginx.CERT_PATH, 'cert'),
        (Nginx.CA_CERT_PATH, 'cacert'),
    ):
        temp_file = tmp_path / tmpname
        temp_file.write_text('foo')
        mounts[path] = testing.Mount(location=path, source=str(temp_file))

    return mounts


def test_certs_on_disk(certificate_mounts: dict, ctx: testing.Context, nginx_container):
    # GIVEN any charm with a container

    # WHEN we process any event
    with ctx(
        ctx.on.update_status(),
        state=testing.State(containers={replace(nginx_container, mounts=certificate_mounts)}),
    ) as mgr:
        charm = mgr.charm
        nginx = Nginx(charm.unit.get_container(nginx_container.name))

        # THEN the certs exist on disk
        assert nginx.are_certificates_on_disk


def test_certs_deleted(certificate_mounts: dict, ctx: testing.Context, nginx_container):
    # Test deleting the certificates.

    # GIVEN any charm with a container

    # WHEN we process any event
    with ctx(
        ctx.on.update_status(),
        state=testing.State(
            containers={
                replace(nginx_container, mounts=certificate_mounts),
            }
        ),
    ) as mgr:
        charm = mgr.charm
        nginx = Nginx(charm.unit.get_container(nginx_container.name))

        # AND when we call delete_certificates
        nginx._delete_certificates()

        # THEN the certs get deleted from disk
        assert not nginx.are_certificates_on_disk


def test_has_config_changed(ctx: testing.Context, nginx_container):
    # Test changing the nginx config and catching the change.

    # GIVEN any charm with a container and a nginx config file
    with tempfile.NamedTemporaryFile(delete=False, mode='w+') as test_config:
        test_config.write('foo')

    # WHEN we process any event
    with ctx(
        ctx.on.update_status(),
        state=testing.State(
            containers={
                replace(
                    nginx_container,
                    mounts={
                        'config': testing.Mount(
                            location=Nginx.NGINX_CONFIG, source=test_config.name
                        )
                    },
                )
            },
        ),
    ) as mgr:
        charm = mgr.charm
        nginx = Nginx(charm.unit.get_container(nginx_container.name))

        # AND a unique config is added
        new_config = 'bar'

        # THEN the _has_config_changed method correctly determines that foo != bar
        assert nginx._has_config_changed(new_config)

    test_config.close()


@pytest.mark.parametrize(
    'container_name, config_generator, args, expected_layer',
    (
        (
            'nginx',
            Nginx,
            ('foo',),
            {
                'summary': 'Nginx layer.',
                'description': 'Pebble config layer for Nginx.',
                'services': {
                    'nginx': {
                        'summary': 'nginx',
                        'startup': 'enabled',
                        'override': 'replace',
                        'command': "nginx -g 'daemon off;'",
                    }
                },
            },
        ),
        (
            'nginx-pexp',
            NginxPrometheusExporter,
            (),
            {
                'summary': 'Nginx prometheus exporter layer.',
                'description': 'Pebble config layer for the Nginx Prometheus exporter service.',
                'services': {
                    'nginx-prometheus-exporter': {
                        'summary': 'Nginx prometheus exporter service.',
                        'startup': 'enabled',
                        'override': 'replace',
                        'command': 'nginx-prometheus-exporter '
                        '--no-nginx.ssl-verify '
                        '--web.listen-address=:9113 '
                        '--nginx.scrape-uri=https://127.0.0.1:8080/status',
                    }
                },
            },
        ),
    ),
)
def test_nginx_pebble_plan(
    ctx, container_name, config_generator, args, expected_layer, null_state
):
    # GIVEN any charm with a container
    # WHEN we process any event
    with ctx(
        ctx.on.update_status(),
        state=null_state,
    ) as mgr:
        config_generator(mgr.charm.unit.get_container(container_name)).reconcile(*args)
        state_out = mgr.run()
    # THEN the generated pebble layer is as expected
    assert (
        state_out.get_container(container_name).layers[config_generator._layer_name]
        == expected_layer
    )


@pytest.mark.parametrize('tls', (False, True))
def test_nginx_pebble_checks(tls, nginx_container):
    check_endpoint = f'http{"s" if tls else ""}://1.2.3.4/health'
    expected_partial_service_dict = {'nginx-up': 'restart'}

    # GIVEN any charm with a container
    ctx = testing.Context(
        ops.CharmBase, meta={'name': 'foo', 'containers': {'nginx': {'type': 'oci-image'}}}
    )

    # WHEN we process any event
    with ctx(
        ctx.on.update_status(),
        state=testing.State(
            containers={
                nginx_container,
            },
        ),
    ) as mgr:
        charm = mgr.charm
        # AND we pass a liveness check endpoint
        nginx = Nginx(
            charm.unit.get_container(nginx_container.name),
            liveness_check_endpoint_getter=lambda _: check_endpoint,
        )
        nginx.reconcile('mock nginx config')
        # THEN the generated pebble layer has the expected pebble check
        out = mgr.run()
        layer = out.get_container('nginx').layers['nginx']
        actual_services = layer.services
        actual_checks = layer.checks
        assert actual_checks['nginx-up'].http == {'url': check_endpoint}
        # AND the pebble layer service has a restart on check-failure
        assert actual_services['nginx'].on_check_failure == expected_partial_service_dict


@contextmanager
def mock_resolv_conf(contents: str):
    with tempfile.NamedTemporaryFile() as tf:
        Path(tf.name).write_text(contents)
        with patch('charmlibs.nginx_k8s._config.RESOLV_CONF_PATH', tf.name):
            yield


@pytest.mark.parametrize(
    'mock_contents, expected_dns_ip',
    (
        (f'foo bar\nnameserver {sample_dns_ip}', sample_dns_ip),
        (f'nameserver {sample_dns_ip}\n foo bar baz', sample_dns_ip),
        (
            f'foo bar\nfoo bar\nnameserver {sample_dns_ip}\nnameserver 198.18.0.1',
            sample_dns_ip,
        ),
    ),
)
def test_dns_ip_addr_getter(mock_contents, expected_dns_ip):
    with mock_resolv_conf(mock_contents):
        assert NginxConfig._get_dns_ip_address() == expected_dns_ip


def test_dns_ip_addr_fail():
    with pytest.raises(RuntimeError):
        with mock_resolv_conf('foo bar'):
            NginxConfig._get_dns_ip_address()


@pytest.mark.parametrize('workload', ('tempo', 'mimir', 'loki'))
@pytest.mark.parametrize('tls', (False, True))
def test_generate_nginx_config(tls, workload):
    upstream_configs, server_ports_to_locations = _get_nginx_config_params(workload)
    # loki & mimir changes the port from 8080 to 443 when TLS is enabled
    if workload in ('loki', 'mimir') and tls:
        server_ports_to_locations[443] = server_ports_to_locations.pop(8080)

    addrs_by_role = {
        role: {'worker-address'}
        for role in (upstream.address_lookup_key for upstream in upstream_configs)
    }
    with mock_resolv_conf(f'foo bar\nnameserver {sample_dns_ip}'):
        nginx = NginxConfig(
            'localhost',
            upstream_configs=upstream_configs,
            server_ports_to_locations=server_ports_to_locations,
            enable_health_check=workload in ('mimir', 'loki'),
            enable_status_page=workload in ('mimir', 'loki'),
        )
        generated_config = nginx.get_config(addrs_by_role, tls)
        sample_config_path = (
            Path(__file__).parent
            / 'resources'
            / f'sample_{workload}_nginx_conf{"_tls" if tls else ""}.txt'
        )
        assert generated_config == sample_config_path.read_text()


def test_generate_nginx_config_with_root_path():
    upstream_configs, server_ports_to_locations = _get_nginx_config_params('tempo')

    addrs_by_role = {
        role: {'worker-address'}
        for role in (upstream.address_lookup_key for upstream in upstream_configs)
    }
    with mock_resolv_conf(f'foo bar\nnameserver {sample_dns_ip}'):
        nginx = NginxConfig(
            'localhost',
            upstream_configs=upstream_configs,
            server_ports_to_locations=server_ports_to_locations,
            enable_health_check=False,
            enable_status_page=False,
        )
        generated_config = nginx.get_config(addrs_by_role, False, root_path='/dist')
        sample_config_path = (
            Path(__file__).parent / 'resources' / 'sample_tempo_nginx_conf_root_path.txt'
        )
        assert sample_config_path.read_text() == generated_config


def test_generate_litmus_config_with_rewrite():
    upstream_configs, server_ports_to_locations = _get_nginx_config_params('litmus')

    addrs_by_role = {
        'auth': ['worker-address'],
        'backend': ['worker-address'],
    }
    with mock_resolv_conf(f'foo bar\nnameserver {sample_dns_ip}'):
        nginx = NginxConfig(
            'localhost',
            upstream_configs=upstream_configs,
            server_ports_to_locations=server_ports_to_locations,
            enable_health_check=False,
            enable_status_page=False,
        )
        generated_config = nginx.get_config(addrs_by_role, False)
        sample_config_path = (
            Path(__file__).parent / 'resources' / 'sample_litmus_conf_with_rewrite.txt'
        )
        assert sample_config_path.read_text() == generated_config


def test_generate_nginx_config_with_extra_location_directives():
    upstream_configs, server_ports_to_locations = _get_nginx_config_params('litmus_ssl')

    addrs_by_role = {
        role: {'worker-address'}
        for role in (upstream.address_lookup_key for upstream in upstream_configs)
    }
    with mock_resolv_conf(f'foo bar\nnameserver {sample_dns_ip}'):
        nginx = NginxConfig(
            'localhost',
            upstream_configs=upstream_configs,
            server_ports_to_locations=server_ports_to_locations,
            enable_health_check=False,
            enable_status_page=False,
        )
        generated_config = nginx.get_config(addrs_by_role, False, root_path='/dist')
        sample_config_path = Path(__file__).parent / 'resources' / 'sample_litmus_ssl_conf.txt'
        assert sample_config_path.read_text() == generated_config


def test_location_skipped_if_no_matching_upstream():
    upstream_configs, server_ports_to_locations = (
        [],
        _get_server_ports_to_locations('litmus_ssl'),
    )

    addrs_by_role = {
        role: {'worker-address'}
        for role in (upstream.address_lookup_key for upstream in upstream_configs)
    }
    with mock_resolv_conf(f'foo bar\nnameserver {sample_dns_ip}'):
        nginx = NginxConfig(
            'localhost',
            upstream_configs=upstream_configs,
            server_ports_to_locations=server_ports_to_locations,
            enable_health_check=False,
            enable_status_page=False,
        )
        generated_config = nginx.get_config(addrs_by_role, False, root_path='/dist')
        sample_config_path = (
            Path(__file__).parent / 'resources' / 'sample_litmus_missing_upstreams_conf.txt'
        )
        assert sample_config_path.read_text() == generated_config


def test_generate_nginx_config_with_tracing_enabled():
    mock_tracing_config = NginxTracingConfig(
        endpoint='endpoint:4317',
        service_name='nginx-workload',
        resource_attributes={
            'juju_application': 'nginx',
            'juju_model': 'test',
            'juju_unit': 'nginx/0',
        },
    )
    upstream_configs, server_ports_to_locations = _get_nginx_config_params('litmus')

    addrs_by_role = {
        'auth': ['worker-address'],
        'backend': ['worker-address'],
    }
    with mock_resolv_conf(f'foo bar\nnameserver {sample_dns_ip}'):
        nginx = NginxConfig(
            'localhost',
            upstream_configs=upstream_configs,
            server_ports_to_locations=server_ports_to_locations,
            enable_health_check=False,
            enable_status_page=False,
        )
        generated_config = nginx.get_config(
            addrs_by_role, False, tracing_config=mock_tracing_config
        )
        sample_config_path = (
            Path(__file__).parent / 'resources' / 'sample_litmus_conf_with_tracing.txt'
        )
        assert sample_config_path.read_text() == generated_config


def test_generate_nginx_config_with_extra_http_variables():
    upstream_configs, server_ports_to_locations = _get_nginx_config_params('litmus')

    addrs_by_role = {
        'auth': ['worker-address'],
        'backend': ['worker-address'],
    }
    with mock_resolv_conf(f'foo bar\nnameserver {sample_dns_ip}'):
        nginx = NginxConfig(
            'localhost',
            upstream_configs=upstream_configs,
            server_ports_to_locations=server_ports_to_locations,
            map_configs=[
                NginxMapConfig(
                    source_variable='$http_upgrade',
                    target_variable='$connection_upgrade',
                    value_mappings={
                        'default': ['upgrade'],
                        '': ['close'],
                    },
                )
            ],
            enable_health_check=False,
            enable_status_page=False,
        )
        generated_config = nginx.get_config(addrs_by_role, False)
        sample_config_path = (
            Path(__file__).parent
            / 'resources'
            / 'sample_litmus_conf_with_extra_http_variables.txt'
        )
        assert sample_config_path.read_text() == generated_config


def test_exception_raised_if_nginx_module_missing(caplog):
    # GIVEN an instance of Nginx class
    mock_container = MagicMock()

    # AND a mock container that will fail when the pebble service is started
    mock_container.autostart = MagicMock(side_effect=pebble.ChangeError('something', MagicMock()))
    # AND ngx_otel_module file is not found in the container
    mock_container.exists.return_value = False

    nginx = Nginx(mock_container)

    # WHEN we call nginx.reconcile with some tracing related config
    # THEN an exception should be raised
    with pytest.raises(pebble.ChangeError):
        with caplog.at_level('ERROR'):
            nginx.reconcile(nginx_config='placeholder nginx config with ngx_otel_module')

    # AND we can verify that the missing-module message is in the logs
    assert 'missing the ngx_otel_module' in caplog.text


upstream_configs = {
    'tempo': [
        NginxUpstream('zipkin', 9411, 'distributor'),
        NginxUpstream('otlp-grpc', 4317, 'distributor'),
        NginxUpstream('otlp-http', 4318, 'distributor'),
        NginxUpstream('jaeger-thrift-http', 14268, 'distributor'),
        NginxUpstream('jaeger-grpc', 14250, 'distributor'),
        NginxUpstream('tempo-http', 3200, 'query-frontend'),
        NginxUpstream('tempo-grpc', 9096, 'query-frontend'),
    ],
    'mimir': [
        NginxUpstream('distributor', 8080, 'distributor'),
        NginxUpstream('compactor', 8080, 'compactor'),
        NginxUpstream('querier', 8080, 'querier'),
        NginxUpstream('query-frontend', 8080, 'query-frontend'),
        NginxUpstream('ingester', 8080, 'ingester'),
        NginxUpstream('ruler', 8080, 'ruler'),
        NginxUpstream('store-gateway', 8080, 'store-gateway'),
    ],
    'loki': [
        NginxUpstream('read', 3100, 'read'),
        NginxUpstream('write', 3100, 'write'),
        NginxUpstream('all', 3100, 'all'),
        NginxUpstream('backend', 3100, 'backend'),
        NginxUpstream('worker', 3100, 'worker', ignore_address_lookup_key=True),
    ],
    'litmus': [
        NginxUpstream('auth', 3000, 'auth'),
        NginxUpstream('backend', 8080, 'backend'),
    ],
    'litmus_ssl': [
        NginxUpstream('auth', 3001, 'auth'),
        NginxUpstream('backend', 8081, 'backend'),
    ],
}
server_ports_to_locations = {
    'tempo': {
        9411: [NginxLocationConfig(backend='zipkin', path='/')],
        4317: [NginxLocationConfig(backend='otlp-grpc', path='/', is_grpc=True)],
        4318: [NginxLocationConfig(backend='otlp-http', path='/')],
        14268: [NginxLocationConfig(backend='jaeger-thrift-http', path='/')],
        14250: [NginxLocationConfig(backend='jaeger-grpc', path='/', is_grpc=True)],
        3200: [NginxLocationConfig(backend='tempo-http', path='/')],
        9096: [NginxLocationConfig(backend='tempo-grpc', path='/', is_grpc=True)],
    },
    'mimir': {
        8080: [
            NginxLocationConfig(path='/distributor', backend='distributor'),
            NginxLocationConfig(path='/api/v1/push', backend='distributor'),
            NginxLocationConfig(path='/otlp/v1/metrics', backend='distributor'),
            NginxLocationConfig(path='/prometheus/config/v1/rules', backend='ruler'),
            NginxLocationConfig(path='/prometheus/api/v1/rules', backend='ruler'),
            NginxLocationConfig(path='/prometheus/api/v1/alerts', backend='ruler'),
            NginxLocationConfig(path='/ruler/ring', backend='ruler', modifier='='),
            NginxLocationConfig(path='/prometheus', backend='query-frontend'),
            NginxLocationConfig(
                path='/api/v1/status/buildinfo', backend='query-frontend', modifier='='
            ),
            NginxLocationConfig(path='/api/v1/upload/block/', backend='compactor', modifier='='),
        ]
    },
    'loki': {
        8080: [
            NginxLocationConfig(path='/loki/api/v1/push', modifier='=', backend='write'),
            NginxLocationConfig(path='/loki/api/v1/rules', modifier='=', backend='backend'),
            NginxLocationConfig(path='/prometheus', modifier='=', backend='backend'),
            NginxLocationConfig(
                path='/api/v1/rules',
                modifier='=',
                backend='backend',
                backend_url='/loki/api/v1/rules',
            ),
            NginxLocationConfig(path='/loki/api/v1/tail', modifier='=', backend='read'),
            NginxLocationConfig(
                path='/loki/api/.*',
                modifier='~',
                backend='read',
                headers={'Upgrade': '$http_upgrade', 'Connection': 'upgrade'},
            ),
            NginxLocationConfig(path='/loki/api/v1/format_query', modifier='=', backend='worker'),
            NginxLocationConfig(
                path='/loki/api/v1/status/buildinfo', modifier='=', backend='worker'
            ),
            NginxLocationConfig(path='/ring', modifier='=', backend='worker'),
        ]
    },
    'litmus': {
        8185: [
            NginxLocationConfig(
                path='/',
                extra_directives={
                    'add_header': ['Cache-Control', 'no-cache'],
                    'try_files': ['$uri', '/index.html'],
                    'autoindex': ['on'],
                },
            ),
            NginxLocationConfig(
                path='/auth', backend='auth', rewrite=['^/auth(/.*)$', '$1', 'break']
            ),
            NginxLocationConfig(path='/api', backend='backend'),
        ]
    },
    'litmus_ssl': {
        8185: [
            NginxLocationConfig(
                path='/',
                extra_directives={
                    'add_header': ['Cache-Control', 'no-cache'],
                    'try_files': ['$uri', '/index.html'],
                    'autoindex': ['on'],
                },
            ),
            NginxLocationConfig(
                path='/auth',
                backend='auth',
                rewrite=['^/auth(/.*)$', '$1', 'break'],
                extra_directives={
                    'proxy_ssl_verify': ['off'],
                    'proxy_ssl_session_reuse': ['on'],
                    'proxy_ssl_certificate': ['/etc/tls/tls.crt'],
                    'proxy_ssl_certificate_key': ['/etc/tls/tls.key'],
                },
            ),
            NginxLocationConfig(
                path='/api',
                backend='backend',
                extra_directives={
                    'proxy_ssl_verify': ['off'],
                    'proxy_ssl_session_reuse': ['on'],
                    'proxy_ssl_certificate': ['/etc/tls/tls.crt'],
                    'proxy_ssl_certificate_key': ['/etc/tls/tls.key'],
                },
            ),
        ]
    },
}


def _get_nginx_config_params(workload: str) -> tuple[list, dict]:
    return upstream_configs[workload], _get_server_ports_to_locations(workload)


def _get_server_ports_to_locations(workload: str) -> dict[int, list[NginxLocationConfig]]:
    return server_ports_to_locations[workload]
