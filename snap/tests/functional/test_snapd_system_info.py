#!/usr/bin/env python3
# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Functional tests for _snapd_system_info: system_arch."""

import subprocess

from charmlibs import snap


def test_system_arch_matches_dpkg():
    # snapd's architecture is its dpkg architecture, so on a standard Ubuntu system
    # the two agree by construction.
    dpkg_arch = subprocess.run(
        ['dpkg', '--print-architecture'], capture_output=True, check=True, text=True
    ).stdout.strip()
    assert snap.system_arch() == dpkg_arch
