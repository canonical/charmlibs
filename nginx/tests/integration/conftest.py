# Copyright 2025 Canonical
# See LICENSE file for licensing details.

from __future__ import annotations

import os
import pathlib
import typing

import pytest

if typing.TYPE_CHECKING:
    import jubilant


@pytest.fixture(scope='session')
def charm() -> str:
    return os.environ['CHARMLIBS_SUBSTRATE']


def deploy(juju: jubilant.Juju, charm: str) -> None:
    if charm == 'k8s':
        juju.deploy(
            _get_packed_charm_path(charm),
            resources={
                'nginx': 'ghcr.io/canonical/nginx@sha256:6415a2c5f25f1d313c87315a681bdc84be80f3c79c304c6744737f9b34207993',
                'nginx-pexp': 'ubuntu/nginx-prometheus-exporter:1.4-24.04_stable',
            },
        )
    elif charm == 'machine':
        juju.deploy(_get_packed_charm_path(charm))
    else:
        raise ValueError(f'Unknown charm: {charm!r}')


def _get_packed_charm_path(charm: str) -> pathlib.Path:
    return pathlib.Path(__file__).parent / 'charms' / '.packed' / f'{charm}.charm'
