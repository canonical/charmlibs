(charmlibs-tests)=
# Types of tests in the charmlibs monorepo

In addition to static analysis, the `charmlibs` monorepo supports running three distinct kinds of tests: unit, functional, and integration tests.
These are all optional from the perspective of the repository infrastructure, and will be skipped if the corresponding `tests/` directory does not exist.
For example, if `<LIBRARY>/tests/functional` does not exist, then the functional testing job will be skipped for `<LIBRARY>`.

`just <TESTS> <LIBRARY>` will run the tests under `<LIBRARY>/tests/<TESTS>` with `pytest`.
`<TESTS>` is one of unit, functional, or integration.
`<LIBRARY>` is the path from the repository root to the library, for example `pathops` or `interfaces/.example`.

Extra arguments are passed to [pytest](https://docs.pytest.org/en/6.2.x/usage.html). For example:
```bash
just unit pathops -x  # exit on first failure
```
The specific version of `pytest` to run is specified in the repository's `test-requirements.txt`.

```{tip}
`just` commands can be invoked from anywhere in the repository, as they always execute from the location of the `justfile`.
```

## Unit tests

Unit tests are lightweight tests of your library that are fast to run and don't require any additional setup.
They typically mock out the external world so your tests are reproducible and side-effect free.
Execute them locally with:
```bash
just unit <LIBRARY>
```

## Functional tests

Functional tests are intended to be end-to-end tests of everything except the real Juju environment.
Interacting with Juju itself is reserved for integration tests.
Functional tests are most useful for libraries that interact with some significant external component that can be decoupled from the Juju context.
For example, the `apt` and `snap` packages interact with the Ubuntu system's package management tools, which will broadly act the same regardless of whether they're being called from a charm. (For machine charms, at least.)

Execute these tests locally with:
```bash
just functional <LIBRARY>
```
But be careful!
These tests may make changes to your system, and may require `sudo` to run correctly.
For example, the `apt` library's tests require `sudo`, and will install and uninstall `apt` packages.

Before running `pytest`, `just functional <LIBRARY>` will first source `<LIBRARY>/tests/functional/setup.sh` if it exists.
After the tests complete, regardless of whether they passed or failed, `<LIBRARY>/tests/functional/teardown.sh` is sourced.
Finally, the recipe exits with the return code of the `pytest` run.

> Read more: {ref}`how-to-customize-functional-tests`

## Integration tests

Integration tests involve packing one or more real charms that includes your library, deploying them on a real Juju model, and running tests against the deployed charms.
Juju integration tests are slow and can sometimes be a bit flaky, but they're a valuable test that your library works 'for real', and that you understand how it should be used in a charm.
They're worth keeping even if they stay pretty minimal.

Packing the test charms is a separate step, both locally and in CI.
To pack your test charms locally, execute `just pack-k8s <LIBRARY>` or `just pack-machine <LIBRARY>`.
These will execute your `<LIBRARY>/tests/integration/pack.sh` script with the `CHARMLIBS_SUBSTRATE` environment variable set to `k8s` or `machine` respectively.
You'll need to have `charmcraft` installed locally to pack your charms.

After packing your test charms, run your integration tests with `just integration-k8s <LIBRARY>` or `just integration-machine <LIBRARY>`.
These will run the tests under `<LIBRARY>/tests/integration`, selecting either all the tests not marked as `machine_only` or all the tests not marked as `k8s_only` respectively.
You'll need to have a Juju controller set up locally to run your integration tests.
In CI, Juju is set up for you by [concierge](https://github.com/canonical/concierge).

> Read more: {ref}`how-to-customize-integration-tests`
