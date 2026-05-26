# Copyright 2025 Canonical
# See LICENSE file for licensing details.

"""Regression tests for ResourceWarning leaks from container.pull().

``ops.Container.pull()`` returns a real Python file object (backed by a
``tempfile.NamedTemporaryFile`` under real pebble, or by ``open()`` in
``ops.testing``). Failing to close that handle emits a ``ResourceWarning``
when the object is garbage-collected, which fails any test run under
``-W error`` and indicates a real file-descriptor leak in production.

CPython releases the unreferenced file object as soon as ``pull(...).read()``
returns (refcount drops to zero), so the destructor fires synchronously and
the warning lands inside the ``catch_warnings`` window without an explicit
``gc.collect()``. Avoiding that call keeps these tests insensitive to
unrelated cycle-collected leaks elsewhere in the stack (e.g. in
``scenario.Context``).
"""

from __future__ import annotations

import warnings
from dataclasses import replace

from ops import testing

from charmlibs.nginx_k8s import Nginx, TLSConfig, TLSConfigManager


def _assert_no_unclosed_file_warnings(caught: list[warnings.WarningMessage]) -> None:
    leaks = [
        w
        for w in caught
        if issubclass(w.category, ResourceWarning) and 'unclosed file' in str(w.message)
    ]
    assert not leaks, '\n'.join(str(w.message) for w in leaks)


def test_has_config_changed_closes_pull_handle(
    ctx: testing.Context, nginx_container: testing.Container, tmp_path
):
    """``Nginx._has_config_changed`` must close the file returned by ``pull()``."""
    config_file = tmp_path / 'nginx.conf'
    config_file.write_text('foo')
    container = replace(
        nginx_container,
        mounts={
            'config': testing.Mount(location=Nginx.NGINX_CONFIG, source=str(config_file)),
        },
    )
    state = testing.State(containers={container})

    with ctx(ctx.on.update_status(), state=state) as mgr:
        nginx = Nginx(mgr.charm.unit.get_container(nginx_container.name))
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            assert nginx._has_config_changed('foo') is False
        _assert_no_unclosed_file_warnings(caught)


def test_sync_certificates_closes_pull_handles(
    ctx: testing.Context, nginx_container: testing.Container, tmp_path
):
    """``TLSConfigManager._sync_certificates`` must close every ``pull()`` handle."""
    mounts = {}
    for path, name in (
        (TLSConfigManager.KEY_PATH, 'key'),
        (TLSConfigManager.CERT_PATH, 'cert'),
        (TLSConfigManager.CA_CERT_PATH, 'cacert'),
    ):
        f = tmp_path / name
        f.write_text('foo')
        mounts[name] = testing.Mount(location=path, source=str(f))
    container = replace(nginx_container, mounts=mounts)
    state = testing.State(containers={container})

    with ctx(ctx.on.update_status(), state=state) as mgr:
        tls_mgr = TLSConfigManager(mgr.charm.unit.get_container(nginx_container.name))
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            tls_mgr._sync_certificates(
                TLSConfig(server_cert='foo', ca_cert='foo', private_key='foo'),
            )
        _assert_no_unclosed_file_warnings(caught)
