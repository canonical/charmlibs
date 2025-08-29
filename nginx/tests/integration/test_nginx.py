# Copyright 2025 Canonical
# See LICENSE file for licensing details.

"""Integration tests using a real Juju and charm to test ContainerPath."""

from __future__ import annotations

import jubilant
import pytest

from conftest import deploy


@pytest.mark.setup
def test_deployment(juju: jubilant.Juju, charm: str):
    deploy(juju, charm)
    assert charm in juju.status().apps
    juju.wait(lambda status: jubilant.all_active(status, charm))


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
