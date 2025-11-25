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

"""Manage services controlled by systemd."""

import logging
import subprocess

_logger = logging.getLogger(__name__)


class SystemdError(Exception):
    """Custom exception for systemd related errors."""


def _systemctl(*args: str, check: bool = False) -> int:
    """Call a `systemctl` command with logging enabled.

    Args:
        args: Arguments to pass to the `systemctl` command.
        check: If set to `True`, raise an error if the command exits with a non-zero exit code.

    Returns:
        Returncode of `systemctl` command execution.

    Raises:
        SystemdError:
            Raised if the called command fails and check is set to `True`.
    """
    cmd = ['systemctl', *args]
    _logger.debug('running command %s', cmd)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=check)
    except subprocess.CalledProcessError as e:
        raise SystemdError(
            f'Command {cmd} failed with returncode {e.returncode}. systemctl output:\n'
            + f'stdout: {e.stdout}\n'
            + f'stderr: {e.stderr}'
        ) from None

    _logger.debug(
        "command '%s' completed with:\nexit code: %s\nstdout: %s\nstderr: %s",
        ' '.join(cmd),
        result.returncode,
        result.stdout,
        result.stderr,
    )
    return result.returncode


def service_running(service_name: str) -> bool:
    """Report whether a system service is running.

    Args:
        service_name: The name of the service to check.

    Returns:
        True if service is running/active; False if not.
    """
    # If returncode is 0, this means that is service is active.
    return _systemctl('--quiet', 'is-active', service_name) == 0


def service_failed(service_name: str) -> bool:
    """Report whether a system service has failed.

    Args:
        service_name: The name of the service to check.

    Returns:
        True if service is marked as failed; False if not.
    """
    # If returncode is 0, this means that the service has failed.
    return _systemctl('--quiet', 'is-failed', service_name) == 0


def service_start(*args: str) -> bool:
    """Start a system service.

    Args:
        *args: Arguments to pass to `systemctl start` (normally the service name).

    Returns:
        On success, this function returns True for historical reasons.

    Raises:
        SystemdError: Raised if `systemctl start ...` returns a non-zero returncode.
    """
    return _systemctl('start', *args, check=True) == 0


def service_stop(*args: str) -> bool:
    """Stop a system service.

    Args:
        *args: Arguments to pass to `systemctl stop` (normally the service name).

    Returns:
        On success, this function returns True for historical reasons.

    Raises:
        SystemdError: Raised if `systemctl stop ...` returns a non-zero returncode.
    """
    return _systemctl('stop', *args, check=True) == 0


def service_restart(*args: str) -> bool:
    """Restart a system service.

    Args:
        *args: Arguments to pass to `systemctl restart` (normally the service name).

    Returns:
        On success, this function returns True for historical reasons.

    Raises:
        SystemdError: Raised if `systemctl restart ...` returns a non-zero returncode.
    """
    return _systemctl('restart', *args, check=True) == 0


def service_enable(*args: str) -> bool:
    """Enable a system service.

    Args:
        *args: Arguments to pass to `systemctl enable` (normally the service name).

    Returns:
        On success, this function returns True for historical reasons.

    Raises:
        SystemdError: Raised if `systemctl enable ...` returns a non-zero returncode.
    """
    return _systemctl('enable', *args, check=True) == 0


def service_disable(*args: str) -> bool:
    """Disable a system service.

    Args:
        *args: Arguments to pass to `systemctl disable` (normally the service name).

    Returns:
        On success, this function returns True for historical reasons.

    Raises:
        SystemdError: Raised if `systemctl disable ...` returns a non-zero returncode.
    """
    return _systemctl('disable', *args, check=True) == 0


def service_reload(service_name: str, restart_on_failure: bool = False) -> bool:
    """Reload a system service, optionally falling back to restart if reload fails.

    Args:
        service_name: The name of the service to reload.
        restart_on_failure:
            Boolean indicating whether to fall back to a restart if the reload fails.

    Returns:
        On success, this function returns True for historical reasons.

    Raises:
        SystemdError: Raised if `systemctl reload|restart ...` returns a non-zero returncode.
    """
    try:
        return _systemctl('reload', service_name, check=True) == 0
    except SystemdError:
        if restart_on_failure:
            return service_restart(service_name)
        else:
            raise


def service_pause(service_name: str) -> bool:
    """Pause a system service.

    Stops the service and prevents the service from starting again at boot.

    Args:
        service_name: The name of the service to pause.

    Returns:
        On success, this function returns True for historical reasons.

    Raises:
        SystemdError: Raised if service is still running after being paused by systemctl.
    """
    _systemctl('disable', '--now', service_name)
    _systemctl('mask', service_name)

    if service_running(service_name):
        raise SystemdError(f'Attempted to pause {service_name!r}, but it is still running.')

    return True


def service_resume(service_name: str) -> bool:
    """Resume a system service.

    Re-enable starting the service again at boot. Start the service.

    Args:
        service_name: The name of the service to resume.

    Returns:
        On success, this function returns True for historical reasons.

    Raises:
        SystemdError: Raised if service is not running after being resumed by systemctl.
    """
    _systemctl('unmask', service_name)
    _systemctl('enable', '--now', service_name)

    if not service_running(service_name):
        raise SystemdError(f'Attempted to resume {service_name!r}, but it is not running.')

    return True


def daemon_reload() -> bool:
    """Reload systemd manager configuration.

    Returns:
        On success, this function returns True for historical reasons.

    Raises:
        SystemdError: Raised if `systemctl daemon-reload` returns a non-zero returncode.
    """
    return _systemctl('daemon-reload', check=True) == 0
