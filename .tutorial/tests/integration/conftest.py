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

"""Fixtures for Juju integration tests."""

import os
import pathlib
from collections.abc import Iterator

import jubilant
import pytest


@pytest.fixture(scope='session')
def charm() -> str:
    """Return the charm name."""
    return 'test'  # determined by test charms' charmcraft.yaml


@pytest.fixture(scope='module')
def juju(juju: jubilant.Juju, charm: str) -> Iterator[jubilant.Juju]:
    """Deploy into pytest-jubilant's temporary model.

    pytest-jubilant creates the model and tears it down afterwards. See its
    ``--no-juju-teardown`` and ``--juju-dump-logs`` options.
    """
    juju.model_config({'logging-config': '<root>=INFO;unit=DEBUG'})
    _deploy(juju)
    juju.wait(jubilant.all_active)
    yield juju


def _deploy(juju: jubilant.Juju) -> None:
    substrate = os.environ['CHARMLIBS_SUBSTRATE']
    # tag = os.environ.get('CHARMLIBS_TAG', '')  # get the tag if needed
    path = pathlib.Path(__file__).parent / '.packed' / f'{substrate}.charm'  # set by pack.sh
    if substrate == 'k8s':
        juju.deploy(path, resources={'workload': 'ubuntu:latest'})  # name set in metadata.yaml
    else:
        juju.deploy(path)
