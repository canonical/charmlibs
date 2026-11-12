#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Functional tests for _snapd_system_info: system_info."""

import subprocess

from charmlibs import snap


def test_architecture_matches_dpkg():
    # snapd's architecture is its dpkg architecture, so on a standard Ubuntu system
    # the two agree.
    dpkg_arch = subprocess.run(
        ['dpkg', '--print-architecture'], capture_output=True, check=True, text=True
    ).stdout.strip()
    assert snap.system_info().architecture == dpkg_arch
