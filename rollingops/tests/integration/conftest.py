# Copyright 2026 Canonical Ltd.
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

import logging
import os
import pathlib
import sys
import time
from collections.abc import Iterator

import jubilant
import pytest

logger = logging.getLogger(__name__)


def pytest_addoption(parser: pytest.OptionGroup):
    parser.addoption(
        '--keep-models',
        action='store_true',
        default=False,
        help='keep temporarily-created models',
    )


@pytest.fixture(scope='session')
def app_name() -> str:
    """Return the default application name."""
    return 'test'  # determined by test charms' charmcraft.yaml


@pytest.fixture(scope='session')
def charm() -> pathlib.Path:
    """Return the packed charm path."""
    substrate = os.environ['CHARMLIBS_SUBSTRATE']
    # tag = os.environ.get('CHARMLIBS_TAG', '')  # get the tag if needed
    return pathlib.Path(__file__).parent / '.packed' / f'{substrate}.charm'  # set by pack.sh


@pytest.fixture(scope='module')
def juju(
    request: pytest.FixtureRequest, charm: pathlib.Path, app_name: str
) -> Iterator[jubilant.Juju]:
    """Pytest fixture that wraps :meth:`jubilant.with_model`.

    This adds command line parameter ``--keep-models`` (see help for details).
    """
    # keep_models = typing.cast('bool', request.config.getoption('--keep-models'))
    with jubilant.temp_model(keep=True) as juju:
        juju.model_config({'logging-config': '<root>=INFO;unit=DEBUG'})
        _deploy(juju, charm=charm, app_name=app_name)
        juju.wait(jubilant.all_active, timeout=15 * 60.0)
        yield juju
        if request.session.testsfailed:
            logger.info('Collecting Juju logs ...')
            time.sleep(0.5)  # Wait for Juju to process logs.
            log = juju.debug_log(limit=0)
            print(log, end='', file=sys.stderr)


def _deploy(juju: jubilant.Juju, charm: pathlib.Path, app_name: str, num_units: int = 1) -> None:
    substrate = os.environ['CHARMLIBS_SUBSTRATE']
    if substrate == 'k8s':
        juju.deploy(
            charm, app=app_name, num_units=num_units, resources={'workload': 'ubuntu:latest'}
        )
    else:
        juju.deploy(charm, app=app_name, num_units=num_units)
