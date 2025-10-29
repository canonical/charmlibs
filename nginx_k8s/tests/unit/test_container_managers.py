# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.
import typing

import ops
import ops.testing as scenario
import pytest

from charmlibs.nginx_k8s import Nginx, NginxConfig, NginxPrometheusExporter


@pytest.fixture(params=[4242, 8080])
def nginx_port(request: pytest.FixtureRequest) -> int:
    return typing.cast('int', request.param)


@pytest.fixture(params=[True, False])
def nginx_insecure(request: pytest.FixtureRequest) -> bool:
    return typing.cast('bool', request.param)


@pytest.fixture(params=[True, False])
def update_cacerts(request: pytest.FixtureRequest) -> bool:
    return typing.cast('bool', request.param)


@pytest.fixture(params=[3030, 5050])
def nginx_pexp_port(request: pytest.FixtureRequest) -> int:
    return typing.cast('int', request.param)


@pytest.fixture
def ctx(
    nginx_port: int, nginx_insecure: bool, nginx_pexp_port: int, update_cacerts: bool
) -> scenario.Context[ops.CharmBase]:
    class MyCharm(ops.CharmBase):
        META: typing.ClassVar[dict[str, typing.Any]] = {
            'name': 'jeremy',
            'containers': {'nginx': {}, 'nginx-pexp': {}},
        }

        def __init__(self, f: ops.Framework):
            super().__init__(f)
            self.nginx = Nginx(
                container=self.unit.get_container('nginx'),
                update_ca_certificates_on_restart=update_cacerts,
            )
            self.nginx_pexp = NginxPrometheusExporter(
                self.unit.get_container('nginx-pexp'),
                nginx_port=nginx_port,
                nginx_insecure=nginx_insecure,
                nginx_prometheus_exporter_port=nginx_pexp_port,
            )

            self.nginx.reconcile(
                NginxConfig(
                    server_name='server',
                    upstream_configs=[],
                    server_ports_to_locations={},
                ).get_config(upstreams_to_addresses={}, listen_tls=False)
            )
            self.nginx_pexp.reconcile()

    return scenario.Context(MyCharm, meta=MyCharm.META)


@pytest.fixture
def base_state():
    execs = {
        scenario.Exec(['nginx', '-s', 'reload']),
        scenario.Exec(['update-ca-certificates', '--fresh']),
    }
    return scenario.State(
        leader=True,
        containers={
            scenario.Container('nginx', can_connect=True, execs=execs),
            scenario.Container('nginx-pexp', can_connect=True, execs=execs),
        },
    )


def test_nginx_container_service(ctx: scenario.Context[ops.CharmBase], base_state: scenario.State):
    # given any event
    state_out = ctx.run(ctx.on.update_status(), state=base_state)
    # the services are running
    assert state_out.get_container('nginx').services['nginx'].is_running()
    assert state_out.get_container('nginx-pexp').services['nginx-prometheus-exporter'].is_running()


def test_layer_commands(
    ctx: scenario.Context[ops.CharmBase],
    base_state: scenario.State,
    nginx_pexp_port: int,
    nginx_insecure: bool,
    nginx_port: int,
):
    # given any event
    state_out = ctx.run(ctx.on.update_status(), state=base_state)
    # the commands are running with the expected arguments
    assert (
        state_out.get_container('nginx').plan.services['nginx'].command == "nginx -g 'daemon off;'"
    )

    pexp_command = (
        state_out.get_container('nginx-pexp').plan.services['nginx-prometheus-exporter'].command
    )
    scheme = 'http' if nginx_insecure else 'https'
    assert (
        pexp_command == f'nginx-prometheus-exporter '
        f'--no-nginx.ssl-verify '
        f'--web.listen-address=:{nginx_pexp_port} '
        f'--nginx.scrape-uri={scheme}://127.0.0.1:{nginx_port}/status'
    )
