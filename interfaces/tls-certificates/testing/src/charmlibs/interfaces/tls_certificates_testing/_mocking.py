# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""The ``mocked`` context manager, and the scope check the state-producing methods share."""

from __future__ import annotations

import contextlib
import itertools
import threading
import typing
import unittest.mock

from charmlibs.interfaces import tls_certificates
from charmlibs.interfaces.tls_certificates import _tls_certificates as _internal

from . import _raw

if typing.TYPE_CHECKING:
    from collections.abc import Iterator

_MOCKED_KEY = tls_certificates.PrivateKey(raw=_raw.KEY)
"""The key the library gets instead of generating one, while ``mocked`` is active.

Deliberately not public. A test that wants to know which key the charm ended up with reads
it off the library (``get_assigned_certificates`` returns it), which works whether the key
came from here, from the charm, or from a rotation -- so no test needs to name this.
"""

# The scope is process-wide rather than per-instance because `mocked` and the remote classes
# are independent pieces of API (see OP093): a fixture opens the scope, and remotes
# constructed anywhere -- at module level, typically -- operate inside it. Thread-local so
# that pytest-xdist-style parallelism, or a test that runs a charm on another thread, can't
# see another scope's depth.
_state = threading.local()


def _depth() -> int:
    return getattr(_state, "depth", 0)


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
            with tls_certificates_testing.mocked():
                yield

    Several libraries' scopes stack, in any order::

        with tls_certificates_testing.mocked(), certificate_transfer_testing.mocked():
            ...

    What is mocked today is the library's private key generation, which is replaced with a
    pre-generated RSA key. Generating a 2048-bit key takes a noticeable fraction of a
    second, and a charm that lets the library manage its key generates one on its first
    reconcile and again on every rotation, so a suite of a few hundred state-transition
    tests otherwise spends most of its time on key generation. Nothing outside the library
    is patched: a charm that generates its own keys, through ``cryptography`` or anything
    else, is unaffected.

    The key is a real RSA key, so everything that depends on having one keeps working --
    signing, ``matches_private_key``, chain verification. The only observable difference is
    that a charm which lets the library manage its key gets the same key in every test. Key
    *rotation* still produces a distinct key: the mock returns a fresh key for each call
    after the first, so a test asserting that ``regenerate_private_key`` changed the key
    still tests something.

    The scope is reentrant, so a fixture and the test that uses it may each open one, and
    nesting is harmless.
    """
    if _depth():  # already inside a scope; nothing to do but count the nesting
        _state.depth = _depth() + 1
        try:
            yield
        finally:
            _state.depth = _depth() - 1
        return
    keys = _mocked_keys()
    serial_numbers = itertools.count(_FIRST_SERIAL_NUMBER)
    unique_identifiers = _mocked_unique_identifiers()
    _state.depth = 1
    try:
        with (
            unittest.mock.patch.object(
                tls_certificates.PrivateKey,
                "generate",
                # The signature the library calls it with, so a mistyped call still fails.
                side_effect=lambda key_size=2048, public_exponent=65537: next(keys),
            ),
            unittest.mock.patch.object(
                _internal, "_random_serial_number", side_effect=lambda: next(serial_numbers)
            ),
            unittest.mock.patch.object(
                _internal, "_unique_identifier", side_effect=lambda: next(unique_identifiers)
            ),
        ):
            yield
    finally:
        _state.depth = _depth() - 1


_FIRST_SERIAL_NUMBER = 1
"""Where the serial number sequence starts. Small, so that failures are readable."""


def _mocked_unique_identifiers() -> Iterator[str]:
    """Yield the identifiers the library puts in each request's subject name.

    Sequential rather than constant, and this is the one thing a replacement here must get
    right. The library uses this value to tell one request from another, so a constant would
    make a re-request -- what a key rotation or a renewal produces -- byte-identical to the
    request it replaces. The simulated provider would then see a request it had already
    answered and keep the stale certificate.
    """
    for n in itertools.count(1):
        # A valid version-4 UUID, so that anything parsing the subject name still works.
        yield f"00000000-0000-4000-8000-{n:012d}"


def _mocked_keys() -> Iterator[tls_certificates.PrivateKey]:
    """Yield the pre-generated key first, then freshly generated ones.

    The first call is the one that happens in almost every test -- a charm that lets the
    library manage its key generating it on its first reconcile -- and is the one worth
    making free. Later calls mean the charm asked for a *different* key, which is what
    ``regenerate_private_key`` does, so they must not return the same key again: a test
    asserting that rotation changed the key would then pass while testing nothing.
    """
    yield _MOCKED_KEY
    while True:
        yield _real_generate()


# Bound before any patching, so that the fallback path can't recurse into the mock.
_real_generate = tls_certificates.PrivateKey.generate


def require_mocked(method: str) -> None:
    """Raise unless a ``mocked`` scope is active. Called by every state-producing method."""
    if _depth():
        return
    raise RuntimeError(
        f"{method} must be called inside a tls_certificates_testing.mocked() scope, which "
        "has to be entered before the charm runs:\n\n"
        "    with tls_certificates_testing.mocked():\n"
        f"        state = remote.{method}(...)\n\n"
        "Every charmlibs.interfaces testing package requires this, including the ones that "
        "currently mock nothing, so that a library can start mocking without breaking the "
        "tests already written against it."
    )
