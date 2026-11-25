# Charmlibs

```{toctree}
:maxdepth: 3
:hidden: false

tutorials/index
how-to/index
reference/index
explanation/index
```

`charmlibs` is the home of Canonical's charm libraries.

If you're searching for a library to use in a charm, check out the library listings to learn which libraries are recommended and where to get them: {ref}`General charm libraries <general-libs-listing>` and {ref}`Charm interface libraries <interface-libs-listing>`. This site also hosts documentation for Python packages in the [charmlibs monorepo](https://github.com/canonical/charmlibs).

If you're new to charms, see {ref}`Juju | Charm <juju:charm>`.

## In this documentation

### Libraries and interfaces

````{domain}
```{slice} Available libraries
{doc}`General libraries <reference/general-libs>`
{doc}`Interface libraries <reference/interface-libs>`
```

```{slice} Use libraries in charms
{doc}`Overview <explanation/charm-libs>`
{doc}`Manage libraries <how-to/manage-libraries>`
```

```{slice} Charmhub-hosted libraries
{doc}`Overview of deprecation <explanation/charmhub-libraries-deprecation>`
{doc}`Use replacements from Charmlibs <how-to/migrate-charm>`
{doc}`Move libraries to Charmlibs <how-to/migrate>`
```

```{slice} Library development
{doc}`Write your first library <tutorial>`
{doc}`Distribute libraries <how-to/python-package>`
{doc}`Provide relation data for charm tests <how-to/provide-relation-data-for-charm-tests>`
{doc}`Add docs <how-to/add-library-docs>` slice
```

```{slice} Interface development
{doc}`Design relation interfaces <how-to/design-relation-interfaces>`
{doc}`Add docs <how-to/document-an-interface>` slice
{doc}`Interface specifications <reference/interfaces>`
```

```{slice} CI
{doc}`Publishing <explanation/charmlibs-publishing>`
{doc}`Testing <explanation/charmlibs-tests>`
{doc}`Customize functional tests <how-to/customize-functional-tests>`
{doc}`Customize integration tests <how-to/customize-integration-tests>`
```
````

### Packages

- {doc}`charmlibs <reference/charmlibs>`
- {doc}`charmlibs.interfaces <reference/charmlibs-interfaces>`

## How this documentation is organised

This documentation uses the [Diátaxis documentation structure](https://diataxis.fr/).

- {doc}`Tutorials <tutorials/index>`
- {doc}`How-to guides <how-to/index>`
- {doc}`Reference <reference/index>`
- {doc}`Explanation <explanation/index>`

## Project and community

Charmlibs is a member of the Ubuntu family. It's an open source project ([Apache license](https://www.apache.org/licenses/LICENSE-2.0)) that warmly welcomes community contributions, suggestions, fixes and constructive feedback.

- [Report a bug](https://github.com/canonical/charmlibs/issues)
- [Contribute](https://github.com/canonical/charmlibs?tab=contributing-ov-file)
- [Code of conduct](https://ubuntu.com/community/ethos/code-of-conduct)

For support, join [Charm Development](https://matrix.to/#/#charmhub-charmdev:ubuntu.com) on Matrix. You'll be able to chat with the maintainers of charmlibs (the Canonical Charm Tech team) and a friendly community of library authors and charm developers!

To follow along with updates and tips about charm development, join our [Discourse forum](https://discourse.charmhub.io/).
