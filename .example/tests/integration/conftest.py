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

# pack.sh packs charms/<id>-charm/ to .packed/<id>.charm, deployed below as the fixture's app name
PACKED = pathlib.Path(__file__).parent / '.packed'


@pytest.fixture(scope='session')
def charm() -> str:
    """Return the app name, as deployed by the juju fixture."""
    return 'test'


@pytest.fixture(scope='module')
def juju(
    request: pytest.FixtureRequest, juju: jubilant.Juju, charm: str
) -> Iterator[jubilant.Juju]:
    """Deploy the test charm into pytest-jubilant's temporary model.

    pytest-jubilant creates the model and tears it down afterwards. See its
    ``--no-juju-teardown`` and ``--juju-dump-logs`` options.
    """
    juju.model_config({'logging-config': '<root>=INFO;unit=DEBUG'})
    substrate = os.environ['CHARMLIBS_SUBSTRATE']
    # tag = os.environ.get('CHARMLIBS_TAG', '')  # get the tag if needed
    path = PACKED / f'{substrate}.charm'  # the charm ID is the substrate
    if substrate == 'k8s':
        juju.deploy(path, app=charm, resources={'workload': 'ubuntu:latest'})
    else:
        juju.deploy(path, app=charm)
    juju.wait(jubilant.all_active)
    yield juju
    if request.session.testsfailed:
        logger.info('Collecting Juju logs ...')
        time.sleep(0.5)  # Wait for Juju to process logs.
        log = juju.debug_log(limit=1000)
        print(log, end='', file=sys.stderr)
