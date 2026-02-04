# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for library code, not involving charm code."""

from charmlibs.interfaces import sloth


def test_version():
    assert isinstance(sloth.__version__, str)
