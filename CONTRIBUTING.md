# Contributing to charmlibs

This monorepo contains Python libraries for [Juju](https://canonical.com/juju) charms. General libraries are defined in top-level subdirectories, and interface libraries and/or metadata are defined under the interfaces directory.

# Quick start

This project uses [just](https://github.com/casey/just) as a task runner, backed by [uv](https://github.com/astral-sh/uv).

Consider installing them both like this:

```bash
sudo snap install --classic astral-uv
uv tool install rust-just
```

Then run `just` or `just help` from anywhere in the repository for usage.

# Adding a new library

Run `just init` to create a new general library, or `just init --interface` for a new interface library.
We recommend following the [tutorial](https://documentation.ubuntu.com/charmlibs/tutorial) to learn how to add your library to the `charmlibs` monorepo.
If you're migrating a library that was published elsewhere, read the [how-to guide for migrating an existing library to this repository](https://documentation.ubuntu.com/charmlibs/how-to/migrate/).

# Working on an existing library

Run `just check <my package>` to run the primary checks for your package. This runs linting, unit tests, and builds the reference docs:

- `just lint <my package>` runs `ruff`, `codespell`, and `pyright` on your package.
    - `just fast-lint` runs ruff across the whole repository.
    - `just format [package]` will try to automatically fix formatting errors.
    - `just static <package>` runs pyright only.
- `just unit <my package>` runs unit tests.
- `just docs html <my package>` builds the reference docs for `<my package>` only (for speed).
    - `just docs html` or `just docs` will build docs for all packages.

## Adding dependencies

Use `just add <package> <dep>` to add a dependency to a library, rather than calling `uv add` directly. This applies repo-level version constraints from `test-requirements.txt`, keeping the lockfile consistent.

```bash
just add pathops 'pydantic>=2'
```

## Functional and integration tests

`functional` and `integration` tests are also executed in CI, and can be run locally too. They're excluded from `just check` as they may require additional setup:

- `just functional <package>` runs functional tests, which interact with real external processes (but not Juju itself). Some functional test suites may require `sudo` access and may be destructive to the local environment (e.g. installing or removing system packages). Use [Workshop](https://snapcraft.io/workshop) to run them in an isolated container instead of running them directly on your host:

  ```bash
  workshop run resolute -- functional <package>    # Ubuntu 26.04
  workshop run noble -- functional <package>       # Ubuntu 24.04
  workshop run jammy -- functional <package>       # Ubuntu 22.04
  ```

  Extra pytest flags are passed through, e.g. `workshop run noble -- functional snap -x -k test_install`. Workshop configs are in `.workshop/`.

- Integration tests involve packing real test charms and deploying them on a Juju cloud. Pack first with `just pack-k8s <package>` or `just pack-machine <package>`, then run `just integration-k8s <package>` or `just integration-machine <package>`.

Read more: [the different types of tests](https://documentation.ubuntu.com/charmlibs/explanation/charmlibs-tests/).

# Pull requests

PRs are squash-merged, so your PR title becomes the single commit message that lands on `main`. Commit messages on your branch don't need to follow any particular format.

PR titles must follow [conventional commits](https://www.conventionalcommits.org/en/v1.0.0/). When a PR affects a single library, use the distribution package name without the leading `charmlibs-` or `charmlibs-interfaces` as the scope:

```
feat(pathops): add copytree and rmtree
chore(tls-certificates): update to Pydantic v2
```

## Versioning and releases

Libraries are automatically published to PyPI when a merged PR bumps the version to a non-dev version. Dev versions (like `1.0.0.dev0`) are excluded from the release CI, so you can safely merge in-progress work with a dev version.

Any PR that would trigger a release must also update the library's `CHANGELOG.md` — CI will block the merge otherwise.

Read more: [publishing packages from the monorepo](https://documentation.ubuntu.com/charmlibs/explanation/charmlibs-publishing/).
