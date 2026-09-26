# charmlibs.interfaces.certificate_transfer_testing

The `certificate_transfer` testing library. Charms that use `certificate_transfer` should use this library in their state-transition tests, so that they don't need to know the underlying relation data format.

To install, add `charmlibs-interfaces-certificate-transfer[testing]` to your test dependencies — not `charmlibs-interfaces-certificate-transfer-testing` directly, so that the testing package version always matches the library itself. Then in your Python code, import as:

```py
from charmlibs.interfaces import certificate_transfer_testing
```

Read more:
- [How to use a testing package in state-transition tests](https://canonical.com/juju/docs/charmlibs/how-to/use-a-testing-package/)
- [Testing package reference](https://canonical.com/juju/docs/charmlibs/reference/testing/charmlibs-interfaces-certificate-transfer-testing/)
- [Library reference](https://canonical.com/juju/docs/charmlibs/reference/charmlibs/interfaces/certificate-transfer/)
