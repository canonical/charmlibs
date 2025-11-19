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

"""Unit tests for the `systemd` charm library."""

from unittest.mock import call

import pytest

from charmlibs import systemd


def test_daemon_reload(make_mock):
    mock_run, kwargs = make_mock([0, 1], check=True)

    systemd.daemon_reload()
    mock_run.assert_called_with(['systemctl', 'daemon-reload'], **kwargs)

    # Failed to reload systemd configuration.
    with pytest.raises(systemd.SystemdError):
        systemd.daemon_reload()
    mock_run.assert_called_with(['systemctl', 'daemon-reload'], **kwargs)


def test_service_running(make_mock):
    mock_run, kwargs = make_mock([0, 3])

    result = systemd.service_running('mysql')
    mock_run.assert_called_with(['systemctl', '--quiet', 'is-active', 'mysql'], **kwargs)
    assert result is True

    result = systemd.service_running('mysql')
    mock_run.assert_called_with(['systemctl', '--quiet', 'is-active', 'mysql'], **kwargs)
    assert result is False


def test_service_failed(make_mock):
    mock_run, kwargs = make_mock([0, 1])

    result = systemd.service_failed('mysql')
    mock_run.assert_called_with(['systemctl', '--quiet', 'is-failed', 'mysql'], **kwargs)
    assert result

    result = systemd.service_failed('mysql')
    mock_run.assert_called_with(
        [
            'systemctl',
            '--quiet',
            'is-failed',
            'mysql',
        ],
        **kwargs,
    )
    assert result is False


def test_service_start(make_mock):
    mock_run, kwargs = make_mock([0, 1], check=True)

    systemd.service_start('mysql')
    mock_run.assert_called_with(['systemctl', 'start', 'mysql'], **kwargs)

    with pytest.raises(systemd.SystemdError):
        systemd.service_start('mysql')
    mock_run.assert_called_with(['systemctl', 'start', 'mysql'], **kwargs)


def test_service_stop(make_mock):
    mock_run, kwargs = make_mock([0, 1], check=True)

    systemd.service_stop('mysql')
    mock_run.assert_called_with(['systemctl', 'stop', 'mysql'], **kwargs)

    with pytest.raises(systemd.SystemdError):
        systemd.service_stop('mysql')
    mock_run.assert_called_with(['systemctl', 'stop', 'mysql'], **kwargs)


def test_service_restart(make_mock):
    mock_run, kwargs = make_mock([0, 1], check=True)

    systemd.service_restart('mysql')
    mock_run.assert_called_with(['systemctl', 'restart', 'mysql'], **kwargs)

    with pytest.raises(systemd.SystemdError):
        systemd.service_restart('mysql')
    mock_run.assert_called_with(['systemctl', 'restart', 'mysql'], **kwargs)


def test_service_enable(make_mock):
    mock_run, kwargs = make_mock([0, 1], check=True)

    systemd.service_enable('slurmd')
    mock_run.assert_called_with(['systemctl', 'enable', 'slurmd'], **kwargs)

    with pytest.raises(systemd.SystemdError):
        systemd.service_enable('slurmd')
    mock_run.assert_called_with(['systemctl', 'enable', 'slurmd'], **kwargs)


def test_service_disable(make_mock):
    mock_run, kwargs = make_mock([0, 1], check=True)

    systemd.service_disable('slurmd')
    mock_run.assert_called_with(['systemctl', 'disable', 'slurmd'], **kwargs)

    with pytest.raises(systemd.SystemdError):
        systemd.service_disable('slurmd')
    mock_run.assert_called_with(['systemctl', 'disable', 'slurmd'], **kwargs)


def test_service_reload(make_mock):
    # We reload successfully.
    mock_run, kwargs = make_mock([0], check=True)
    systemd.service_reload('mysql')
    mock_run.assert_called_with(['systemctl', 'reload', 'mysql'], **kwargs)

    # We can't reload, so we restart
    mock_run, kwargs = make_mock([1, 0], check=True)
    systemd.service_reload('mysql', restart_on_failure=True)
    mock_run.assert_has_calls([
        call(['systemctl', 'reload', 'mysql'], **kwargs),
        call(['systemctl', 'restart', 'mysql'], **kwargs),
    ])

    # We should only restart if requested.
    mock_run, kwargs = make_mock([1, 0], check=True)
    with pytest.raises(systemd.SystemdError):
        systemd.service_reload('mysql')
    mock_run.assert_called_with(['systemctl', 'reload', 'mysql'], **kwargs)

    # ... and if we fail at both, we should fail.
    mock_run, kwargs = make_mock([1, 1], check=True)
    with pytest.raises(systemd.SystemdError):
        systemd.service_reload('mysql', restart_on_failure=True)
    mock_run.assert_has_calls([
        call(['systemctl', 'reload', 'mysql'], **kwargs),
        call(['systemctl', 'restart', 'mysql'], **kwargs),
    ])


def test_service_pause(make_mock):
    # Test pause
    mock_run, kwargs = make_mock([0, 0, 3])

    systemd.service_pause('mysql')
    mock_run.assert_has_calls([
        call(['systemctl', 'disable', '--now', 'mysql'], **kwargs),
        call(['systemctl', 'mask', 'mysql'], **kwargs),
        call(['systemctl', '--quiet', 'is-active', 'mysql'], **kwargs),
    ])

    # Could not stop service!
    mock_run, kwargs = make_mock([0, 0, 0])
    with pytest.raises(systemd.SystemdError):
        systemd.service_pause('mysql')
    mock_run.assert_has_calls([
        call(['systemctl', 'disable', '--now', 'mysql'], **kwargs),
        call(['systemctl', 'mask', 'mysql'], **kwargs),
        call(['systemctl', '--quiet', 'is-active', 'mysql'], **kwargs),
    ])


def test_service_resume(make_mock):
    # Resume service.
    mock_run, kwargs = make_mock([0, 0, 0])
    systemd.service_resume('mysql')
    mock_run.assert_has_calls([
        call(['systemctl', 'unmask', 'mysql'], **kwargs),
        call(['systemctl', 'enable', '--now', 'mysql'], **kwargs),
        call(['systemctl', '--quiet', 'is-active', 'mysql'], **kwargs),
    ])

    # Failed to resume service.
    mock_run, kwargs = make_mock([0, 0, 3])
    with pytest.raises(systemd.SystemdError):
        systemd.service_resume('mysql')
    mock_run.assert_has_calls([
        call(['systemctl', 'unmask', 'mysql'], **kwargs),
        call(['systemctl', 'enable', '--now', 'mysql'], **kwargs),
        call(['systemctl', '--quiet', 'is-active', 'mysql'], **kwargs),
    ])
