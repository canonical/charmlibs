# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

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


@pytest.fixture(scope='module')
def juju(request: pytest.FixtureRequest) -> Iterator[jubilant.Juju]:
    """Pytest fixture that wraps :meth:`jubilant.with_model`.

    This adds command line parameter ``--keep-models`` (see help for details).
    """
    keep_models = typing.cast('bool', request.config.getoption('--keep-models'))
    with jubilant.temp_model(keep=keep_models) as juju:
        juju.model_config({'logging-config': '<root>=INFO;unit=DEBUG'})
        yield juju
        if request.session.testsfailed:
            logger.info('Collecting Juju logs ...')
            time.sleep(0.5)  # Wait for Juju to process logs.
            log = juju.debug_log(limit=1000)
            print(log, end='', file=sys.stderr)


@pytest.fixture(scope='module')
def sloth_provider_charm() -> str:
    """Sloth test provider charm used for integration testing."""
    provider_dir = pathlib.Path(__file__).parent / 'charms' / 'sloth-provider'
    charm_path = (
        provider_dir.parent.parent / '.packed' / 'sloth-test-provider_ubuntu-24.04-amd64.charm'
    )

    if charm_path.exists():
        logger.info('using existing provider charm: %s', charm_path)
        return str(charm_path)

    # If not found, the charm needs to be packed first with `just pack-k8s sloth`
    raise FileNotFoundError(
        f'Sloth provider charm not found at {charm_path}. '
        "Run 'just pack-k8s sloth' to pack the test charms first."
    )


@pytest.fixture(scope='module')
def sloth_requirer_charm() -> str:
    """Sloth test requirer charm used for integration testing."""
    requirer_dir = pathlib.Path(__file__).parent / 'charms' / 'sloth-requirer'
    charm_path = (
        requirer_dir.parent.parent / '.packed' / 'sloth-test-requirer_ubuntu-24.04-amd64.charm'
    )

    if charm_path.exists():
        logger.info('using existing requirer charm: %s', charm_path)
        return str(charm_path)

    # If not found, the charm needs to be packed first with `just pack-k8s sloth`
    raise FileNotFoundError(
        f'Sloth requirer charm not found at {charm_path}. '
        "Run 'just pack-k8s sloth' to pack the test charms first."
    )
