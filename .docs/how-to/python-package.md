(how-to-python-package)=
# How to distribute charm libraries

```{warning}
This guide has not yet been updated to reflect the latest recommendations: all new charm libraries intended for wide use should be developed as Python packages in the `charmlibs` monorepo and distributed on PyPI under the `charmlibs` namespace. Likewise for interface libraries, but distributed under the `charmlibs.interfaces` namespace. Charmhub-hosted libraries will be deprecated going forward.
```

This guide details when and how you should create your charm libraries as Python packages, instead of {doc}`Charmcraft-style charm libs <charmcraft:reference/commands/fetch-libs>`.


(when-to-python-package)=
## When to use a Python package

You should use a Python package for your charm library if:

- The library relies on any dependencies other than `ops` and the Python standard library.

- The library will be difficult to manage as a single file.

- The library isn't logically associated with a single charm.

- You need to share modules between the machine and Kubernetes versions of a charm.

For a relation library, the current recommendation is still to use a Charmcraft lib where possible. This is an especially good fit if the library is associated with a single charm. There's also infrastructure and documentation that supports this pattern. However, even in this case, if your relation library needs additional dependencies it would be better to distribute it as a Python package.


(python-package-name)=
## Naming and namespacing your Python package

If your library is a Python package, for public use, and addresses charming-specific concerns, make the library a [namespace package](https://packaging.python.org/en/latest/guides/packaging-namespace-packages/) using the `charmlibs` namespace. The distribution package name should be `charmlibs-$libname`, imported as `from charmlibs import $libname`.

If you have a dedicated repository for the charmlib, we recommend naming it `charmlibs-$libname`. For a repository containing several libraries, consider naming the repository `$teamname-charmlibs`.

```{important}
Don't use the `ops` or `charm` namespaces for your libraries. It will be easier for charmers to follow your code if the `ops` namespace is reserved for the `ops` package. Likewise, the `charms` namespace is best left for charmcraft managed libs.
```

If your library should only be used by your own charms, you don't need to publish it to PyPI. In this case, you don't need to use the `charmlibs` namespace either, but feel free to do so if it's helpful. [](#python-package-distribution) suggests alternative distribution methods for this case.


(namespace-package)=
### Making a namespace package
To make a namespace package, nest your package in an empty directory with the namespace name, in this case `charmlibs`. For example, the file structure for your library might look like this:

```
src/
  charmlibs/
    $libname/
      __init__.py
      ...
tests/
  unit/
  integration/
pyproject.toml
```

The `charmlibs` folder must not contain an `__init__.py` file. Likewise, there is no need to install an actual package named `charmlibs` -- this package does exist on PyPI, but solely to reserve the package name as a namespace for charm libraries, and to make charm library documentation easier to find.


(python-package-distribution)=
## How to distribute your Python package

Distributing your package on PyPI allows your users to use dependency ranges, improves discoverability, and makes it easier for users to install your library. However, it requires some additional work to publish, and is most appropriate if your library is intended for public use.

During development and team internal use, you may find it useful to begin by distributing your package by sharing a git URL. If your library is purely for your own charms and not intended for external users, a git dependency avoids some publishing overhead.

If your package is developed in the same repo as one or more charms, consider working with the local files during development and testing. This way, you can test against the latest changes before releasing the next version of your package.


(python-package-distribution-pypi)=
### PyPI

To publish your library on PyPI, set up [trusted publishing](https://docs.pypi.org/trusted-publishers/) on PyPI, and create a GitHub workflow triggered by a version tag. For example:

```yaml
# .github/workflows/publish.yaml
on:
  push:
    tags:
      - 'v*.*.*'
jobs:
  build-n-publish:
    environment: pypi
    runs-on: ubuntu-latest
    permissions:
      id-token: write
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv build
      - uses: pypa/gh-action-pypi-publish@release/v1
```

Make sure that your repository only allows write access from trusted contributors. The team manager and another trusted team member should be the package owners on PyPI, using their Canonical email addresses. Make sure to also claim your package on [Test PyPI](https://test.pypi.org/), and setup a workflow for publishing there. All team members can be owners on Test PyPI.

A major benefit of publishing on PyPI is that users of your library can specify version ranges in their dependencies. Therefore, if you’re going to publish on PyPI, we highly recommend that you use semantic versioning for your library.

A 1.x release to PyPI that isn't qualified with dev/alpha/beta/etc signifies that your library is ready for public consumption. You should also communicate this through the ["Development Status" Trove classifier](https://pypi.org/classifiers/) in your `pyproject.toml`.


(python-package-distribution-git)=
### Git

You can get started by distributing your library as a Python package with very little friction using GitHub. This is good for prototyping, or when first transitioning from a charmcraft-style library to a Python package, and may be a good fit for libraries that are intended for team-internal use. If your library is intended for external users, consider whether PyPI would be a better choice.

You’ll need to include `git` in your charm’s build dependencies:

```yaml
parts:
  charm:
    build-packages: [git]
```

Then you can specify the dependency in your requirements:

```
charmlibs-pathops @ git+https://github.com/canonical/charmtech-charmlibs@main#subdirectory=pathops
```

You can specify any branch, tag, or commit after the `@`. If you leave it off, it will default to `@main`. You can’t specify a version range. This can make dependency resolution problematic for users, especially if your library is depended on by other charm libraries. Tools that scan versions for security vulnerabilities may also struggle with such dependencies.

If your package is in a subdirectory of your repository, for example in a monorepo (like the example above), or when developing libraries alongside charms, you'll need to specify the subdirectory. If your library has a dedicated repository, leave off the subdirectory and it will default to the repository root.

In `pyproject.toml`, quote the entire string starting `charmlibs-pathops @ git+...` in your dependencies list. Alternatively, use `uv add git+...` to have `uv` add `charmlibs-pathops` to your dependencies list and the git reference to `tool.uv.sources`. For `poetry` see [the `poetry` docs](https://python-poetry.org/docs/dependency-specification/#git-dependencies).


(python-package-distribution-local)=
### Local files for testing

If you're developing a Python package in the same repository as a charm, it may be desirable to skip distribution and use the local files when packing the charm for testing. This allows your tests and IDE to cover the latest changes without needing to release the package first.

`charmcraft pack` won't be able to include the local files unless the library directory is inside the charm directory. During development, you could copy everything into a temporary packing directory. However, for distribution, you should make sure that it's possible to `git clone` your repo and immediately run `charmcraft pack` in the charm directory.

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


(python-package-deps)=
## Dependencies

Your library is not required to depend on `ops`. If you do require `ops` as a dependency, specify `ops>=2.X,<3`, where 2.X is the lowest `ops` version that you support, and 3 is the next major version of `ops`. This protects your library from breaking changes. When creating a new library, it’s fine to declare the latest `ops` release as the minimum supported version, as charms are encouraged to always use the latest version of `ops`.

For other dependencies, ideally follow a similar approach: `>=` the lowest version that you need, `<` the next potential (or actual) breaking version. Keeping these dependencies permissive increases the number of charms that will be able to use your library.
