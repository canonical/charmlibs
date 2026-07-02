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
We recommend following the [tutorial](https://canonical.com/juju/docs/charmlibs/tutorial) to learn how to add your library to the `charmlibs` monorepo.
If you're migrating a library that was published elsewhere, read the [how-to guide for migrating an existing library to this repository](https://canonical.com/juju/docs/charmlibs/how-to/migrate/).

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
  workshop exec resolute -- sudo just functional <package>    # Ubuntu 26.04
  workshop exec noble -- sudo just functional <package>       # Ubuntu 24.04
  workshop exec jammy -- sudo just functional <package>       # Ubuntu 22.04
  ```

  Extra pytest flags are passed through, e.g. `workshop exec noble -- sudo just functional snap -x -k test_install`. Workshop configs are in `.workshop/`.

- Integration tests involve packing real test charms and deploying them on a Juju cloud. Pack first with `just pack-k8s <package>` or `just pack-machine <package>`, then run `just integration-k8s <package>` or `just integration-machine <package>`.

Read more: [the different types of tests](https://canonical.com/juju/docs/charmlibs/explanation/charmlibs-tests/).

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

Read more: [publishing packages from the monorepo](https://canonical.com/juju/docs/charmlibs/explanation/charmlibs-publishing/).

# Documentation

The documentation site published at [canonical.com/juju/docs/charmlibs](https://canonical.com/juju/docs/charmlibs) is built with [Sphinx](https://www.sphinx-doc.org/) from the source in the `.docs/` directory. It combines three kinds of content:

- **Hand-written diataxis pages** (tutorials, how-to guides, and explanations) authored in `.docs/`, plus per-library pages that live in each library's own `docs/` directory.
- **Reference docs** generated automatically from your library's docstrings via Sphinx [autodoc](https://www.sphinx-doc.org/en/master/usage/extensions/autodoc.html). The module docstring in your package's `__init__.py` becomes the top-level description for that library's reference page.
- **Interface specification docs** generated from the versioned `README.md` files in each interface's `interface/` directory. These describe the relation interface contract itself (separately from the `charmlibs.interfaces` Python package reference, which is generated from docstrings like any other library).

## Building the docs

All docs commands are exposed under the `docs` module of `just`. Run `just docs help` to list them.

```bash
just docs html <package>   # build docs, generating reference docs for <package> only (fast)
just docs html             # build everything, including reference docs for all packages
just docs                  # alias for `just docs html`
just docs html -           # build the site with no package reference docs (fastest; for editing prose only)
```

`just docs html <package>` is also run as part of `just check <package>`, so building the reference docs for your library happens automatically when you run the standard pre-commit check.

## How the build works

The build is intentionally multi-pass, because different libraries can have conflicting dependencies and we can't install them all into a single Sphinx environment:

1. **Diataxis preprocessing.** The `.docs/scripts/diataxis_preprocessor.py` script runs first. It walks every library, copies any `docs/` pages into the Sphinx source tree, and generates the `_lib-*.md` toctree include files that the category index pages pull in.
2. **Per-package reference passes.** `sphinx-build` is invoked once per package, each time with that package installed into an isolated `uvx` environment and the `package=<name>` config option set. Each pass runs autodoc against a single library and saves its resolved doctree and index information to disk. Reference warnings are suppressed during these passes because cross-references to other libraries aren't available yet.
3. **Final combined pass.** A final `sphinx-build` runs with no `package` set. It restores the per-package reference docs saved in step 2, generates the interface specification pages, combines everything with the hand-written pages, and produces the complete HTML site (and `llms.txt`).

The logic for steps 2 and 3 lives in the local Sphinx extensions under `.docs/extensions/`, which are registered in `.docs/conf.py`. In particular:

- `package_docs.py` drives the per-package autodoc passes and saves/restores each library's reference doctree.
- `interface_docs.py` generates the interface specification pages. During the final pass it reads the interface `README.md` files, rewrites relative links to point at the repo on GitHub, and writes the pages under `reference/interfaces/`. (During the per-package passes it only writes a placeholder so the toctree glob doesn't fail.)

## Writing library docs

Reference docs are generated from docstrings, so anything you write in your public API's docstrings appears verbatim in the published reference. Keep them informative for library users rather than implementation notes.

For adding tutorials, how-to guides, and explanations specific to your library, see the [how-to guide for adding docs to a library](https://canonical.com/juju/docs/charmlibs/how-to/add-library-docs/).

## Working on the docs extensions

The local Sphinx extensions are covered by linting, and have their own tests and static analysis:

```bash
just fast-lint .docs   # run ruff for content under .docs/
just docs ext-unit     # run unit tests under .docs/tests
just docs ext-static   # run pyright over the local Sphinx extensions and tests
```
