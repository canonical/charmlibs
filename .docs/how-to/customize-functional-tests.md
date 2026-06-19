(how-to-customize-functional-tests)=
# How to customize your functional tests

Functional tests are executed much like your unit tests, but they provide more entry points for customisation to accommodate the need to interact with external processes.

> Read more: {ref}`charmlibs-tests`

Functional tests are only executed if the `<LIBRARY>/tests/functional` directory exists.
If you don't need functional tests, remove the directory.

There are two entry points for customization: your library's `pyproject.toml` file, and `setup.sh` and `teardown.sh` files in your `tests/functional` directory.

## Customizing CI

How your functional tests are executed in CI can be customised by editing this section of your library's `pyproject.toml` file (it has no effect if `tests/functional` is removed):

```toml
[tool.charmlibs.functional]
```

There are currently three supported variables:
- `ubuntu` is a list of Ubuntu bases, for example `["22.04", "24.04"]`.
    - This is used to run your functional tests in a matrix in CI, with the operating system set as `ubuntu@<YOUR VERSION>`.
    - By default, your tests are run once with `ubuntu@latest`.
    - If you want to run your tests against multiple bases locally, consider using virtual machines.
- `pebble` is a list of [Pebble version tags](https://github.com/canonical/pebble/tags), for example `["v1.24.0"]`.
    - If specified, the Pebble version will be an additional row in the matrix your functional tests are run with, with the corresponding Pebble version installed.
    - By default, your tests are run once without Pebble installed.
    - For an example of how to start and stop Pebble for your functional tests, see [pathops/tests/functional](https://github.com/canonical/charmlibs/tree/main/pathops/tests/functional).
    - For local testing, you'll need to manually install the version of Pebble that you want to test against.
- `sudo` is a Boolean option, defaulting to `false`.
    - If it's `true`, your tests are run in CI with `sudo` permissions in their ephemeral runner.
    - If your tests require `sudo` privileges, you'll need to manage that locally yourself, for example by testing in a virtual machine.

If your library needs another piece of software like `pebble` installed for its functional tests, get in touch with us on [Matrix](https://matrix.to/#/#charmhub-charmdev:ubuntu.com) or [open an issue](https://github.com/canonical/charmlibs/issues/new) about the option to install it in CI.

## Customizing setup and teardown

When `just functional <LIBRARY>` is executed locally or in CI, `<LIBRARY>/tests/functional/setup.sh` will be sourced before running any tests (if it exists).
After the tests complete, regardless of whether they passed or failed, `<LIBRARY>/tests/functional/teardown.sh` is sourced.
For example, `pathops` uses these scripts to start a `pebble` instance and kill it after the tests have completed.

## Examples

- `charmlibs-pathops`
    - [pyproject.toml](https://github.com/canonical/charmlibs/blob/main/pathops/pyproject.toml) with Pebble and Ubuntu versions configured in `tool.charmlibs.functional`.
    - [setup.sh](https://github.com/canonical/charmlibs/blob/main/pathops/tests/functional/setup.sh) and [teardown.sh](https://github.com/canonical/charmlibs/blob/main/pathops/tests/functional/teardown.sh) that start Pebble, record its PID, and then kill it after tests have run.
- `charmlibs-snap`
    - [pyproject.toml](https://github.com/canonical/charmlibs/blob/main/snap/pyproject.toml) with Ubuntu versions configured and `sudo = true`.
