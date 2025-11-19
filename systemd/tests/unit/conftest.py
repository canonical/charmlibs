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

"""Fixtures for unit tests, typically mocking out parts of the external system."""

import subprocess
from collections.abc import Callable, Iterable
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pytest


@pytest.fixture(scope='function')
def make_mock(
    request: pytest.FixtureRequest,
) -> Callable[[Iterable[int], bool], tuple[MagicMock, dict[str, Any]]]:
    """Create a `subprocess.run` mock with side effects.

    Examples:
        >>> mock_run, kwargs = make_mock([0, 1], check=True)
        >>> subprocess.run(...)
        >>> mock_run.assert_called()
        >>> with pytest.raises(subprocess.CalledProcessError)
        ...     subprocess.run(...)
    """

    def _make(returncodes: Iterable[int], check: bool = False) -> tuple[MagicMock, dict[str, Any]]:
        side_effects = []
        for code in returncodes:
            if code != 0 and check:
                side_effects.append(subprocess.CalledProcessError(code, cmd='systemctl fail'))
            else:
                mock_result = Mock()
                mock_result.returncode = code
                mock_result.stdout = ''
                mock_result.stderr = ''
                mock_result.check = check
                side_effects.append(mock_result)

        mock_run = MagicMock()
        mock_run.side_effect = side_effects

        # Patch `subprocess.run` function for the test.
        patcher = patch.object(subprocess, 'run', mock_run)
        patcher.start()
        request.addfinalizer(patcher.stop)

        return mock_run, {'capture_output': True, 'text': True, 'check': check}

    return _make
