#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Shared helpers for functional tests."""

from __future__ import annotations

import logging
import subprocess
import time
import typing

from charmlibs import snap
from charmlibs.snap import _functions

if typing.TYPE_CHECKING:
    from collections.abc import Callable
    from typing import TypeVar

    _T = TypeVar('_T')

# Enable debug logging from snap library during tests.
handler = logging.StreamHandler()
handler.setLevel(logging.DEBUG)
snap_logger = logging.getLogger(snap.__name__)
snap_logger.setLevel(logging.DEBUG)
snap_logger.addHandler(handler)

# The snap store rate-limits by client IP (HTTP 429). snapd surfaces this as a kindless error
# with the message "too many requests" -- synchronously for store queries like /v2/find, and
# wrapped in a ChangeError (an APIError subclass) for async install/refresh. CI runners share
# egress IPs and run the functional matrix concurrently, so these 429s are transient: retry with
# exponential backoff rather than failing the run. Only rate-limit errors are retried, so tests
# asserting on a specific error still see that error unchanged.
_RATE_LIMITED = 'too many requests'
_RETRY_ATTEMPTS = 5
_RETRY_BASE_DELAY = 2.0  # seconds; doubled each attempt (2, 4, 8, 16s between the 5 tries).


def retry_on_rate_limit(func: Callable[[], _T]) -> _T:
    """Call ``func()``, retrying store rate-limit (HTTP 429) failures.

    ``func`` is a zero-arg callable (typically a ``lambda`` wrapping the store operation), so
    that overloaded operations like ``install``/``refresh`` keep their normal type checking.
    """
    for attempt in range(_RETRY_ATTEMPTS):
        try:
            return func()
        except snap.APIError as e:  # noqa: PERF203
            if _RATE_LIMITED not in e.message.lower() or attempt == _RETRY_ATTEMPTS - 1:
                raise
            delay = _RETRY_BASE_DELAY * 2**attempt
            snap_logger.warning(
                'snap store rate-limited; retrying in %.0fs (attempt %d/%d)',
                delay,
                attempt + 1,
                _RETRY_ATTEMPTS,
            )
            time.sleep(delay)
    raise AssertionError('unreachable')  # pragma: no cover -- last attempt re-raises above.


def get_command_path(command: str) -> str:
    try:
        return subprocess.check_output(['which', command]).decode().strip()
    except subprocess.CalledProcessError:
        return ''


def ensure_removed(*snaps: str) -> None:
    for snap_name in snaps:
        if _functions._get_info(snap_name) is not None:
            snap.remove(snap_name)


def ensure_installed(*snaps: str, channel: str | None = None, classic: bool = False) -> None:
    for snap_name in snaps:
        retry_on_rate_limit(
            lambda name=snap_name: snap.ensure(
                name, channel=channel, classic=classic, update=False
            )
        )
