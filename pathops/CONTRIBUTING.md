# Contributing to charmlibs-pathops

See the repo-level [CONTRIBUTING.md](../CONTRIBUTING.md) for the general monorepo contribution guide.

## Source layout

```
src/charmlibs/pathops/
├── __init__.py          # Public API exports and module docstring
├── _container_path.py   # ContainerPath: Pebble-backed remote path implementation
├── _local_path.py       # LocalPath: pathlib.PosixPath subclass with extended signatures
├── _types.py            # PathProtocol: Protocol definition (type-checking only)
├── _functions.py        # Top-level helpers: ensure_contents
├── _errors.py           # Maps Pebble errors to Python exceptions
├── _constants.py        # Default permission modes
└── _version.txt         # Package version (auto-generated)
```

## Design notes

**`PathProtocol` is a `typing.Protocol`, not an ABC.** It exists to make type annotations work correctly for code that accepts either `ContainerPath` or `LocalPath`. It is defined in `_types.py` and is intended for import for type checking only. `PathProtocol` reflects the implementation of `ContainerPath` and `LocalPath`. User implementations of `PathProtocol` are explicitly not covered by semver. For example, if an argument type is broadened in `ContainerPath` and `LocalPath` (a backwards compatible change), `PathProtocol` would also broaden (a backwards incompatible change for alternative implementations that only support the narrower argument type).

**Default permissions follow Pebble, not pathlib.** `_constants.py` defines `DEFAULT_WRITE_MODE = 0o644` and `DEFAULT_MKDIR_MODE = 0o755`, matching Pebble's defaults. `pathlib` uses `0o666` and `0o777` respectively. This is intentional — `ContainerPath` and `LocalPath` share the same defaults for consistency.

**`_errors.py` maps Pebble errors to standard Python exceptions.** Where possible, `ContainerPath` methods raise standard exceptions (`FileNotFoundError`, `FileExistsError`, `PermissionError`, `OSError`) rather than Pebble-specific errors. `_errors.py` centralises the mapping logic. When adding new `ContainerPath` methods, follow the existing error handling patterns there.

**`ContainerPath` and `LocalPath` must stay in sync.** The `PathProtocol` is updated to reflect the current combined interface of both classes. When adding or changing a method on one class, check whether the same change is needed on the other.

## Testing

Always run:

```bash
just check pathops
```

### Unit tests and type checking

Pathops is very concerned with `pathlib` compatibility across Python versions. Unit tests should be run with the Python versions supported by Ubuntu LTS releases (which charms will run with). Run the unit tests against these versions with:

```bash
just unit --python 3.10 pathops
just unit --python 3.12 pathops
just unit --python 3.14 pathops
```

Also run static analysis the same way to ensure typing compatibility is preserved as intended.
```bash
just static --python <version> pathops
```

Unit tests live under `tests/unit/`. They test `ContainerPath`, `LocalPath`, and `ensure_contents` without a real Pebble instance. `ContainerPath` is constructed using a dummy `ops.Container` backend (see `tests/unit/conftest.py`), and Pebble API calls are monkeypatched using the helpers in `tests/unit/utils.py`.

`tests/typecheck.py` is not a pytest file — it contains statements that verify `ContainerPath` and `LocalPath` implement `PathProtocol` and that `LocalPath` is a valid `pathlib.Path`. These are checked by pyright as part of `just lint pathops` / `just static pathops`.

### Functional tests

```bash
just functional pathops
```

Functional tests live under `tests/functional/` and exercise both `ContainerPath` and `LocalPath` against a real Pebble instance. They require `pebble` to be installed and available in `PATH`.

`tests/functional/setup.sh` starts Pebble with `PEBBLE=/tmp/pebble-test` and `umask 0`. `teardown.sh` kills the process. The `umask 0` setting is important — tests that check file modes will fail if the umask masks bits.

In CI, functional tests run against a matrix of Pebble versions and Ubuntu bases (see `[tool.charmlibs.functional]` in `pyproject.toml`). Locally you'll need to install the Pebble version you want to test against manually.

The functional tests will fail early if `pebble` is unavailable. Pebble can be installed with `snap`:

```bash
sudo snap install --classic pebble
```

### Integration tests

```bash
# First pack the charm(s) if the library or charm code has changed:
# just [pack-k8s|pack-machine]
# CHARMLIBS_TAG must be set to a supported base
env CHARMLIBS_TAG=22.04 just pack-k8s pathops
# Then run the integration tests against a real Juju cloud:
# just [integration-k8s|integration-machine]
just integration-k8s pathops
```

Integration tests deploy real charms against a live Juju model. They require `charmcraft` for packing, and a live Juju controller.

`pack.sh` copies the library's `src/` and `pyproject.toml` directly into a temporary charm directory before calling `charmcraft pack`. The `CHARMLIBS_TAG` environment variable (set to `22.04` or `24.04`, for example) determines which Ubuntu base to pack for. In CI, the integration test matrix runs across the supported bases and substrates.

`tests/integration/test_meta.py` asserts that the `k8s` and `machine` test charms have identical `common.py` files — if this test fails, the charms have drifted and need to be reconciled.
