# charmlibs.interfaces.tls_certificates_testing

The `tls-certificates` testing library. Charms that use `tls-certificates` should use this library in their state-transition tests, so that they don't need to know the underlying relation data format.

To install, add `charmlibs-interfaces-tls-certificates[testing]` to your test dependencies — not `charmlibs-interfaces-tls-certificates-testing` directly, so that the testing package version always matches the library itself. Then in your Python code, import as:

```py
from charmlibs.interfaces import tls_certificates_testing
```

Read more:
- [How to write state-transition tests for your charm](https://canonical.com/juju/docs/charmlibs/how-to/charmlibs/interfaces/tls-certificates/write-state-transition-tests/)
- [Testing package reference](https://canonical.com/juju/docs/charmlibs/reference/testing/charmlibs-interfaces-tls-certificates-testing/)
- [Library reference](https://canonical.com/juju/docs/charmlibs/reference/charmlibs/interfaces/tls-certificates/)
