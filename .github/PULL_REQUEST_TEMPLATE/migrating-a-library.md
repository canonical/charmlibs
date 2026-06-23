<!--
Template: Migrating an existing Charmhub-hosted library into the charmlibs monorepo.

If you selected the wrong template, go back one page in your browser.

Read first:
https://documentation.ubuntu.com/charmlibs/how-to/python-package/#what-can-i-publish-under-the-charmlibs-namespace

To learn how to migrate a library:
https://documentation.ubuntu.com/charmlibs/how-to/migrate/
-->

This PR migrates an existing library to the charmlibs monorepo. <!-- update with relevant context -->

## Library being migrated

- **Charmhub-hosted library:** <!-- for example `charms.operator_libs_linux.v2.snap` -->
  - **LIBAPI:**
  - **LIBPATCH:**
  - **LIBID:**
- **New `charmlibs` package:** <!-- for example `charmlibs.snap` / `charmlibs.interfaces.tls_certificates` -->

<!-- remove one -->
This is a general library (`charmlibs.<name>`, `just init`).
This is an interface library (`charmlibs.interfaces.<name>`, `just init --interface`).

## Migration status

<!-- Update to match migration strategy -->
This is a bug compatible migration of the Charmhub-hosted library, releasing as version 1.0.0.

Package:
- [ ] Package initialised with `just init` or `just init --interface`.
- [ ] Code migrated to `src/charmlibs/<name>/_<name>.py`.
- [ ] Public API exported from `__init__.py` with `__all__`.
- [ ] Charmhub lib docstring moved to `__init__.py` (this is rendered in the docs).
- [ ] Charmhub-hosted `LIBAPI` and `LIBPATCH` version documented in the migrated module's docstring.
- [ ] `LIBID`, `LIBAPI`, `LIBPATCH` removed (or retained with a note on why).
- [ ] `PYDEPS` moved to `pyproject.toml` `dependencies` with appropriate constraints.
- [ ] Library version set for release (typically `1.0.0`).

Repository metadata:
- [ ] `.docs/reference/libs.yaml` updated with entries for new and old libs.
- [ ] `CODEOWNERS` updated with a `/<package>/` entry for the owning team.

Tests and docs:
- [ ] Unit tests migrated, plus functional and integration tests as appropriate.
- [ ] Unnecessary files created by `just init` have been removed (including `test_version.py` and `tests/functional` and `tests/integration` if unused).
- [ ] Diataxis docs (if any) migrated to `<package>/docs/`.

<!-- remove section if this isn't an interface library -->
### Interface library specific items

- [ ] Directory name exactly matches the interface name as written in `charmcraft.yaml`.
- [ ] Interface metadata added (or updated if necessary), or an issue created and tracked to do this as a follow-up task.
- [ ] Testing package added under `interfaces/<name>/testing/` exporting `relation_for_provider` and `relation_for_requirer` if needed (see [how-to guide](https://documentation.ubuntu.com/charmlibs/how-to/provide-relation-data-for-charm-tests/)), or an issue created and tracked to do this as a follow-up task.


## Commit strategy

To make review easier, this PR begins with a series of mechanical commits that can be easily excluded from review:

<!-- Update to match your work. -->

1. **Scaffolding** — output of `just init` or `just init --interface`.
2. **Lift and shift** — the existing Charmhub library source, tests, and docs copied to their new locations verbatim, providing a baseline for comparison with the original.
4. **Fix imports** — update import paths from `charms.<charm>.v<n>` to `charmlibs.<name>` (or `charmlibs.interfaces.<name>`) in code, tests and docs.
3. **Lint and format** — result of `just format` and `just lint`, with any necessary `pyproject.toml` config or ignores to avoid unwanted changes.
