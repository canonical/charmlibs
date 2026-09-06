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

"""Pytest configuration and fixtures that apply to all this package's tests."""

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Pytest configuration specific to the uptime package.

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
