# Changelog

## 1.1.0

- Backport holistic client reconciliation fixes from `charms.hydra.v0.oauth`:
  - Refresh client secret on provider info lookup to prevent stale revisions when secrets rotate.
  - Handle invalid or incomplete relation databags gracefully without wedging hook execution.
  - Support updating existing Juju secrets in `OAuthProvider._create_juju_secret`.
  - Add `OAuthProvider.get_client_secret()` and `OAuthProvider.get_client_config()` methods.

## 1.0.0

Initial release. Migrated from `charms.hydra.v0.oauth` (v0.12).
