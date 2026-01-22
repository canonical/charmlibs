# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for library code, not involving charm code."""

from charmlibs import slo


def test_version():
    assert isinstance(slo.__version__, str)
