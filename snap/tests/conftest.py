# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Pytest configuration and fixtures that apply to all this package's tests."""

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Pytest configuration specific to the snap package.

    Used instead of the package's ``pyproject.toml`` or ``pytest.ini`` so that the repository
    root's ``pyproject.toml`` is treated as the pytest root. Otherwise pytest would use the
    package's file as its only config, silently dropping the root's ``--strict-markers`` and
    shared marker list.
    """
    # Opt in to warnings-as-errors.
    # Relax a category for a single test with the @pytest.mark.filterwarnings decorator:
    # https://docs.pytest.org/en/stable/reference/reference.html#pytest-mark-filterwarnings-ref
    # https://docs.python.org/3/library/warnings.html#warning-filter
    config.addinivalue_line('filterwarnings', 'error')
