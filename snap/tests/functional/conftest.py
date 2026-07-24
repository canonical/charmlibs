#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Shared helpers for functional tests."""

from __future__ import annotations

import functools
import logging
import random
import subprocess
import time
import typing

from charmlibs import snap
from charmlibs.snap import _functions

if typing.TYPE_CHECKING:
    from collections.abc import Callable
    from typing import ParamSpec, TypeVar

    _P = ParamSpec('_P')
    _T = TypeVar('_T')

# Enable debug logging from snap library during tests.
handler = logging.StreamHandler()
handler.setLevel(logging.DEBUG)
snap_logger = logging.getLogger(snap.__name__)
snap_logger.setLevel(logging.DEBUG)
snap_logger.addHandler(handler)


def retry_on_rate_limit(func: Callable[_P, _T]) -> Callable[_P, _T]:
    """Wrap ``func`` so store rate-limit (HTTP 429) failures are retried with backoff.

    The snap store rate-limits by client IP. snapd surfaces this as a kindless error
    with the message "too many requests" -- synchronously for store queries like /v2/find, and
    wrapped in a ChangeError (an APIError subclass) for async install/refresh. CI runners share
    egress IPs and run the functional matrix concurrently, so these 429s are transient: retry with
    exponential backoff rather than failing the run. Only rate-limit errors are retried, so tests
    asserting on a specific error still see that error unchanged.
    """

    @functools.wraps(func)
    def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _T:
        max_attempts = 5
        attempts = 0
        while True:
            if attempts > 0:
                # Exponential backoff with jitter: 5s-6s, 10s-12s, 20s-24s, 40s-48s, ...
                delay = 5 * 2 ** (attempts - 1) * random.uniform(1.0, 1.2)
                msg = 'snap store rate-limited; retrying in %.0fs (attempt %d/%d)'
                snap_logger.warning(msg, delay, attempts, max_attempts)
                time.sleep(delay)
            attempts += 1
            try:
                return func(*args, **kwargs)
            except snap.APIError as e:
                # "too many requests" from canonical/snapd's store/store.go (ErrTooManyRequests)
                if attempts >= max_attempts or 'too many requests' not in e.message.lower():
                    raise

    return wrapper


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
        retry_on_rate_limit(snap.ensure)(snap_name, channel=channel, classic=classic, update=False)
