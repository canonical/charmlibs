# Tutorial

In this tutorial you'll add a new library to the `charmlibs` monorepo.

```{warning}
Check if your library should be distributed via `charmlibs` by reading {ref}`charmlibs-inclusion`.
```

**What you'll need:**

- Your development machine.
- An internet connection.

**What you'll do:**

- Use the `charmlibs` repository tooling to add a new library from the template.
- Get familiar with the repository tooling that will test and release your library.
- Document your library and get approval to add your library to the monorepo.

In this tutorial we'll make a library for retrieving system uptime, but feel free to follow these instructions with your own library.

```{note}
Should you get stuck at any point: Don't hesitate to get in touch on [Matrix](https://matrix.to/#/#charmhub-charmdev:ubuntu.com) or [Discourse](https://discourse.charmhub.io/).
```

## Set up your machine

We'll need [uv](https://github.com/astral-sh/uv) for all our developer commands.
If you don't already have it installed, follow the [uv installation instructions](https://github.com/astral-sh/uv?tab=readme-ov-file#installation), or install the `snap`:
```bash
sudo snap install --classic astral-uv
```

This repository uses [just](https://github.com/casey/just) as a command runner. With `uv` installed, we can install `just` with:
```bash
uv tool install rust-just
```

If you want to run the Juju integration tests locally, you'll also need `charmcraft`installed for packing, as well as a Juju controller for your local K8s or machine clouds.
In CI, these are installed and set up for you using [concierge](https://github.com/canonical/concierge?tab=readme-ov-file#presets), with the `microk8s` and `machine` presets.
The `dev` preset is suitable for local development and testing of both K8s and machine charms, but you may find it easier to run the Juju integration tests in CI when following this tutorial.

> See more:
> - {ref}`Charmcraft | Install charmcraft <charmcraft:manage-charmcraft>`
> - {ref}`Juju | Set up your Juju deployment <juju:set-up-your-deployment>`
> - {ref}`Juju | Set up an isolated environment <juju:set-things-up>`

If you're not already using some alternative authentication for `git push`, you'll also want to [make sure you've set up your Github account with your SSH key](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/adding-a-new-ssh-key-to-your-github-account).

## Create a library from the template

Head to your local copy of your fork of the `charmlibs` monorepo and ensure it's up-to-date.

Alternatively, if you don't already have a fork: [Create a fork](https://github.com/canonical/charmlibs/fork), then run `git clone git@github.com:<USERNAME>/charmlibs.git` to create a local clone of your fork.

In your local clone of your fork, create a new feature branch to add your library. In this tutorial, we'll add a library named `uptime`:
```bash
git checkout -b feat/add-uptime-lib
```

This repository uses `just` as a command runner. You can run `just` from anywhere in the repository to see help on the available commands.
These commands can also be run from anywhere in the repository, as they're always executed in the repository root -- specifically, in the directory where the `justfile` is found.

Get started by running `just init`, and provide the requested information interactively:
- The name of your library (without the `charmlibs-` prefix) -- in this case, `uptime`.
- The minimum Python version you'll support (e.g. `3.10` or `3.12`) -- the default of `3.10` is perfectly fine here.
- The author information to display on PyPI (e.g. `The <YOUR TEAM NAME> team at Canonical`).

````{tip}
If you're working on an interface library, run `just interface init` instead.
This will create the library directory under the `interfaces/` directory and set it up to use the `charmlibs.interfaces` namespace.
````

This creates a new directory for your library, named accordingly.
The library itself just sets `__version__` to `0.0.0.dev0`, and the tests just check the version.

The author and minimum Python version information are easy to change in the generated `pyproject.toml` later. If you change the name of your library, you'll need to change it in a few other locations too, including directory names (`uptime/src/charmlibs/uptime`) and the imports in your tests and test charms.

## Inspect your library

Let's verify that your library has been scaffolded correctly.

Start by running `just lint uptime` from anywhere in the repository.
(`just` commands execute from the `justfile` directory, regardless of where they're run.)
This will run `ruff`, `codespell`, and `pyright` on your library, all of which should pass.
This will also create a `uv.lock` file in your library's directory, which should be included in version control.

Then run `just unit uptime` to verify that your unit tests pass, and `just functional uptime` to check the functional tests.
We'll talk more about Juju integration tests later.

````{tip}
You can verify that everything looks right in an interactive session by installing your library into a virtual environment and running a Python interpreter, for example with:
```bash
uvx --with-editable=./uptime ipython --pdb
```
In the Python shell, import your library:
```python
from charmlibs import uptime
```
You can then run `uptime.__version__` to see the initial `0.0.0.dev0` version string.
````

Assuming everything is working as expected, run `git add uptime` and `git commit` to make a clean starting point for future comparisons.
This should include the `uptime/uv.lock` file that was created by running `just lint uptime`.

## Add a feature

If you have already started prototyping your library, or are porting some existing code, this is a perfect time to add it to the library.
It's a good idea to start small, so you can verify that the basics are all working as expected.
In this tutorial, we'll add a function to return the uptime of the system the charm is running on, using `psutil.boot_time` and `datetime.now`, but feel free to follow along with your own code instead.

We'll start by adding the `psutil` dependency. From anywhere in the repository, run:
```bash
just add uptime psutil
```
If you committed the generated files previously, then running `git diff --stat` should show that your `pyproject.toml` and `uv.lock` files have been updated.

Now we can add the code itself.
`src/charmlibs/uptime/__init__.py` is the file that's executed when your library is imported.
In principle we can put all our library code here, but it's good practice to use separate files (modules) instead, so we can be more intentional about the public interface of our library.

In Python, names prefixed with a single underscore are private.
This isn't enforced technically (a user who knows your library layout can import private symbols), but semantically there are no stability guarantees when using private variables.
`charmlibs` follow semantic verisoning, so if we expose something publicly, we're promising to support it until at least our next major verson.
Let's add a private module where our feature implementation will live.

Create the file `src/charmlibs/uptime/_uptime.py`, then copy the copyright header from `src/charmlibs/uptime/__init__.py` to `_uptime.py`. Next, add the following code to `_uptime.py`:
```python
"""Private module defining the core logic of the uptime package."""

import datetime

import psutil


def uptime() -> datetime.timedelta:
    """Get the uptime for the system where the charm is running."""
    utc = datetime.timezone.utc
    utc_now = datetime.datetime.now(tz=utc)
    utc_boot_time = datetime.datetime.fromtimestamp(psutil.boot_time(), tz=utc)
    return utc_now - utc_boot_time
```
Confirm that you've formatted it correctly with `just lint uptime`, which will also run static type checking for your package.

```{tip}
Automatically format your code with `just format`.

You can optionally run `just format uptime` to confine formatting changes to the `uptime` directory.
```

Currently, the `uptime` function isn't part of our package's public interface.
It *is* a public function, but it's hidden away from our users in a private module.
If the function was intended to be private, it would be a good idea to name it `_uptime` instead, but in this case we want it to be public.

To expose the `uptime` function, add a relative import to `__init__.py` and include `uptime` in `__all__`:

```python
from ._uptime import uptime
from ._version import __version__ as __version__

__all__ = [
    'uptime',
]
```

To test your library in charms outside this repo, consider using a [git dependency](python-package-distribution-git) on your branch, like this:
```bash
uv add git+https://github.com/<USERNAME>/charmlibs@<BRANCH>#subdirectory=uptime
```

In the next sections, we'll add tests to the library to verify it works as intended.

## Test your library

The `charmlibs` monorepo supports three distinct types of tests: unit, functional and integration.
The template starts you off with a simple passing test for each.
We'll add a test of each kind for our `uptime` library in the following sections.

> Read more: {ref}`charmlibs-tests`

### Add unit tests

Running `just unit uptime` uses `pytest` to collect and run any tests defined under your library's `tests/unit` directory.
In this section we'll add a test for our `uptime` function.

We don't really need to mock out `psutil.boot_time`, as it should work perfectly cross-platform, but let's do it anyway for didactic purposes.
Let's assume we want every unit test to use a mock `psutil.boot_time`, as we would for some expensive or dangerous external process.
We'll achieve this with an `autouse` fixture, which will run automatically before every test.

Add the following code to `tests/unit/conftest.py`:
```python
import datetime

import psutil
import pytest


@pytest.fixture(autouse=True)
def mock_boot_time(monkeypatch: pytest.MonkeyPatch) -> None:
    timestamp = datetime.datetime(2004, 10, 20).timestamp()
    monkeypatch.setattr(psutil, 'boot_time', lambda: timestamp)
```

```{warning}
Don't add `pytest` to your `pyproject.toml`.

`just unit uptime` will install and run a specific version of `pytest`, which may clash with the version added in your dependencies.
Instead, use `just` to run tests -- any extra arguments will be passed to `pytest`.
You can point your IDE to `uptime/.venv` after running any of the test commands to have it use the correct virtual environment.
```

Then copy your `tests/unit/test_version.py` file to `tests/unit/test_uptime.py`, and replace the `test_version` function with this:
```python
def test_uptime():
    assert uptime.uptime().total_seconds() > 20 * 365 * 24 * 60 * 60
```

You can also use the `ops.testing` framework to write lightweight tests of your library in a charm.
This is particularly useful if your library observes any events or emits custom events.

Copy `tests/unit/test_version_in_charm.py` to `test_uptime_in_charm.py`, and replace the `test_uptime` function with this:
```python
def test_uptime():
    ctx = ops.testing.Context(Charm, meta={'name': 'charm'})
    with ctx(ctx.on.start(), ops.testing.State()) as manager:
        manager.run()
        assert manager.charm.uptime.total_seconds() > 20 * 365 * 24 * 60 * 60
```

This tests executes code in the `Charm` class, which we also need to update. Replace the `_on_start` method with the following:
```python
def _on_start(self, event: ops.StartEvent):
    self.uptime = uptime.uptime()
```

Now run `just unit uptime` to verify that both tests pass.

````{tip}
If you're working on a real library you intend to open a PR for, you should remove `test_version.py` and `test_version_in_charm.py` once you have some working unit tests of your own.
You should also feel free to split your tests across as many files as needed to keep them organised nicely.
````

For more on `ops.testing`, see:
- [ops.testing reference docs for custom events](ops.testing.CharmEvents.custom)
- [ops.testing how-to for testing that a custom event is emitted](https://documentation.ubuntu.com/ops/latest/howto/manage-libraries/#test-that-the-custom-event-is-emitted)

(tutorial-add-functional-tests)=
### Add functional tests

In this repository, functional tests are essentially integration or end-to-end tests.
In contrast to unit tests, which typically mock out external concerns, functional tests interact with real systems, external processes, and networks.
However, they do not interact with a real Juju environment, which is reserved for tests under the `integration/` directory.

> Read more: {ref}`how-to-customize-functional-tests`

````{tip}
If you're working on an interface library, functional tests probably aren't a good fit, since the main thing the library interacts with is Juju.
In this case, consider dropping functional tests entirely, and focusing on a combination of unit and Juju integration tests.
````

Functional tests for our `uptime` package look similar to the unit tests, but we won't mock anything out.

Copy `tests/functional/test_version.py` to `tests/functional/test_uptime.py` and replace the `test_version` function with this:
```python
def test_hostname():
    assert uptime.uptime().total_seconds() > 0.0
```

Now run `just functional uptime` to verify that our new functional test passes.

Realisticaly, our `uptime` function isn't really a good fit for functional tests, as its interaction with the external world is limited to fast and reliable system calls.
In this case, the library's core functionality would be well exercised by unit tests alone.
We should still use full Juju integration tests to ensure everything is working correctly in the charm context, but in this case we could drop the functional tests altogether by removing the `tests/functional` directory.
The functional tests would then show as skipped in CI.

You may also want to skip functional testing if your library only really makes sense in a charm context, and seems difficult to test outside it.
On the other hand, if your library does interact with or wrap some external process that can be tested outside a charm context, functional tests may be a good fit.

For example, `charmlibs-apt` wraps Ubuntu's `apt` command, and its functional tests install and uninstall real packages.
Another example is `charmlibs-pathops`, which provides a `pathlib`-like API for filesystem operations in K8s charms -- its functional tests interact with a `pebble` instance running and acting on the local system, avoiding the overhead of having Juju create a real pair of charm and workload containers and their `pebble` processes.

In both cases, these tests fully exercise the interesting parts of the library, but are a lot faster than packing the library into a charm and deploying it with Juju.

(tutorial-add-integration-tests)=
### Add integration tests

Integration tests are the most complicated and most heavyweight part of the library testing story.
They involve packing a real charm that includes your library, and deploying it on a real Juju model.
They can be customized in several ways depending on your library's needs.

> Read more: {ref}`how-to-customize-integration-tests`

For now, we'll just add an integration test for our `uptime` function.

We'll start by taking a look at the files that will make up our packed charm, under `tests/integration/charms`.
At the top level are directories for two test charms, with the directory name reflecting the substrate the charm is for: `k8s` and `machine`.
You'll also see some common files which are symlinked into the structure for our two test charms -- these symlinks are resolved by the packing step before `charmcraft pack` is executed.
Taking a look inside one of the charm directories, you can see these symlinks, as well as a unique `charmcraft.yaml` file per substrate, and the usual `src/` directory.
There's also a directory named `library/`, which contains symlinks to your library code and metadata -- this is how the latest changes from your library are made available to these charms.
Under `src/`, you'll see a unique `charm.py` file, and a symlink to `common.py`.

Our `uptime` function should work just as well in a K8s charm as in a machine charm, so we'll test on both substrates, meaning that we don't need to change anything so far.

````{tip}
If you're working on an integration library, the K8s / machine distinction may or may not be important, depending on what information your library needs to populate the databags with.
As long as your library is intended to work on both substrates, it's a good idea to test on both.

However, whether you test on both substrates or just one, you'll definitely want to be packing both a requirer and provider charm.
Consider adding `provider` and `requirer` directories under `tests/integration/charms`, duplicating the existing charm structure in each, updating `pack.sh` to pack both `requirer` and `provider` charms, and deploying both in `conftest.py`.
````

For testing purposes, we'll communicate with the library in our packed charm via a Juju action.
Open `tests/integration/charms/actions.yaml` and add a new action:
```yaml
charm-uptime:
```

We'll also need an observer for this action, which can be the same for both charms, so it can go in the `Charm` base class in `common.py`.
It will look a lot like the handler for `lib-version`, `_on_lib_version`, but we'll serialize the result as a JSON object to preserve its type for our test code.
Open `tests/integraton/charms/common.py` and add this import statement:
```python
import json
```
Then add an observer for our new action to the `Charm` class body:
```python
def _on_charm_uptime(self, event: ops.ActionEvent):
    logger.info('action [charm-uptime] called with params: %s', event.params)
    results = {'uptime': json.dumps(uptime.uptime().total_seconds())}
    event.set_results(results)
    logger.info('action [charm-uptime] set_results: %s', results)
```
And observe the new method in `Charm.__init__`:
```python
framework.observe(self.on['charm-uptime'].action, self._on_charm_uptime)
```

Finally, we'll need a test to exercise this code. Copy `tests/integration/test_version.py`, to `tests/integration/test_uptime.py`, and add this import to `test_uptime.py`:
```python
import json
```
Then replace the `test_version` function with this:
```python
def test_charm_uptime(juju: jubilant.Juju, charm: str):
    result = juju.run(f'{charm}/0', 'charm-uptime')
    uptime_seconds = json.loads(result.results['uptime'])
    assert uptime_seconds > 0.0
```
You'll also want to remove the `from charmlibs import uptime` line since it's now unused, and linting will complain about the unused import.

You can test this locally by running `just pack-k8s uptime` and `just pack-machine uptime` to pack your K8s and machine charms, and then running `just integration-k8s uptime` and `just integration-machine uptime` to deploy the charms on your local Juju K8s and machine clouds and test them.
Note that this will require `charmcraft` installed locally for packing, and a Juju controller available for the K8s or machine clouds.

However, you may find it easier to run the integration tests in CI instead, which is most easily done by opening a pull request.
If you're following along with your own library, then see the next section for how to do this for real.
Otherwise, if you're using the `uptime` example, open a PR against the `main` branch of your fork -- just make sure you enable the workflows first!
You'll be prompted to do this if you visit `https://github.com/<USERNAME>/charmlibs/actions`. 

## Next steps

You can stop here if you're using the `uptime` example.

If you're following along with your own code though, you'll probably want to make a PR to add your library to the `charmlibs` monorepo.
However, there's one important step we must do first: add an entry to the [CODEOWNERS](https://github.com/canonical/charmlibs/blob/main/CODEOWNERS) file.

Scan through `CODEOWNERS` and find the correct place to enter your library alphabetically.
Next, add a line starting with `/<YOUR LIBRARY NAME>/`, followed by a space, and then the name of the team or individuals who will own the library.
Ownership means they can approve PRs that change the files in your library directory -- its code, metadata, tests, and so on.

The `canonical/charmlibs-maintainers` team has owner permissions for the whole repo. They need to approve the initial PR adding the `CODEOWNERS` entry, and they can always approve changes.

Now you can open a PR.
The title should be `feat: add <YOUR LIBRARY NAME> lib`.

Review will automatically be requested from `canonical/charmlibs-maintainers`.
Their review will cover whether the name and purpose of the library is appropriate (for example, not redundant with an existing library), as well as the library's design and general code review.
This type of review will be repeated for major version bumps of your library.
All other releases will only require `CODEOWNERS` approval.

> Read more: {ref}`charmlibs-publishing`
