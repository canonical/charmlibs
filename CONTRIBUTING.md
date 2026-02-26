# Quick start

This project uses [just](https://github.com/casey/just) as a task runner, backed by [uv](https://github.com/astral-sh/uv).

Consider installing them both like this:

```bash
sudo snap install --classic astral-uv
uv tool install rust-just
```

Then run `just` from anywhere in the repository for usage.

# Adding a new library

Follow the [tutorial](https://documentation.ubuntu.com/charmlibs/tutorial) to learn how to add your library to the `charmlibs` monorepo, or read the [how-to guide for migrating an existing library to this repository](https://documentation.ubuntu.com/charmlibs/how-to/migrate/).

# Working on an existing library

Run `just check <my package>` to run the following tests for your package:

- `just lint <my package>` runs linters and static type checkers.
    - `just fast-lint` will run fast linters for all packages.
    - `just format <my package>` or `just format` will try to automatically fix errors.
- `just docs html <my package>` builds the docs, only including reference docs for `<my package>` (for speed).
    - `just docs html` or `just docs` will build docs for all packages.
- `just unit <my package>` runs unit tests.

`functional` and `integration` tests are also executed in CI, and can be executed locally too.

Read more:

- [The different types of tests](https://documentation.ubuntu.com/charmlibs/explanation/charmlibs-tests/).
- [Publishing packages](https://documentation.ubuntu.com/charmlibs/explanation/charmlibs-publishing/).

# Pull requests

Pull request titles must follow [conventional commits](https://www.conventionalcommits.org/en/v1.0.0/).
When working on a single library, use the scope to indicate this.
The scope should be the distribution package name without the leading `charmlibs-`.
For example:
`feat(pathops): ...`, `chore(interfaces-tls-certificates).
