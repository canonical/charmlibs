---
myst:
  html_meta:
    description: Migrate your charm from a Charmhub-hosted library to the equivalent charmlibs Python package.
---

(how-to-migrate-charm)=
# How to migrate your charm to a charmlibs package

{ref}`Charmhub-hosted libraries are being phased out <charmhub-libraries-deprecation>` in favour of regular Python packages.
When a Charmhub-hosted library is migrated to the `charmlibs` monorepo, the new package is released as version `1.0.0` -- a bug-for-bug port of the library's latest Charmhub-hosted release.
This means that migrating your charm is a mechanical process that doesn't require any changes to your charm's logic.

This guide covers migrating your charm from a Charmhub-hosted library to the equivalent `charmlibs` or `charmlibs.interfaces` package.
If you maintain a Charmhub-hosted library and want to migrate the library itself, see {ref}`how-to-migrate` instead.

```{tip}
To find out which package supersedes a Charmhub-hosted library, check the library's documentation, or look it up in the {ref}`general <general-libs-listing>` and {ref}`interface <interface-libs-listing>` library listings, where legacy Charmhub-hosted libraries name their replacements.
```

## Remove the Charmhub-hosted library

1. If the library is listed in the `charm-libs` section of your `charmcraft.yaml`, remove its entry.
   If this was the only entry, remove the `charm-libs` section entirely.
   Likewise, if your build process calls `charmcraft fetch-libs` (for example, in CI) and no Charmhub-hosted libraries remain, remove those calls.
2. Delete the vendored copy of the library from your charm's repository -- that's the file `lib/charms/<charm name>/v<API version>/<module name>.py`.
   If the `lib/` directory is now empty, delete it too.
3. If you added any Python dependencies manually for the library (from its `PYDEPS`), remove the ones that nothing else needs.
   The new package declares its own dependencies, which are resolved automatically when your charm is packed.
   Take care to keep any dependencies that your charm uses directly, or that a remaining Charmhub-hosted library still needs.

## Add the charmlibs package

Add the new package to your charm's Python dependencies, for example with `uv`:

`````{tab-set}
````{tab-item} General libraries
:sync: general

```bash
uv add 'charmlibs-<module name>~=1.0'
```
````

````{tab-item} Interface libraries
:sync: interface

```bash
uv add 'charmlibs-interfaces-<module name>~=1.0'
```
````
`````

For example, `uv add 'charmlibs-snap~=1.0'` or `uv add 'charmlibs-interfaces-tls-certificates~=1.0'`.

If you don't use `uv`, add the package to your charm's dependencies in `pyproject.toml` or `requirements.txt` directly.
The `~=1.0` constraint means `>=1.0,<2` -- high enough to get bug fixes and new features, but protected from breaking changes.
Read more about version constraints and locking your charm's dependencies in {ref}`how-to-manage-charm-libraries`.

## Update your imports

In your charm code and tests, replace imports of the Charmhub-hosted library, which look like this:

```python
from charms.<charm name>.v<API version> import <module name>
from charms.<charm name>.v<API version>.<module name> import ...
```

with imports of the new package:

`````{tab-set}
````{tab-item} General libraries
:sync: general

```python
from charmlibs import <module name>
from charmlibs.<module name> import ...
```
````

````{tab-item} Interface libraries
:sync: interface

```python
from charmlibs.interfaces import <module name>
from charmlibs.interfaces.<module name> import ...
```
````
`````

For example, `from charms.operator_libs_linux.v2 import snap` becomes `from charmlibs import snap`, and `from charms.tls_certificates_interface.v4 import tls_certificates` becomes `from charmlibs.interfaces import tls_certificates`.

Because version `1.0` of the package is a bug-for-bug port of the Charmhub-hosted library, no other code changes are needed -- the names you import and their behaviour are unchanged.

## Verify the migration

Run your charm's unit tests, then pack your charm with `charmcraft pack` and deploy it or run your integration tests, to confirm that everything works exactly as before.

If the package you're migrating to is *not* a bug-for-bug port of the Charmhub-hosted library you were using -- for example, `charmlibs-snap` 2.0 has a new, backwards incompatible API -- refer to the library's documentation and changelog for the code changes you'll need to make.
