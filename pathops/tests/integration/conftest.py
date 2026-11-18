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

from __future__ import annotations

import os
import pathlib
import typing

import jubilant
import pytest

if typing.TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(scope='session')
def charm() -> str:
    return os.environ['CHARMLIBS_SUBSTRATE']


@pytest.fixture(scope='module')
def juju(juju: jubilant.Juju, charm: str) -> Iterator[jubilant.Juju]:
    """Deploy into pytest-jubilant's temporary model.

    pytest-jubilant creates the model and tears it down afterwards. See its
    ``--no-juju-teardown`` and ``--juju-dump-logs`` options.
    """
    juju.model_config({'logging-config': '<root>=INFO;unit=DEBUG'})
    _deploy(juju, charm)
    juju.wait(jubilant.all_active)
    yield juju


def _deploy(juju: jubilant.Juju, charm: str) -> None:
    if charm == 'k8s':
        juju.deploy(
            _get_packed_charm_path(charm),
            resources={'workload': 'ubuntu:latest'},
        )
    elif charm == 'machine':
        juju.deploy(_get_packed_charm_path(charm))
    else:
        raise ValueError(f'Unknown charm: {charm!r}')


def _get_packed_charm_path(charm: str) -> pathlib.Path:
    return pathlib.Path(__file__).parent / 'charms' / '.packed' / f'{charm}.charm'
