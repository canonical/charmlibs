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
import pathlib
import sys
import time
import typing
from collections.abc import Iterator

import jubilant
import pytest

logger = logging.getLogger(__name__)

# pack.sh packs charms/<id>-charm/ to .packed/<id>.charm, deployed below as the fixture's app name
PACKED = pathlib.Path(__file__).parent / '.packed'


def pytest_addoption(parser: pytest.OptionGroup):
    parser.addoption(
        '--keep-models',
        action='store_true',
        default=False,
        help='keep temporarily-created models',
    )


@pytest.fixture(scope='session')
def provider() -> str:
    """Return the provider app name, as deployed by the juju fixture."""
    return 'provider'


@pytest.fixture(scope='session')
def requirer() -> str:
    """Return the requirer app name, as deployed by the juju fixture."""
    return 'requirer'


@pytest.fixture(scope='module')
def juju(request: pytest.FixtureRequest, provider: str, requirer: str) -> Iterator[jubilant.Juju]:
    """Pytest fixture that wraps :meth:`jubilant.with_model`.

    This adds command line parameter ``--keep-models`` (see help for details).
    """
    keep_models = typing.cast('bool', request.config.getoption('--keep-models'))
    with jubilant.temp_model(keep=keep_models) as juju:
        juju.model_config({'logging-config': '<root>=INFO;unit=DEBUG'})
        # tag = os.environ.get('CHARMLIBS_TAG', '')  # get the tag if needed
        juju.deploy(PACKED / 'provider.charm', app=provider)  # charm ID -> app name
        juju.deploy(PACKED / 'requirer.charm', app=requirer)
        juju.wait(jubilant.all_active)
        yield juju
        if request.session.testsfailed:
            logger.info('Collecting Juju logs ...')
            time.sleep(0.5)  # Wait for Juju to process logs.
            log = juju.debug_log(limit=1000)
            print(log, end='', file=sys.stderr)
