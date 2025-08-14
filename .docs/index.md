# Charmlibs

```{toctree}
:maxdepth: 3
:hidden: false

how-to/index
reference/index
explanation/index
```

This is the Charm Tech team at Canonical's documentation website for charm libraries. It hosts the documentation for the team's charm libraries that are distributed as Python packages, as well as general documentation about charm libraries.

You can also read our {ref}`guidance on distributing charm libraries as Python packages <how-to-python-package>`.

If you're new to charms, see {ref}`Juju | Charm <juju:charm>`.

## Pathops

Pathops is a Python package that provides a {doc}`pathlib <python:library/pathlib>`-like interface for both local filesystem and Kubernetes workload container paths. Charms can use [ContainerPath](pathops.ContainerPath) to interact with files in the workload container, or [LocalPath](pathops.LocalPath) to interact with local files using the same API. Code designed to work for both cases can use [PathProtocol](pathops.PathProtocol) in type annotations.

Pathops is [available on PyPI](https://pypi.org/project/charmlibs-pathops) with examples of how to get started. You can also read the [full reference documentation](pathops).
