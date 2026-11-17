# Changelog

## 1.2.0

- Allow a client to register more than one redirect URI: `ClientConfig.redirect_uri` and the
  `redirect_uri` databag field now accept a list of URIs as well as a single URI.
  - Add `ClientConfig.redirect_uris`, which returns the URIs as a list whichever form was used.
  - A single URI is still published as a plain string, so requirers that do not use a list keep
    working with providers older than 1.2.0. Those providers reject a list.

## 1.1.0

- Backport holistic client reconciliation fixes from `charms.hydra.v0.oauth`:
  - Refresh client secret on provider info lookup to prevent stale revisions when secrets rotate.
  - Handle invalid or incomplete relation databags gracefully without wedging hook execution.
  - Support updating existing Juju secrets in `OAuthProvider._create_juju_secret`.
  - Add `OAuthProvider.get_client_secret()` and `OAuthProvider.get_client_config()` methods.

## 1.0.0

Initial release. Migrated from `charms.hydra.v0.oauth` (v0.12).
