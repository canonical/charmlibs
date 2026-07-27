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
