# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Pytest configuration for this package's tests."""

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Opt this package in to warnings-as-errors.

    Setting ``filterwarnings`` in the package's own ``pyproject.toml`` would make pytest
    use that file as its only config, silently dropping the repository root's
    ``--strict-markers`` and shared marker list, so the filter is added here instead.
    Relax a category for a single test with ``@pytest.mark.filterwarnings``.
    """
    config.addinivalue_line('filterwarnings', 'error')
