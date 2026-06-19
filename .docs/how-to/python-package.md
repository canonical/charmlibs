(how-to-python-package)=
# How to distribute charm libraries

This guide details how you should distribute your charm libraries as Python packages, instead of {doc}`Charmhub-hosted libs <charmcraft:reference/commands/fetch-libs>`.
In future, using Charmhub to host and distribute charm libraries will be deprecated, so new libraries should be created as Python packages instead.

For the purposes of library distribution, there are two kinds of charm libraries:

1. Libraries of broad interest, intended to be used in a wide range of charms. All libraries for *public* interfaces fall into this category. These libraries comprise a key part of the charming ecosystem.

2. Libraries that are domain specific and likely to be used exclusively by a single team. These libraries are considered implementation details of one or more charms.

Libraries of broad interest should be developed in the `charmlibs` monorepo and distributed under the `charmlibs` or `charmlibs.interfaces` namespace on PyPI.

Team-internal libraries should not be published on PyPI under the `charmlibs` namespace.
Instead, consider including such libraries in a shared team package for common code, distributing them as a `git` dependency, or including them as a local dependency (in a charm monorepo).
If none of those options work for you, then you might consider publishing them as generic packages on PyPI.

Read on to learn more about your options for distributing Python packages.

(charmlibs-inclusion)=
## What can I publish under the charmlibs namespace?

The `charmlibs` namespace should only be used by packages published from the `charmlibs` monorepo.
But what packages should be included in this monorepo?

`charmlibs` is for libraries that are likely to be useful to a wide range of charms.
- For {ref}`general libraries <charm-libs-general>`, this means well-scoped libraries providing functionality that would be used by many different charms or libraries.
`charmlibs` isn't for shared code for specific teams' patterns (or specific workloads). Instead, use one of the other distribution methods outlined in this document.
- For {ref}`interface libraries <charm-libs-interface>`, this means libraries for public interfaces that would be used by many different charms. `charmlibs` isn't for interfaces that are intended for communication between (for example) a pair of tightly coupled charms.

New libraries should have a specification with some cross-team buy-in before being added to `charmlibs`.
Ideally, they would implement patterns that have already been tested in production.
For example, you could develop a new library as a sub-package of your team-specific package, use it in your charms, and then migrate it to `charmlibs` when it proves useful in production.

You don't need a specification when migrating a legacy, Charmhub-hosted library of an existing, widely-used interface to `charmlibs`.

To get started with a new `charmlibs` package, follow {doc}`the tutorial </tutorial>`.

(python-package-distribution)=
## Distribute your team's Python package

It may be easiest to begin by distributing your package by sharing a `git` URL.
This avoids some publishing overhead and keeps things tidy.

If your package is developed in the same repo as one or more charms, consider working with the local files, especially during development and testing.
This way, you can test against the latest changes before releasing the next version of your package.

Distributing your package on PyPI allows your users to use dependency ranges.
However, it requires some additional work to publish, so it's best for stable packages that are used across the entire team.

(python-package-distribution-git)=
### Git

You can use GitHub to distribute your library with very little friction.
This is a good fit for libraries that are intended for team-internal use.
It's also very useful when developing a new library or porting a Charmhub-hosted library.

You don't need to do anything special to make your Python package installable with `git` -- just commit it and push to your repository as usual.

> Read more: {ref}`manage-git-dependencies`

(python-package-distribution-local)=
### Local files

If you're developing a Python package in the same repository as a charm, it may be desirable to skip distribution and use the local files when packing the charm, especially for testing.
This allows your tests and IDE to cover the latest changes without needing to release the package first.

`charmcraft pack` won't be able to include the local files unless the library directory is inside the charm directory.
During development, you could copy everything into a temporary packing directory.
However, for distribution, you should make sure that it's possible to `git clone` your repo and immediately run `charmcraft pack` in the charm directory.
We're still working on ways to make this feasible for charm monorepos.

For example, if you had the following structure:

```
$repo/
    $charm/
        src/charm.py
        pyproject.toml
    $package/
        src/charmlibs/$libname/__init__.py
        pyproject.toml
```

Add `$package` to your charm's requirements as normal, depending on whether you'll distribute it via `git` or on PyPI. This will be committed into version control. When it comes time to pack `$charm` for testing, you could do something like this:

```bash
cd $repo
cp -r ./$charm ./pack-$charm
cp -r ./$package ./pack-$charm/
cd ./pack-$charm
uv add ./$package
charmcraft pack
```

To provision virtual environments for development (including linting and unit testing) we can use editable installs. For a `$repo` wide virtual environment for conveniently working on both `$package` and `$charm`, you could do this:

```bash
cd $repo
uv venv
uv pip install -e ./$charm -e ./$package
```

Using editable installs ensures that the virtual environment reflects all changes made to either `$charm` or `$package`. You can then point your editor to the python interpreter in `.venv`, or [activate it manually](https://docs.python.org/3/library/venv.html#how-venvs-work).

To create a virtual environment with a specific python version, use the `--python` flag or define it in a `$repo` level `pyproject.toml`. If you take this approach, a `$repo` level `pyproject.toml` is a good place to put your common dev dependencies like `ruff` and `codespell`. You can remove the created `.venv` directory to start afresh.

If you wanted a virtual environment for `$charm` specifically, you could do:

```bash
cd $charm
uv sync  # install deps from $charm/pyproject.toml
uv pip install -e ../$package
```

Since `$package` doesn't depend on `$charm`, its development virtual environment doesn't require an editable install:

```bash
cd $package
uv sync  # install deps from $package/pyproject.toml
```

The approach should be the same if you have multiple charms, (for example `$charm-kubernetes` and `$charm-machine`), or multiple packages.

(python-package-distribution-pypi)=
### PyPI

To publish a new library on PyPI, set up [trusted publishing](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/#github-actions) on PyPI, and create a GitHub workflow triggered by a version tag. For example:

```yaml
# .github/workflows/publish.yaml
on:
  push:
    tags:
      - 'v*.*.*'
jobs:
  build-n-publish:
    # A dedicated environment for publishing is optional, but recommended.
    # https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments
    environment: pypi
    runs-on: ubuntu-latest
    permissions:
      id-token: write
    steps:
      # Consider pinning to the exact commit hash and updating dependencies with dependabot.
      # https://docs.github.com/en/actions/reference/security/secure-use#using-third-party-actions
      - uses: actions/checkout@v5
      - uses: astral-sh/setup-uv@v7
      - run: uv build
      - uses: pypa/gh-action-pypi-publish@release/v1
```

Make sure that your repository only allows write access from trusted contributors. The team manager and another trusted team member should be the package owners on PyPI, using their Canonical email addresses. Make sure to also claim your package on [Test PyPI](https://test.pypi.org/), and setup a workflow for publishing there. All team members can be owners on Test PyPI.

A major benefit of publishing on PyPI is that users of your library can specify version ranges in their dependencies. Therefore, if you’re going to publish on PyPI, we highly recommend that you use semantic versioning for your library.

A 1.x release to PyPI that doesn't have a qualifier such as dev/alpha/beta signifies that your library is ready for public consumption. You should also communicate this through the ["Development Status" Trove classifier](https://pypi.org/classifiers/) in your `pyproject.toml`.


(python-package-deps)=
## Dependencies

Your library is not required to depend on `ops`. If you do require `ops` as a dependency, specify `ops~=X.Y`, where `X.Y` is the lowest `ops` version that you support.
This evaluates to something like `ops>=X.Y,<X+1`.
This protects your library from breaking changes.
When creating a new library, it’s fine to declare the latest `ops` release as the minimum supported version, as charms are encouraged to always use the latest version of `ops`.

For other dependencies, ideally follow a similar approach: `>=` the lowest version that you need, `<` the next potential (or actual) breaking version. Keeping these dependencies permissive increases the number of charms that will be able to use your library.
