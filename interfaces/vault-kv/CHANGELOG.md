# 1.0.0 - 18 November 2026

Migrate the Charmhub-hosted `charms.vault_k8s.v0.vault_kv` library (LIBAPI 0, LIBPATCH 16) to `charmlibs.interfaces.vault_kv`.

Changes from the Charmhub-hosted library:

- Drop the `pytest-interface-tester` dependency. Charms that only depended on it for this library can remove it.
- Remove `ProviderSchema` and `RequirerSchema`, which were not used by the library's public API. Use `VaultKvProviderSchema`, `AppVaultKvRequirerSchema` and `UnitVaultKvRequirerSchema` instead.
