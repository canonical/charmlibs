(how-to-migrate)=
# How to migrate to the charmlibs monorepo

This guide will walk you through migrating an existing Charmhub-hosted library to the `charmlibs` monorepo.

```{tip}
This guide is for library authors.
If you're a library user trying to figure out how to switch to the `charmlibs` version of a library, all you need to do is:
1. Delete your vendored copy of the Charmhub-hosted library, remove any references to it in your `charmcraft.yaml`, and remove any transitive dependencies you added.
2. Add the library to your charm as a regular Python dependency (with the appropriate version constraints).
3. Update any imports to refer to the new library -- the library's reference docs should explain this.
```

## Get started

The first thing to check is whether the library you're migrating is an {ref}`interface library <charm-libs-interface>`.
That is, is it responsible for abstracting away the management of a specific interface's databag contents for charms?
If it is, it will be distributed under the `charmlibs.interfaces` namespace instead of the `charmlibs` namespace, and you'll want to think about interface definitions and tests too.

After cloning your fork of the `charmlibs` monorepo, run the following command to add a new directory for your library with an appropriately structured Python package and tests.

`````{tab-set}
````{tab-item} General libraries
:sync: general

```bash
just init
```
````

````{tab-item} Interface libraries
:sync: interface

```bash
just interface init
```
````
`````

You'll be prompted for information about your package, with default values shown in brackets.

The most important piece of information to get right initially is the project name.
This determines the name of your library's project directory, which most of the `just` commands run later in this guide require.
We'll refer to this as `<library path>` in examples.
- For a general library, the project name is the import package name (without the `charmlibs.` namespace).
- For an interface library, the project name is `interfaces/<interface name>`.

Read on for more details about naming and generating your project, depending on whether you're migrating a general library or an interface library.

### General libraries

The project name must be the name of the package as users would type it when they import with:
```python
from charmlibs import <your package name>
```
Typically this should be the `<module name>` component of the Charmhub-hosted lib's name: `<charm name>.v<n>.<module name>`.
For example, `operator_libs_linux.v2.snap` is now available as `charmlibs.snap`.

```{important}
The package name must be unique across the `charmlibs` namespace packages defined in the `charmlibs` monorepo.
This is different from Charmhub, where the name only needed to be unique across the libraries defined by a specific charm.
```

If the name you want to use for your library is already taken, consider the following:
1. Is the functionality you're looking for available from the existing library with the same name?
    1. If not, would it make sense to add it to that library?
    2. If so, perhaps the library you're looking at migrating could be deprecated without migration.
2. Is there another logical name your library could use?

### Interface libraries

The project name must be the canonical name of the interface from the charms' perspective -- exactly as it is spelled in `charmcraft.yaml` files.

This means it might be a hyphenated name or an underscored name.
The important thing is that it exactly matches the actual interface name.

The interface name must be unique across the charming ecosystem -- including the `interfaces/` directory of the monorepo.

If `init` fails because the directory already exists, take a look at the directory.
It may be that the interface definitions are already hosted in the repo under `interfaces/<interface name>/interface`.
In this case:
- Temporarily move the `<interface name>` directory.
- Re-run `just interface init`.
- Then add the `interface` subdirectory to your newly generated project.

You'll also want to check for any config files under the old `<interface name>` directory (for example, a `ruff.toml` file), and incorporate any applicable settings into your project's `pyproject.toml`.

## Migrate your library's code

This is the easy bit, since Charmhub-hosted libs are only a single module.
Download a copy of the latest release of your library, and add it to your new package as a private module, alongside the `__init__.py` file.

`````{tab-set}
````{tab-item} General libraries
:sync: general

```
<library path>/src/charmlibs/<name>/_<name>.py
```
````

````{tab-item} Interface libraries
:sync: interface

```
<library path>/src/charmlibs/interfaces/<name>/_<name>.py
```
````
`````

````{tip}
Add dependencies with the `just add <library path> <args...>` command.
This will automatically respect any repo-level version constraints imposed by the tool versions used in CI.
This uses [uv add](https://docs.astral.sh/uv/reference/cli/#uv-add) under the hood -- any arguments after `<library path>` are passed to it.
For example:
```bash
just add pathops 'pydantic>=2' 'requests~=2.3'
just add interfaces/tls-certificates --requirements my-requirements.txt
```
````

Now follow these steps to migrate your library's source code:
1. Copy the copyright header from `__init__.py` to `_<name>.py` to satisfy the linter.
2. Move the docstring from `_<name>.py` to `__init__.py` so that it's included in your library's automatically built reference docs.
3. Document in the `_<name>.py` docstring the API and patch version of the source code that you're migrating. This will be helpful for future maintainers and users if they need to debug issues.
4. Delete `LIB_ID`, `LIB_API`, and `LIB_PATCH` from `_<name>.py` -- unless they're used internally by the library, then you'll need to keep them for now.
5. Move the contents of `PYDEPS` to the `dependencies` entry in your `pyproject.toml` (using `just add`), and delete the `PYDEPS` variable. You'll also need to add any additional dependencies that were assumed to be provided by the charm, like `ops` or `pydantic`. Consider adding version constraints to your dependencies too.
6. Import the public API of your library to `__init__.py` and add the imported names to `__all__`, like this:
```python
# immediately before or after from ._version
# (imports are sorted alphabetically)
from ._<name> import (
    # your library's public API
)

...

__all__ = [
    # the names we imported, as strings
]
```

You can now test that your library can be built and imported by running the simple unit tests that your project was initialized with.
From anywhere in the repo, run the following command:

```bash
just unit <library path>
```

```{tip}
Commit your code now if you haven't already!
```

To be merged, your library will need to comply with the repo's linting and static type checking.
Check how you're doing by running:

```bash
just lint <library path>
```

Consider running `just format` to handle any automatically fixable errors.

You can also check if your docstrings are compatible with the format that Sphinx expects when building the reference docs.
From anywhere in the repo, run `just docs`.
This builds the reference docs for all the libraries.
To speed things up, only build the reference docs for your library:

```bash
just docs html <library path>
```

## Migrate your library's tests

This part is a bit trickier.
With any luck, your library was previously developed in a placeholder charm that exists purely for library distribution.
If your library's development and testing was tightly coupled to a real charm, this step will be more involved.
You'll need to consider which tests can live alongside the library, and which only make sense with the charm.
You might want to add a simplified dummy charm to run some of the tests against.

```{warning}
Don't add `pytest` to your `pyproject.toml`.

`just unit <library path>` will install and run a specific version of `pytest`, which may clash with the version added in your dependencies.
Instead, use `just` to run tests -- any extra arguments will be passed to `pytest`.
You can point your IDE to `uptime/.venv` after running any of the test commands to have it use the correct virtual environment.
```

### Unit tests

If your library wasn't tightly coupled to a real charm, these steps should be sufficient:

1. Add any unit test dependencies to the `unit` dependency group in your `pyproject.toml` (using `just add`).
2. Copy any relevant contents of your `conftest.py` to `tests/unit/conftest.py`.
3. Copy your library's existing unit test files to `tests/unit/`, along with any data files, dummy charms, and so on.
4. Correct the imports in those files.

Replace imports like this:
```python
from charms.<charm>.v<n> import <name>
from charms.<charm>.v<n>.<name> import ...
```
With imports like this:
`````{tab-set}
````{tab-item} General libraries
:sync: general

```python
from charmlibs import <name>
from charmlibs.<name> import ...
```
````

````{tab-item} Interface libraries
:sync: interface

```python
from charmlibs.interfaces import <name>
from charmlibs.interfaces.<name> import ...
```
````
`````

There's now a good chance that the following command will successfully run your unit tests!

```bash
just unit <library path>
```

### Functional tests

While unit tests are run across a selection of the Python versions that your library supports,
functional tests are run on different Ubuntu bases using the system Python.
They're intended for tests that interact with the real world, but don't require a real Juju deployment.

The process for migrating them is exactly the same as for unit tests.

> Read more: {ref}`tutorial-add-functional-tests`, {ref}`charmlibs-functional-tests`

### Integration tests

Integration tests involve packing your library into a charm and deploying it on a real Juju model.

> Read more: {ref}`tutorial-add-integration-tests`, {ref}`charmlibs-integration-tests`

If you take a look at your `<library path>/tests/integration` directory, you'll see a `pack.sh` script.
Currently it packs a simple `k8s` or `machine` charm, depending on the `CHARMLIBS_SUBSTRATE` variable that is set in CI.
In CI, the script is executed by `just pack-k8s` or `just pack-machine`.
The integration tests provided by the template use `jubilant` to deploy and test the packed charm.
They're executed by `just integration-k8s` or `just integration-machine`.

The simple `k8s` and `machine` charms are defined in the `<library path>/tests/integration/charms` directory.
You're more than welcome to fit your existing integration tests into this structure.
However, the use of the `pack.sh` script is completely optional -- you're free to remove it entirely, in which case that step is skipped in CI.
This is especially useful if your integration tests used `pytest-operator` to pack and deploy charms from the tests themselves.

In CI, integration tests are run (separately) with a Juju machine cloud and a Juju K8s cloud.
The `charmlibs` CI is aware of two special `pytest` marks: `k8s_only` and `machine_only`.
If there are no tests compatible with a substrate, then it's skipped completely.
By default each test is treated as compatible with both substrates.

## Migrate your library's docs

Your library's reference documentation is automatically built from its docstrings and source code.

```{warning}
🚧 Actually including the docs described below in this documentation site is coming soon™ 🚧
```

Additional documentation may be placed under `<library path>/docs`, and will be included in this documentation site under the respective categories.
The following files are consumed.
```
docs
├── explanation
│   └── *.{md,rst}
├── how-to
│   └── *.{md,rst}
├── reference
│   └── *.{md,rst}
└── tutorial.{md,rst}
```

## Deprecate the old library

When migrating an existing Charmhub-hosted library, our recommendation is to do a bug-for-bug migration of the latest release.
The new `charmlibs` package should be released as version `1.0.0`, indicating that the API is stable.
This will make it as easy as possible for users to migrate.

You will need to provide critical security and bug fixes for the Charmhub-hosted library for some time,
but you should immediately mark it as deprecated by adding a prominent comment to the docstring and releasing a new patch version of the library.
You should also announce the deprecation in your team's usual communication channels.
You're free to continue to provide feature updates, but users should not expect them. You should encourage users to migrate to get feature updates.

Don't add deprecation warnings to the code -- we don't want to flood the Juju logs with warnings.
Likewise, don't remove the library code -- we want old charms using `charmcraft fetch-libs` in their build process to continue to work.
