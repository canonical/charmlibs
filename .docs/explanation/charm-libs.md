(charm-libs)=
# Charm libraries

A charm library is a library developed for use in Juju charms. There are two major ways in which these libraries are categorised: the library's distribution method, and the library's purpose.

(charm-libs-distribution)=
## Library distribution

There are two ways of distributing charm libraries: either as a Python package, or as a single-file module associated with a charm and hosted on Charmhub.

(charm-libs-python-packages)=
### Python package libraries

Python packages use standard formats for metadata, including the package version and the package's dependencies. This allows for precise specification of the version of required package, as well as the specification of version ranges. When your charm is packed, the tooling is able to resolve your charm's dependencies and their dependencies (and so on) into a concrete set of packages - a process called dependency resolution.

In contrast, {ref}`Charmhub-hosted libraries <charm-libs-charmhub-hosted>` are vendored into your charm's codebase, and their dependencies (if any) are manually added to your charm's dependencies.

Include Python packages in your charm by listing their [distribution package name](https://packaging.python.org/en/latest/discussions/distribution-package-vs-import-package/#what-s-a-distribution-package) and any version constraints in your charm's dependencies, typically in `pyproject.toml` or `requirements.txt`. `charmcraft pack` will build these libraries and install them into a virtual environment which is distributed with your packed charm. In your charm code, import the library with its [import package name](https://packaging.python.org/en/latest/discussions/distribution-package-vs-import-package/#what-s-an-import-package).

For example, you might add `charmlibs-pathops>=1` to your dependencies, and then write `from charmlibs import pathops` in `charm.py`.

See also:

- {ref}`how-to-python-package`

(charm-libs-charmhub-hosted)=
### Charmhub-hosted libraries

Charmhub-hosted libraries are live in the namespaces of specific charms. Some libraries use placeholder charms for this, that aren't intended to be deployed.

Each library is a single-file Python module. To use Charmhub-hosted libraries, list them in the {ref}`charm-libs section of charmcraft.yaml <charmcraft:charmcraft-yaml-key-charm-libs>` and then run {doc}`charmcraft fetch-libs <charmcraft:reference/commands/fetch-libs>`. This will download the libraries and place them in `lib/<charm>/v<api-version>/<lib-name>.py`. These files should be committed into your charm's version control.

Charm libraries all have an API version and a patch version, broadly equivalent to the major and minor version in semantic versioning. If a library is specified by API version only then rerunning `charmcraft fetch-libs` will update the library if a newer patch release is available.

The `lib` directory is added to the `PYTHONPATH` by the charm's `dispatch` script, so these libraries are imported in charm code as `$charm.v$api-version.$lib-name`.

For example, you might add this to your `charmcraft.yaml`:

```yaml
charm-libs:
  - lib: operator_libs_linux.snap
    version: "2"
```

And then in your charm code, you would write `from operator_libs_linux.v2 import snap`.

It is recommended that Charmhub-hosted libraries have no additional dependencies, but some do. It's possible that a Charmhub-hosted library might depend on a regular Python package, or it might even depend on another Charmhub-hosted library.

If a library depends on a Python package, the package should be listed in the `PYDEPS` variable in the library itself. You will need to manually add these dependencies to your charm's Python dependencies. For example, if the `snap` library depended on a Python package named `foo` (it doesn't), it might have `PYDEPS = ['foo']`, and you would add `foo` to your dependencies in `pyproject.toml`.

If a library depends on another Charmhub-hosted library, the dependency should be clearly specified in the library's documentation. In this case, you will need to add this additional Charmhub-hosted library to your charm's `charmcraft.yaml` and  run `charmcraft fetch-libs`. For example, if the `snap` library depended on a Charmhub-hosted library `foo.v0.bar`, then you would update your `charmcraft.yaml` to look like this:

```yaml
charm-libs:
  - lib: operator_libs_linux.snap
    version: "2"
  - lib: foo.bar
    version: "0"
```

See also:

- {ref}`Charmcraft | Manage libraries <charmcraft:manage-libraries>`

(charm-libs-purpose)=
## Library purpose

(charm-libs-interface)=
### Interface libraries

An interface library is a special kind of library for interacting with another charm over a defined Juju interface.

A Juju interface is a name associated with one of the {ref}`endpoints <juju:application-endpoint>` that a charm provides or requires. For two charms to be {ref}`integrated <juju:relation>`, they must each have an endpoint with the same interface, with one charm being a requirer and the other a provider. This information is used on Charmhub to show charm users which charms can be integrated with each other.

Under the hood, a relation between two charms typically involves exchanging serialised data using the databags that Juju provides. Charms can read and write this data directly, which is common for peer relations. However, the best practice for managing a relation with another charm to use an interface library. An established interface may also have a schema for the relation data format, which would allow the interface to be reimplemented in another library or even a different language entirely.

To use an interface in your charm, add a requires or provides endpoint to your `charmcraft.yaml` for that interface. Then you'll need to find the interface library for that interface. A good place to start is the {ref}`interface libraries listing <interface-libs-listing>`. You can also visit `charmhub.io/interfaces/<interface name>`, which lists the charms that provide and require the interface. The Charmhub page may present developer documentation for the interface, but you can also look at other charms that implement the interface to see what library they used.

See also:

- {ref}`interface-libs-listing`
- {ref}`Ops | How to manage relations <ops:manage-relations>`
- {ref}`Ops | How to manage interfaces <ops:manage-interfaces>`

(charm-libs-general)=
### General libraries

This category covers all other use cases for libraries, including general-purpose charming helpers and sharing team-specific code between charms. Non-interface libraries may provide everything you need to use them out of the box, like {mod}`pathops` does. Alternatively, they may rely or build on functionality provided by integrating with another charm.

See also:

- {ref}`general-libs-listing`
