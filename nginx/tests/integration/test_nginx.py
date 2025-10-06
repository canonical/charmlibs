# Copyright 2025 Canonical
# See LICENSE file for licensing details.

"""Integration tests using a real Juju and charm to test ContainerPath."""

from __future__ import annotations

import jubilant
import pytest
import yaml

from .conftest import deploy

pytestmark = pytest.mark.k8s_only


@pytest.mark.setup
def test_deployment(juju: jubilant.Juju, charm: str):
    deploy(juju, charm)
    assert charm in juju.status().apps
    juju.wait(
        lambda status: jubilant.all_active(status, charm),
        timeout=3600,
        successes=6,
        delay=10,
    )


def test_nginx_service_running(juju: jubilant.Juju, charm: str):
    services = juju.ssh(charm + '/0', 'pebble services', container='nginx')
    assert services.splitlines()[1].split()[:3] == ['nginx', 'enabled', 'active']


def test_nginx_pexp_service_running(juju: jubilant.Juju, charm: str):
    services = juju.ssh(charm + '/0', 'pebble services', container='nginx-pexp')
    assert services.splitlines()[1].split()[:3] == [
        'nginx-prometheus-exporter',
        'enabled',
        'active',
    ]


def test_configs(juju: jubilant.Juju, charm: str):
    res = juju.run(charm + '/0', 'inspect').results
    # services are UP
    assert res['nginx-up'] == 'True'
    assert res['nginx-pexp-up'] == 'True'

    # nginx config is a complex format; make a couple of simple assertions to verify
    # expected structures are there.
    nginx_cfg_raw = res['nginx-config']
    assert 'client_body_temp_path /tmp/client_temp' in nginx_cfg_raw
    assert 'worker_processes 5' in nginx_cfg_raw  # the default number

    # check the nginx pexp plan
    cmd = yaml.safe_load(res['nginx-prom-exporter-plan'])['services']['nginx-prometheus-exporter'][
        'command'
    ]
    assert '--nginx.scrape-uri=https://127.0.0.1:8080/status' in cmd
