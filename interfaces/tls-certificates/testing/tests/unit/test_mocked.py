# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

"""Tests for the ``mocked`` context manager itself."""

import datetime
import threading
import time
import unittest.mock

import ops.testing
import pytest

import requirer_charm
from charmlibs.interfaces import tls_certificates as tls_certificates
from charmlibs.interfaces import tls_certificates_testing as tls_certificates_testing

REMOTE = tls_certificates_testing.RemoteProvider("certificates")


def test_mocked_takes_no_arguments():
    """OP093 requires it to be callable with no arguments."""
    with tls_certificates_testing.mocked():
        pass


def _is_mocked() -> bool:
    """Whether the library's key generation is currently patched."""
    return isinstance(tls_certificates.PrivateKey.generate, unittest.mock.NonCallableMock)


def test_mocked_is_reentrant():
    """A fixture and the test that uses it may each open a scope.

    The inner scopes must not un-patch on the way out, which is what a naive implementation
    of a reentrant context manager gets wrong.
    """
    with tls_certificates_testing.mocked():
        with tls_certificates_testing.mocked():
            with tls_certificates_testing.mocked():
                assert _is_mocked()
            assert _is_mocked()  # still mocked after the innermost scope exits
        assert _is_mocked()
    assert not _is_mocked()


def test_mocked_restores_the_real_generate():
    """Nothing leaks past the outermost scope."""
    assert not _is_mocked()
    with tls_certificates_testing.mocked():
        assert _is_mocked()
    assert not _is_mocked()
    assert tls_certificates.PrivateKey.generate().is_valid()  # the real thing, unpatched


def test_mocked_restores_on_exception():
    with pytest.raises(RuntimeError, match="boom"):
        with tls_certificates_testing.mocked():
            raise RuntimeError("boom")
    assert not _is_mocked()


def test_mocked_restores_on_exception_from_a_nested_scope():
    with pytest.raises(RuntimeError, match="boom"):
        with tls_certificates_testing.mocked():
            with tls_certificates_testing.mocked():
                raise RuntimeError("boom")
    assert not _is_mocked()


def test_mocked_generates_a_real_key():
    """The mock is a real RSA key, so everything that needs one keeps working."""
    with tls_certificates_testing.mocked():
        key = tls_certificates.PrivateKey.generate()
    assert key.is_valid()


def test_mocked_key_is_stable_for_the_first_generation():
    """The common case -- a charm generating its managed key -- is free and repeatable."""
    with tls_certificates_testing.mocked():
        first = tls_certificates.PrivateKey.generate()
    with tls_certificates_testing.mocked():
        again = tls_certificates.PrivateKey.generate()
    assert first == again


def test_mocked_rotation_returns_a_different_key():
    """Rotation must really rotate.

    An autouse fixture pinning the key to a constant would be actively harmful:
    ``regenerate_private_key`` generates through the same path, so a test asserting the key
    changed would silently pass while testing nothing.
    """
    with tls_certificates_testing.mocked():
        first = tls_certificates.PrivateKey.generate()
        second = tls_certificates.PrivateKey.generate()
        third = tls_certificates.PrivateKey.generate()
    assert first != second
    assert second != third


def test_mocked_accepts_the_libraries_call_signature():
    """The library calls it with keywords; a mock that didn't accept them would hide that."""
    with tls_certificates_testing.mocked():
        assert tls_certificates.PrivateKey.generate(key_size=2048).is_valid()
        assert tls_certificates.PrivateKey.generate(key_size=2048, public_exponent=65537)


def test_mocked_serial_numbers_are_sequential():
    """Serial numbers come from a counter, so certificates don't differ run to run."""
    from charmlibs.interfaces.tls_certificates import _tls_certificates as internal

    with tls_certificates_testing.mocked():
        first = [internal._random_serial_number() for _ in range(3)]
    with tls_certificates_testing.mocked():
        again = [internal._random_serial_number() for _ in range(3)]
    assert first == again
    assert len(set(first)) == 3  # ... and still distinct within a scope.


def test_mocked_unique_identifiers_are_sequential_but_distinct():
    """The one replacement that must stay distinct. See ``_mocked_unique_identifiers``.

    A constant here would make a re-request byte-identical to the request it replaces, so
    the provider would treat it as already answered and a renewal test would assert nothing.
    """
    import uuid

    from charmlibs.interfaces.tls_certificates import _tls_certificates as internal

    with tls_certificates_testing.mocked():
        first = [internal._unique_identifier() for _ in range(3)]
    with tls_certificates_testing.mocked():
        again = [internal._unique_identifier() for _ in range(3)]
    assert first == again  # repeatable ...
    assert len(set(first)) == 3  # ... and distinct, which is the load-bearing part.
    for identifier in first:
        assert uuid.UUID(identifier).version == 4  # still a valid UUID for anything parsing it


def test_mocked_sequences_restart_for_each_scope():
    """Each scope starts over, so one test's work can't change what another test sees."""
    from charmlibs.interfaces.tls_certificates import _tls_certificates as internal
    from charmlibs.interfaces.tls_certificates_testing import _mocking

    with tls_certificates_testing.mocked():
        internal._random_serial_number()
        internal._random_serial_number()
    with tls_certificates_testing.mocked():
        assert internal._random_serial_number() == _mocking._FIRST_SERIAL_NUMBER


def test_mocked_does_not_make_certificates_reproducible_across_a_second():
    """The limit of what mocking can achieve here, and the reason worth knowing.

    Serial numbers and subject identifiers are sequenced, but a certificate's validity dates
    come from the clock, which the library reads directly. Mocking that would mean mocking
    ``datetime`` -- outside the library, and so forbidden, since it would change the
    behaviour of charm code that never touches this library. So two runs of the same
    arrangement match only if they land in the same second, and a test must not compare
    certificate bytes between separately-arranged states.
    """
    ctx = ops.testing.Context(requirer_charm.RequirerCharm, meta=requirer_charm.META)
    remote = tls_certificates_testing.RemoteProvider("certificates")

    def certificate() -> str:
        with tls_certificates_testing.mocked():
            state = remote.integrate(ctx, ops.testing.State.from_context(ctx), end="published")
        return remote.get_relation(state).remote_app_data["certificates"]

    first = certificate()
    second = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    while datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0) == second:
        time.sleep(0.01)  # wait for the clock to tick over
    assert certificate() != first


def test_mocked_does_not_patch_anything_outside_the_library():
    """No side effects for code that doesn't go through the library."""
    from cryptography.hazmat.primitives.asymmetric import rsa

    before = rsa.generate_private_key
    with tls_certificates_testing.mocked():
        assert rsa.generate_private_key is before


def test_mocked_scope_is_thread_local():
    """One thread's scope must not satisfy another's requirement.

    The scope is process-wide by design -- a module-level remote has to see a scope opened in
    a fixture -- but it is kept per-thread so that parallel tests can't see each other's.
    """
    seen: list[bool] = []

    def check() -> None:
        try:
            REMOTE.publish(ops.testing.State())
        except RuntimeError:
            seen.append(False)
        except Exception:  # any other failure means the scope was visible
            seen.append(True)
        else:
            seen.append(True)

    with tls_certificates_testing.mocked():
        thread = threading.Thread(target=check)
        thread.start()
        thread.join()
    assert seen == [False]


@pytest.mark.parametrize("method", ["integrate", "publish", "run_changed"])
def test_state_producing_methods_require_the_scope(method: str):
    """Uniform requirement, so introducing mocking is never a breaking change."""
    ctx = ops.testing.Context(requirer_charm.RequirerCharm, meta=requirer_charm.META)
    state = ops.testing.State()
    args = {"integrate": (ctx, state), "publish": (state,), "run_changed": (ctx, state)}[method]
    with pytest.raises(RuntimeError, match="mocked"):
        getattr(REMOTE, method)(*args)


def test_get_relation_does_not_require_the_scope():
    """Assertions commonly run after the scope has closed, so this one must work outside it."""
    ctx = ops.testing.Context(requirer_charm.RequirerCharm, meta=requirer_charm.META)
    with tls_certificates_testing.mocked():
        state = REMOTE.integrate(ctx, ops.testing.State.from_context(ctx))
    relation = REMOTE.get_relation(state)  # outside the scope
    assert relation.endpoint == "certificates"


def test_the_scope_covers_the_charms_execution():
    """Mocking matters most while the charm runs, not only during arrangement."""
    ctx = ops.testing.Context(requirer_charm.RequirerCharm, meta=requirer_charm.META)
    with tls_certificates_testing.mocked():
        state = REMOTE.integrate(ctx, ops.testing.State.from_context(ctx), end="integrated")
        with ctx(ctx.on.update_status(), state) as manager:
            manager.run()
            _, key = manager.charm.certificates.get_assigned_certificates()
    # The key the charm generated while running is the mocked one.
    with tls_certificates_testing.mocked():
        assert key == tls_certificates.PrivateKey.generate()
