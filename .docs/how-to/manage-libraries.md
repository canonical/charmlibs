(how-to-manage-charm-libraries)=
# How to manage charm libraries

This guide will walk you through the best practices for using `charmlibs` packages, and other packages from PyPI.

This guide also covers installing Python packages directly from Git repositories, as well as managing legacy Charmhub-hosted libraries.

> {ref}`Learn more about different kinds of charm libraries <charm-libs>`

```{tip}
This guide is for charm developers who want to use libraries.
If you're looking for advice for library developers, take a look at the other how-to guides on this site.
```

## Manage charmlibs packages

`charmlibs` packages are Python [namespace packages](https://packaging.python.org/en/latest/guides/packaging-namespace-packages/).
This means that they're installed as separate _distribution_ packages, but imported from the same `charmlibs` namespace.

For example, `charmlibs-apt` and `charmlibs-snap` are separate packages for the `apt` and `snap` package managers respectively.
You can add them to your dependencies the same way you'd add any other PyPI package.
For example:
```bash
uv add 'charmlibs-apt~=1.0' 'charmlibs-snap~=1.0'
```
This would add two entries to the `dependencies` list in `pyproject.toml`.

In your charm code, you would then import the packages like this:
```python
from charmlibs import apt, snap
```

### Interface libraries

Charm interface libraries are also namespace packages.
The only difference is that they use the `charmlibs.interfaces` namespace instead of the base `charmlibs` namespace.

For example, you could add an interface library to your charm's dependencies:
```bash
uv add 'charmlibs-interfaces-tls-certificates~=1.0'
```
And then import it in your charm code:
```python
from charmlibs.interfaces import tls_certificates
```

### Semantic versioning

`charmlibs` packages all use [semantic versioning](https://packaging.python.org/en/latest/discussions/versioning/#semantic-versioning).
This means that they use a three part version number in the form `<MAJOR>.<MINOR>.<PATCH>`.
A major version of 0 means that the package is in early development and its API might change before the stable 1.0 release.
After the 1.0 release, breaking changes are always accompanied by a major version bump.
A minor version bump indicates new features, while other changes like bugfixes or refactors only require a patch version bump.

A good rule of thumb is to specify your dependency versions as `~=X.Y`, where `X.Y` is the oldest release that has all the features that you need.
This is a shorthand for something like `>=X.Y,<X+1`.
That is, greater than or equal to the version you need, but less than the next major version.
This protects your charm from breaking changes.

On top of this, you should lock your charm's dependencies, commit the lockfile to version control, and use a charm plugin that installs dependencies from the lockfile when packing.
We recommend the [uv plugin](https://canonical-charmcraft.readthedocs-hosted.com/en/stable/reference/plugins/uv_plugin/).

Many packages on PyPI follow semantic versioning, some more closely that others.
If you use locked dependencies, you won't need to worry too much about this, as it will be very clear which version bumps cause breakages -- assuming you have good test coverage!

(manage-git-dependencies)=
## Manage git dependencies

You'll need to include `git` in your charm's build dependencies:

```yaml
parts:
  charm:
    build-packages: [git]
```

Then you can specify the dependency in your requirements. For example:

```
charmlibs-pathops @ git+https://github.com/canonical/charmlibs@main#subdirectory=pathops
```

You can specify any branch, tag, or commit after the `@`. If you leave it off, it will default to `@main`. You can't specify a version range. This can make dependency resolution problematic, especially if the library is depended on by other charm libraries. Tools that scan versions for security vulnerabilities may also struggle with such dependencies.

If the package is in a subdirectory of a repository, as in the `charmlibs-pathops` example, you'll need to specify the subdirectory. If the library has a dedicated repository, leave off the subdirectory and the dependency will default to the repository root.

In `pyproject.toml`, quote the entire string starting `charmlibs-pathops @ git+...` in your dependencies list. Alternatively, use `uv add git+...` to have `uv` add the library to your dependencies list and the `git` reference to `tool.uv.sources`. For `poetry` see [the `poetry` docs](https://python-poetry.org/docs/dependency-specification/#git-dependencies).

The exact commit being referenced should be captured in `uv.lock` and committed to your charm's repository, so that rebuilding a given charm release is consistent.

(manage-charmhub-libraries)=
## Manage legacy Charmhub-hosted libraries

To use Charmhub-hosted libraries, list them in the {ref}`charm-libs section of charmcraft.yaml <charmcraft:charmcraft-yaml-key-charm-libs>` and then run {doc}`charmcraft fetch-libs <charmcraft:reference/commands/fetch-libs>`. This will download the libraries and place them in `lib/<charm>/v<api-version>/<lib-name>.py`. These files should be committed into your charm's version control.

Charm libraries all have an API version and a patch version, broadly equivalent to the major and minor version in semantic versioning. If a library is specified by API version only then rerunning `charmcraft fetch-libs` will update the library if a newer patch release is available.

The `lib` directory is added to the `PYTHONPATH` by the charm's `dispatch` script, so these libraries are imported in charm code as `$charm.v$api-version.$lib-name`.

For example, you might add this to `charmcraft.yaml`:

```yaml
charm-libs:
  - lib: operator_libs_linux.snap
    version: "2"
```

And then in your charm code, you would write `from operator_libs_linux.v2 import snap`.

```{warning}
This is just an example -- don't  really do this! Add `charmlibs-snap` to your dependencies and write `from charmlibs import snap` instead.
```

It is recommended that Charmhub-hosted libraries have no additional dependencies, but some do. It's possible that a Charmhub-hosted library might depend on a regular Python package, or it might even depend on another Charmhub-hosted library.

If a library depends on a Python package, the package should be listed in the `PYDEPS` variable in the library itself. You will need to manually add these dependencies to your charm's Python dependencies. For example, if the `snap` library depended on a Python package named `foo` (it doesn't), it might have `PYDEPS = ['foo']`, and you would add `foo` to your dependencies in `pyproject.toml`.

If a library depends on another Charmhub-hosted library, the dependency should be clearly specified in the library's documentation. In this case, you will need to add this additional Charmhub-hosted library to your charm's `charmcraft.yaml` and  run `charmcraft fetch-libs`. For example, if the `snap` library depended on a Charmhub-hosted library `foo.v0.bar`, then you would update `charmcraft.yaml` to look like this:

```yaml
charm-libs:
  - lib: operator_libs_linux.snap
    version: "2"
  - lib: foo.bar
    version: "0"
```

> Read more:
> - {ref}`charm-libs-charmhub-hosted`
> - {ref}`Charmcraft | Manage libraries <charmcraft:manage-libraries>`
