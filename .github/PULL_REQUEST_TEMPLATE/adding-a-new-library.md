<!--
Template: Adding a new library to the charmlibs monorepo.

If you selected the wrong template, go back one page in your browser.

Read first:
https://canonical.com/juju/docs/charmlibs/how-to/python-package/#what-can-i-publish-under-the-charmlibs-namespace

To learn how to add a new library:
https://canonical.com/juju/docs/charmlibs/tutorial/
-->

This PR adds a new charm library. <!-- update with relevant context -->

## Library being added

- **New `charmlibs` package:** <!-- for example `charmlibs.foo` / `charmlibs.interfaces.bar` -->
- **Specification:** <!-- link to the spec / design doc -->

<!-- remove one -->
This is a general library (`charmlibs.<name>`, `just init`).
This is an interface library (`charmlibs.interfaces.<name>`, `just init --interface`).


## Checklist

Package:
- [ ] Package initialised with `just init` or `just init --interface`.
- [ ] Public API exported from `__init__.py` with `__all__`.
- [ ] Everything else is private, unless explicitly documented as public.
- [ ] Module docstring in `__init__.py` describes the package (rendered in the reference docs).
- [ ] Library version set for release (typically `1.0.0`).

Repository metadata:
- [ ] `.docs/reference/libs.yaml` updated with a new entry.
- [ ] `CODEOWNERS` updated with a `/<package>/` entry for the owning team.

Tests and docs:
- [ ] Unit tests added, plus functional and integration tests as appropriate.
- [ ] Unnecessary files created by `just init` have been removed (including `test_version.py` and `tests/functional` and `tests/integration` if unused).
- [ ] Diataxis docs added under `<package>/docs/` (only if needed, prefer module docstring for lightweight docs).

<!-- remove section if this isn't an interface library -->
### Interface library specific items

- [ ] Directory name exactly matches the interface name as written in `charmcraft.yaml`.
- [ ] Interface metadata added under `interfaces/<name>/interface/` (readme, metadata, databag schema).
- [ ] Testing package added under `interfaces/<name>/testing/` exporting `relation_for_provider` and `relation_for_requirer` if needed (see [how-to guide](https://canonical.com/juju/docs/charmlibs/how-to/provide-relation-data-for-charm-tests/)).

## Commit strategy

<!-- Describe how the work is split across commits in this PR. -->

The first commit in this PR is purely the output of `just init`. This commit can be excluded from the changes view (once verified), making it easy to se what changes were made on top of the template.
