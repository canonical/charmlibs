# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""The ``mocked`` context manager, and the scope check the state-producing methods share."""

from __future__ import annotations

import contextlib
import threading
import typing

if typing.TYPE_CHECKING:
    from collections.abc import Iterator

# The scope is process-wide rather than per-instance because `mocked` and the remote classes
# are independent pieces of API (see OP093): a fixture opens the scope, and remotes
# constructed anywhere -- at module level, typically -- operate inside it. Thread-local so
# that pytest-xdist-style parallelism, or a test that runs a charm on another thread, can't
# see another scope's depth.
_state = threading.local()


def _depth() -> int:
    return getattr(_state, 'depth', 0)


@contextlib.contextmanager
def mocked() -> Iterator[None]:
    """Mock out the library's internals for the duration of the context.

    Every method that builds state or runs the charm -- :meth:`RemoteProvider.integrate`,
    :meth:`RemoteProvider.publish`, :meth:`RemoteProvider.run_changed`, and the
    :class:`RemoteRequirer` equivalents -- must be called inside this scope, and raises if
    it isn't. :meth:`RemoteProvider.get_relation` does not, so assertions can read the
    relation after the scope has closed.

    Open it in a fixture, or inline, and keep it open for the charm's execution as well as
    the arrangement::

        @pytest.fixture()
        def mocked():
            with certificate_transfer_testing.mocked():
                yield

    Several libraries' scopes stack, in any order::

        with certificate_transfer_testing.mocked(), tls_certificates_testing.mocked():
            ...

    The scope is reentrant, so a fixture and the test that uses it may each open one, and
    nesting is harmless.

    This library mocks nothing today: everything ``charmlibs.interfaces.certificate_transfer``
    does is reading and writing relation data, which ``ops.testing`` already models, with no
    side effects and nothing slow enough to be worth replacing -- the certificates it moves
    are opaque strings that it never parses. The scope is defined, and required, all the same
    -- a library that didn't require it would break every test written against it on the day
    it started mocking something, whereas requiring it from the start makes introducing
    mocking a non-breaking change.
    """
    _state.depth = _depth() + 1
    try:
        yield
    finally:
        _state.depth = _depth() - 1


def require_mocked(method: str) -> None:
    """Raise unless a ``mocked`` scope is active. Called by every state-producing method."""
    if _depth():
        return
    raise RuntimeError(
        f'{method} must be called inside a certificate_transfer_testing.mocked() scope, '
        'which has to be entered before the charm runs:\n\n'
        '    with certificate_transfer_testing.mocked():\n'
        f'        state = remote.{method}(...)\n\n'
        'Every charmlibs.interfaces testing package requires this, including the ones that '
        'currently mock nothing, so that a library can start mocking without breaking the '
        'tests already written against it.'
    )
