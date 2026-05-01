#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Shared helpers for functional tests."""

import logging
import subprocess

from charmlibs import snap

# Enable debug logging from snap library during tests.
handler = logging.StreamHandler()
handler.setLevel(logging.DEBUG)
snap_logger = logging.getLogger(snap.__name__)
snap_logger.setLevel(logging.DEBUG)
snap_logger.addHandler(handler)


def get_command_path(command: str) -> str:
    try:
        return subprocess.check_output(['which', command]).decode().strip()
    except subprocess.CalledProcessError:
        return ''


def ensure_removed(*snaps: str) -> None:
    for snap_name in snaps:
        if snap.info(snap_name, missing_ok=True) is not None:
            snap.remove(snap_name)


def ensure_installed(*snaps: str, channel: str | None = None, classic: bool = False) -> None:
    for snap_name in snaps:
        snap.ensure(snap_name, channel=channel, classic=classic, update=False)
