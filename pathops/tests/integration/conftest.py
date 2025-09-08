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


def pytest_addoption(parser: pytest.OptionGroup):
    parser.addoption(
        '--keep-models',
        action='store_true',
        default=False,
        help='keep temporarily-created models',
    )


@pytest.fixture(scope='session')
def charm() -> str:
    return os.environ['CHARMLIBS_SUBSTRATE']


@pytest.fixture(scope='module')
def juju(request: pytest.FixtureRequest, charm: str) -> Iterator[jubilant.Juju]:
    """Pytest fixture that wraps :meth:`jubilant.with_model`.

    This adds command line parameter ``--keep-models`` (see help for details).
    """
    keep_models = typing.cast('bool', request.config.getoption('--keep-models'))
    with jubilant.temp_model(keep=keep_models) as juju:
        _deploy(juju, charm)
        juju.wait(jubilant.all_active)
        yield juju
        if request.session.testsfailed:
            log = juju.debug_log(limit=1000)
            print(log, end='')


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
