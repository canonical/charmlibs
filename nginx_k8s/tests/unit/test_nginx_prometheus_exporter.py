# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

from dataclasses import replace

import ops
import ops.testing
import pytest

from charmlibs.nginx_k8s import NginxPrometheusExporter, TLSConfig
from charmlibs.nginx_k8s._nginx_prometheus_exporter import (
    PROM_EXPORTER_CERT_PATH,
    PROM_EXPORTER_KEY_PATH,
)

MOCK_TLS_CONFIG = TLSConfig(
    server_cert='mock-server-cert',
    ca_cert='mock-ca-cert',
    private_key='mock-private-key',
)


@pytest.fixture
def exporter_context():
    return ops.testing.Context(
        ops.CharmBase,
        meta={'name': 'foo', 'containers': {'nginx-pexp': {}}},
    )


@pytest.fixture
def exporter_container():
    return ops.testing.Container('nginx-pexp', can_connect=True)


@pytest.fixture
def exporter_certificate_mounts(tmp_path):
    mounts = {}
    for path, name in (
        (PROM_EXPORTER_KEY_PATH, 'server.key'),
        (PROM_EXPORTER_CERT_PATH, 'server.crt'),
    ):
        temp_file = tmp_path / name
        temp_file.write_text('mock-cert-data')
        mounts[path] = ops.testing.Mount(location=path, source=str(temp_file))
    return mounts


def test_exporter_certs_mgmt(
    exporter_context: ops.testing.Context,
    exporter_container: ops.testing.Container,
    exporter_certificate_mounts: dict,
):
    # GIVEN a charm with a container that has certificate mounts
    ctx = exporter_context

    # WHEN we process any event
    with ctx(
        ctx.on.update_status(),
        state=ops.testing.State(
            containers={replace(exporter_container, mounts=exporter_certificate_mounts)},
        ),
    ) as mgr:
        exporter = NginxPrometheusExporter(mgr.charm.unit.get_container('nginx-pexp'))

        # THEN the certificates exist on disk
        assert exporter.are_certificates_on_disk

        # AND when we clear the TLS configuration
        exporter._configure_tls(tls_config=None)

        # THEN the certificates are removed from disk
        assert not exporter.are_certificates_on_disk


def test_exporter_web_config_file_switch(
    exporter_context: ops.testing.Context,
    exporter_container: ops.testing.Container,
):
    # GIVEN a charm with an exporter container
    ctx = exporter_context

    # WHEN we reconcile without TLS
    with ctx(
        ctx.on.update_status(),
        state=ops.testing.State(containers={exporter_container}),
    ) as mgr:
        NginxPrometheusExporter(mgr.charm.unit.get_container('nginx-pexp')).reconcile()
        state_out = mgr.run()

    # THEN the scrape URI uses HTTP on the standard nginx port
    command = (
        state_out.get_container('nginx-pexp').plan.services['nginx-prometheus-exporter'].command
    )
    assert '--nginx.scrape-uri=http://127.0.0.1:8080/status' in command

    # AND WHEN we reconcile with nginx_serves_tls=True
    with ctx(
        ctx.on.update_status(),
        state=ops.testing.State(containers={exporter_container}),
    ) as mgr:
        NginxPrometheusExporter(mgr.charm.unit.get_container('nginx-pexp')).reconcile(
            nginx_serves_tls=True
        )
        state_out = mgr.run()

    # THEN the scrape URI switches to HTTPS on the TLS port
    command = (
        state_out.get_container('nginx-pexp').plan.services['nginx-prometheus-exporter'].command
    )
    assert '--nginx.scrape-uri=https://127.0.0.1:443/status' in command


def test_nginx_exporter_pebble_layer_sentinel(
    exporter_context: ops.testing.Context,
    exporter_container: ops.testing.Container,
):
    # GIVEN a charm with an exporter container
    ctx = exporter_context

    # WHEN we reconcile without TLS
    with ctx(
        ctx.on.update_status(),
        state=ops.testing.State(containers={exporter_container}),
    ) as mgr:
        NginxPrometheusExporter(mgr.charm.unit.get_container('nginx-pexp')).reconcile()
        state_out = mgr.run()

    sentinel_no_tls = (
        state_out.get_container('nginx-pexp')
        .plan.services['nginx-prometheus-exporter']
        .environment.get('_reload')
    )

    # AND WHEN we reconcile with a TLS config
    with ctx(
        ctx.on.update_status(),
        state=ops.testing.State(containers={exporter_container}),
    ) as mgr:
        NginxPrometheusExporter(mgr.charm.unit.get_container('nginx-pexp')).reconcile(
            MOCK_TLS_CONFIG
        )
        state_out = mgr.run()

    sentinel_tls = (
        state_out.get_container('nginx-pexp')
        .plan.services['nginx-prometheus-exporter']
        .environment.get('_reload')
    )

    # THEN the reload sentinel differs between TLS and non-TLS configurations
    assert sentinel_no_tls != sentinel_tls
