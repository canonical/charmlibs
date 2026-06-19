---
relatedlinks: "[Charmcraft](https://documentation.ubuntu.com/charmcraft/stable/), [Concierge](https://github.com/canonical/concierge), [Jubilant](https://documentation.ubuntu.com/jubilant/), [Juju](https://documentation.ubuntu.com/juju/3.6/), [Ops](https://documentation.ubuntu.com/ops/), [Pebble](https://documentation.ubuntu.com/pebble/)"
---

# Charmlibs

```{toctree}
:maxdepth: 3
:hidden: false

tutorial
how-to/index
reference/index
explanation/index
```

`charmlibs` is the home of Canonical's charm libraries.

If you're searching for a library to use in a charm, check out the library listings to learn which libraries are recommended and where to get them:

- {ref}`General charm libraries<general-libs-listing>`
- {ref}`Charm interface libraries<interface-libs-listing>`

This site also hosts documentation for Python packages in the [charmlibs monorepo](https://github.com/canonical/charmlibs):

- {ref}`reference-charmlibs` - General libraries, imported from `charmlibs` in charm code.
- {ref}`reference-charmlibs-interfaces` - Interface libraries, imported from `charmlibs.interfaces` in charm code.


If you're new to charms, see {ref}`Juju | Charm <juju:charm>`.

## In this documentation

````{grid} 1 1 2 2

```{grid-item-card} [Tutorial](tutorial)
**Start here:** Write your first charm library and contribute it to the monorepo.
```

```{grid-item-card} [How-to guides](how-to/index)
**Step-by-step guides**
- {ref}`Manage charm libraries <how-to-manage-charm-libraries>`
- {ref}`Distribute charm libraries <how-to-python-package>`
- {ref}`Migrate your library to the monorepo <how-to-migrate>`
- {ref}`Customize functional tests <how-to-customize-functional-tests>`
- {ref}`Customize integration tests <how-to-customize-integration-tests>`
```

````

````{grid} 1 1 2 2
:reverse:

```{grid-item-card} [Reference](reference/index)
**Technical information** 
- {ref}`General libraries <general-libs-listing>` and {ref}`interface libraries <interface-libs-listing>`
- {ref}`charmlibs package docs <reference-charmlibs>`
- {ref}`charmlibs.interfaces package docs <reference-charmlibs-interfaces>`
- {ref}`Interface specifications <reference-interfaces>`
```

```{grid-item-card} [Explanation](explanation/index)
**Discussion and clarification** of key topics
- {ref}`Charm libraries <charm-libs>`
- {ref}`Testing packages in the monorepo <charmlibs-tests>`
- {ref}`Publishing packages from the monorepo <charmlibs-publishing>`
```

````

