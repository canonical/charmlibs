---
myst:
  html_meta:
    description: Migrate your charm from the Charmhub-hosted charms.smtp_integrator.v0.smtp library to the charmlibs-interfaces-smtp package.
---

# Migrate from the Charmhub-hosted library

The `charmlibs.interfaces.smtp` package is a bug-for-bug migration of the Charmhub-hosted library `charms.smtp_integrator.v0.smtp` (LIBPATCH 21). The API is unchanged, so migrating only involves changing how the library is installed and imported.

1. Delete your vendored copy of the library at `lib/charms/smtp_integrator/v0/smtp.py`, and remove it from the `charm-libs` section of your `charmcraft.yaml`.

2. Remove `pydantic` and `email-validator` from your charm's dependencies if you only added them for this library. They are now transitive dependencies of the package.

3. Add the package as a regular Python dependency of your charm, for example:

    ```
    charmlibs-interfaces-smtp>=1,<2
    ```

4. Update your imports:

    ```python
    # Before
    from charms.smtp_integrator.v0 import smtp
    from charms.smtp_integrator.v0.smtp import SmtpRequires

    # After
    from charmlibs.interfaces import smtp
    from charmlibs.interfaces.smtp import SmtpRequires
    ```

The `smtp` and `smtp-legacy` relation names, the relation data format, and the events emitted by the library are unchanged.
