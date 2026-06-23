# charmlibs

`charmlibs` is the home of Canonical's charm libraries -- Python packages used by [Juju](https://canonical.com/juju) charms.

Charms are Python programs that use the [Ops](https://canonical.com/juju/docs/ops/) framework to manage workloads on Kubernetes or machine clouds. Charm libraries package up common functionality so that teams don't have to reinvent the wheel.

> [!IMPORTANT]
> Each library in this monorepo is distributed as a separate Python package on PyPI, so charms only include what they actually need.

There are two kinds of charm libraries:

- **General libraries** (such as [`charmlibs-apt`](apt/), [`charmlibs-pathops`](pathops/)) provide utility APIs for charms. Imported as `from charmlibs import apt`.
- **Interface libraries** (such as [`charmlibs-interfaces-tls-certificates`](interfaces/tls-certificates/)) manage the structured data that charms exchange over a Juju relation. Imported as `from charmlibs.interfaces import tls_certificates`.

## Contributing to this monorepo

`charmlibs` is for libraries that are broadly useful across different charms and teams. A library is a good fit if it both:

- **Solves a common problem**: It is useful to charms across multiple products or teams, not just your own.
- **Has a design or a proven track record**: Either a specification with cross-team buy-in, or a pattern already tested in production. (Migrating an existing, widely-used Charmhub-hosted library doesn't need a separate specification.)

All public interfaces intended for use by other charms should have a corresponding `charmlibs.interfaces` library.

If your library is more of a team-internal utility, [Distribute charm libraries](https://canonical.com/juju/docs/charmlibs/how-to/python-package/) covers the alternatives.

Got something in mind? You can talk to us on [Matrix](https://matrix.to/#/#charmhub-charmdev:ubuntu.com) before opening a PR — we'd love to hear about it.

**Ready to dive in?** Follow the **[tutorial](https://canonical.com/juju/docs/charmlibs/tutorial)** to add a new library, or the **[migration guide](https://canonical.com/juju/docs/charmlibs/how-to/migrate/)** to port a Charmhub-hosted library. See [CONTRIBUTING.md](./CONTRIBUTING.md) for the developer quick-reference.

For the details of how the monorepo works:

- [Types of tests](https://canonical.com/juju/docs/charmlibs/explanation/charmlibs-tests/): unit, functional, and Juju integration tests
- [Publishing from the monorepo](https://canonical.com/juju/docs/charmlibs/explanation/charmlibs-publishing/): semantic versioning, dev versions, trusted publishing
- Customizing your [functional](https://canonical.com/juju/docs/charmlibs/how-to/customize-functional-tests/) and [integration](https://canonical.com/juju/docs/charmlibs/how-to/customize-integration-tests/) tests.

## Writing charm libraries

[Distribute charm libraries](https://canonical.com/juju/docs/charmlibs/how-to/python-package/) walks through the distribution options for a new library — git dependencies, PyPI, and this monorepo — and how to choose between them.

For interface libraries specifically:

- [Design relation interfaces](https://canonical.com/juju/docs/charmlibs/how-to/design-relation-interfaces/) — rules and patterns for backwards-compatible relation data formats
- [Provide relation data for charm tests](https://canonical.com/juju/docs/charmlibs/how-to/provide-relation-data-for-charm-tests/) — how to write the testing subpackage for your interface library

## Using libraries in a charm

Browse the library listings to find what you need:

- [General library listing](https://canonical.com/juju/docs/charmlibs/reference/general-libs/)
- [Interface library listing](https://canonical.com/juju/docs/charmlibs/reference/interface-libs/)

The [Manage charm libraries](https://canonical.com/juju/docs/charmlibs/how-to/manage-libraries/) guide covers adding a library to your charm, version constraints, git dependencies, and using legacy Charmhub-hosted libraries.

We also host the library reference docs:

- [charmlibs package reference](https://canonical.com/juju/docs/charmlibs/reference/charmlibs/) — `apt`, `pathops`, `snap`, and more
- [charmlibs.interfaces package reference](https://canonical.com/juju/docs/charmlibs/reference/charmlibs-interfaces/) — `tls_certificates`, `tracing`, and more
- [Interface specifications](https://canonical.com/juju/docs/charmlibs/reference/interfaces/) — relation data schemas and docs for each interface

Read more in the docs: [Charm libraries explained](https://canonical.com/juju/docs/charmlibs/explanation/charm-libs/)

---

New to charming? The [ops documentation](https://canonical.com/juju/docs/ops/) is the best place to start.
