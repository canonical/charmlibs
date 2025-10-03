# Copyright 2025 Canonical
# See LICENSE file for licensing details.

from __future__ import annotations

import os
import pathlib
import typing

import pytest
import yaml

if typing.TYPE_CHECKING:
    import jubilant


@pytest.fixture(scope='session')
def charm() -> str:
    return os.environ['CHARMLIBS_SUBSTRATE']


def deploy(juju: jubilant.Juju, charm: str) -> None:
    if charm == 'k8s':
        juju.deploy(
            _get_packed_charm_path(charm),
            resources=_get_resources(charm),
        )
    else:
        raise ValueError(f'Unknown charm: {charm!r}')


def _get_packed_charm_path(charm: str) -> pathlib.Path:
    return pathlib.Path(__file__).parent / '.packed' / f'{charm}.charm'


def _get_resources(charm: str) -> dict[str, str]:
    charmcraft = pathlib.Path(__file__).parent / 'charms' / charm / 'charmcraft.yaml'
    yml = yaml.safe_load(charmcraft.read_text())
    return {res: meta['upstream-source'] for res, meta in yml['resources'].items()}
