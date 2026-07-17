---
myst:
  html_meta:
    description: Charmhub-hosted charm libraries fetched with charmcraft fetch-libs are being phased out in favour of standard Python packages.
---

(charmhub-libraries-deprecation)=
# Charmhub-hosted libraries are being phased out

Charmhub-hosted charm libraries -- single-file Python modules fetched with `charmcraft fetch-libs` -- are being phased out in favour of standard Python packages distributed on PyPI.

## Background

Charms originally shared code by distributing single-file Python modules on Charmhub. Each module was associated with a specific charm. Charms fetched libraries using the `charmcraft fetch-lib` and `charmcraft fetch-libs` commands, and typically checked them into their version control. These libraries were stored under `lib/`, which was added to `PYTHONPATH` at runtime, allowing the module to be imported by charm name and API version. For example `from operator_libs_linux.v2 import snap`.

## Timeline

- `charmcraft` emits a deprecation warning on library operations (we are here).
- Charmhub disables uploading *new* libraries (26.10 cycle).
- Charmhub disables updates to existing libraries.

## Why the change?

### No dependency resolution

Charmhub-hosted libraries have no mechanism for resolving dependencies on other Python packages. If a library needs a dependency, it lists the package name in a `PYDEPS` variable, and the charm author must manually add each dependency to their charm's own requirements. That is, transitive dependencies of Charmhub-hosted libraries are tracked manually, and the charm author is also responsible for resolving a compatible version for the different libraries that might require that dependency.

Standard Python packages, by contrast, declare their dependencies in metadata that tools like `pip` and `uv` resolve automatically.

### Vendored code is hard to maintain

Because Charmhub libraries are committed into each charm's repository, updating a library means re-running `charmcraft fetch-libs` and committing the result. Across many charms, this creates a maintenance burden and increases the risk of running outdated code.

### Limited tooling integration

Charmhub libraries do not participate in standard Python tooling. This makes it trickier to ensure their visibility for dependency scanners and vulnerability checkers, leads to the library itself not being visible in the charm's lock file, and requires extra work to make the library visible in IDEs.

## What replaces it?

Charm libraries should be distributed as regular Python packages, typically on PyPI.
Libraries of broad interest are published under the `charmlibs` namespace from the [`charmlibs` monorepo](https://github.com/canonical/charmlibs). Team-specific libraries can be distributed on PyPI under their own namespace, as Git dependencies, or as local packages in a charm monorepo.

Read more: {ref}`how-to-python-package`

## What should I do?

### If you maintain a Charmhub-hosted library

Migrate it to a Python package. If it implements a widely-used interface or provides broadly useful functionality, it belongs in the `charmlibs` monorepo.

Read more: {ref}`how-to-migrate`

### If you use Charmhub-hosted libraries in your charm

When a Python package replacement is available, switch to it:

1. Remove the library from the `charm-libs` section of your `charmcraft.yaml` and delete the vendored directory from `lib/`.
2. Remove any manually added transitive dependencies that are no longer needed.
3. Add the replacement package to your charm's dependencies.
4. Update your imports to use the new package's import path.

Read more: {ref}`how-to-manage-charm-libraries`

### If you are writing a new library

Create it as a Python package from the start. Do not publish new libraries on Charmhub.

Read more: {ref}`how-to-python-package`
