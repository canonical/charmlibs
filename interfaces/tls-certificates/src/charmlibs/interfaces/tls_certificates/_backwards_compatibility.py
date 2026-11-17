# Copyright 2026 Canonical Ltd.

"""Backwards-compatibility shims for deployments created by older library versions.

This module is the single home for the upgrade-path hacks in this library. Each
shim papers over data (secret labels, secret ownership, ...) written by an older
version of this library or its Charmhub predecessor
(``charms.tls_certificates_interface.v4``), so that existing deployments keep
working after a charm upgrade.

Keep each shim self-contained and document:

- what the old versions wrote,
- what the current code expects instead, and
- when the shim can be removed.

To avoid circular imports, this module must not import from
``._tls_certificates``; callers pass in whatever they need (e.g. ``LIBID``).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ops.model import SecretNotFoundError

if TYPE_CHECKING:
    from collections.abc import Callable

    import ops

logger = logging.getLogger(__name__)


def legacy_app_private_key_secret_label(libid: str, relationship_name: str) -> str:
    """Label under which ``Mode.APP`` private keys were stored by older versions.

    Depending on the version that created the secret, it refers to:

    - a unit-owned secret, created by every unit (before the fix in
      https://github.com/canonical/charmlibs/pull/267, i.e. Charmhub v4
      libpatch < 30), or
    - an app-owned secret (versions with that fix that still used this label).

    ops cannot report who owns a secret, and Juju's label lookup is ambiguous
    when a unit-owned and an app-owned secret share a label. Current versions
    therefore store the APP key under a distinct label (with an ``-app-``
    infix), and the shims below migrate away from this legacy label.
    """
    return f"{libid}-private-key-{relationship_name}"


def migrate_legacy_app_private_key(
    model: ops.Model,
    libid: str,
    relationship_name: str,
    store_app_private_key: Callable[[str], None],
) -> bool:
    """Adopt the ``Mode.APP`` private key stored under the legacy label, if any.

    Re-stores the legacy key via ``store_app_private_key`` (which must write an
    app-owned secret under the current label) and removes the legacy secret.
    Reusing the key material keeps the outstanding CSRs and issued certificates
    valid, so upgrading does not regenerate certificates
    (https://github.com/canonical/charmlibs/issues/565).

    Must only be called on the leader unit, and only when no secret exists
    under the current APP label yet.

    Returns:
        True if a legacy key was migrated, False if there was nothing to migrate.

    Removal: once upgrades from charmlibs < 1.9.0 and from the Charmhub v4
    library no longer need to be supported.
    """
    label = legacy_app_private_key_secret_label(libid, relationship_name)
    try:
        secret = model.get_secret(label=label)
        private_key = secret.get_content(refresh=True)["private-key"]
    except (SecretNotFoundError, KeyError):
        return False
    try:
        store_app_private_key(private_key)
    except ValueError:
        logger.warning(
            "Legacy private key secret with label %s does not contain a valid key, ignoring it",
            label,
        )
        return False
    secret.remove_all_revisions()
    logger.info("Migrated private key from legacy secret with label %s", label)
    return True


def remove_legacy_app_private_key(model: ops.Model, libid: str, relationship_name: str) -> None:
    """Remove the ``Mode.APP`` private key secret stored under the legacy label, if any.

    Complements :func:`migrate_legacy_app_private_key` in the code paths that
    remove the library-generated private key (relation broken, charm-provided
    key), so a not-yet-migrated legacy secret is cleaned up as well.

    Removal: together with :func:`migrate_legacy_app_private_key`.
    """
    try:
        secret = model.get_secret(
            label=legacy_app_private_key_secret_label(libid, relationship_name)
        )
        secret.remove_all_revisions()
        logger.debug("Removed legacy private key secret")
    except SecretNotFoundError:
        pass


def certificate_secret_label_without_relation_name(
    libid: str, csr_sha256_hex: str, unit_number: str | None
) -> str:
    """Certificate secret label format used before the relation name was added.

    Old versions labelled certificate secrets without the relation name, so
    certificate lookups fall back to this label for secrets created before the
    change. ``unit_number`` is None in ``Mode.APP``.

    Removal: once certificates issued by those versions have all been renewed
    under the current label format (a certificate lifetime after all supported
    deployments upgraded).
    """
    if unit_number is not None:
        return f"{libid}-certificate-{unit_number}-{csr_sha256_hex}"
    return f"{libid}-certificate-{csr_sha256_hex}"
