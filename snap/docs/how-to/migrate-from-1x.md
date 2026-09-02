---
myst:
  html_meta:
    description: Migrate charm code from charmlibs.snap 1.x or operator_libs_linux.v2.snap to charmlibs.snap 2.0.
---

# Migrate from 1.x to 2.0

`charmlibs.snap` 2.0 is a ground-up rewrite. The 1.x library was a straight migration of `operator_libs_linux.v2.snap`; 2.0 is a new, deliberately smaller API. It talks to snapd exclusively over the REST API (it no longer shells out to the `snap` CLI), has no caching layer, and has no runtime dependencies. Function names, argument semantics, and error behaviour follow the `snap` CLI, so what you know from the command line carries over.

This guide describes the 2.0 API in terms of what changed from 1.x, and ends with a table mapping each 1.x name to its replacement. The 1.x series is a drop-in replacement for `operator_libs_linux.v2.snap`, so the same table applies if you're migrating directly from the Charmhub-hosted library.

If you can't migrate yet, pin `charmlibs-snap<2`.

## The new API

Every operation is a module-level function that takes the snap's name. There are no `Snap` objects and no `SnapCache`.

Every name-like argument is validated before a request is made, and an empty or blank name raises `ValueError` rather than reaching snapd.

`ensure_installed(snap, channel=None, *, revision=None, classic=False, update=True)` is the one-call replacement for `ensure`/`add`: it installs the snap if absent, refreshes it if it's on the wrong channel or revision, and otherwise refreshes it only when `update` is true and no revision was requested. `install`, `refresh`, and `ensure_installed` all return a truthy value if something changed and a falsy value otherwise (not guaranteed to be a `bool`). These operations wait for the snapd change to complete, with no overall deadline, like the CLI; a change that finishes in the `Wait` state (for example, one that needs a reboot) is treated as success and logged as a warning.

`get` always returns JSON-typed values (the 1.x `typed=` flag is gone), and always returns a dict keyed by what you asked for; `get_one(snap, key)` returns a single value directly.

`logs` returns structured `LogEntry` objects (`timestamp`, `message`, `sid`, `pid`) in chronological order, rather than a string, and `limit=None` retrieves everything, like `snap logs -n all`.

`hold(snap, duration=None)` accepts a `timedelta` or a number of seconds, and holds indefinitely by default. `InstalledInfo.hold` reports when a hold ends.

## Errors

Every error the library raises is a subclass of `Error`; invalid arguments raise ordinary Python exceptions such as `ValueError`. There are two families:

- Transport errors, for when snapd couldn't be reached or understood: `ConnectionError` (snapd is down; read-only requests are briefly retried, requests that change state are not), `TimeoutError` (snapd didn't answer within the 120s the CLI also allows), and `BadResponseError` (snapd sent something the library can't read; report this to the developers if you see it in the wild). `ConnectionError` and `TimeoutError` also inherit from their builtin namesakes to facilitate generic networking retry logic.
- `APIError`, for an error response from snapd, with specific subclasses for the cases a charm might want to handle: `NotInstalledError`, `NotInStoreError`, `NeedsClassicError`, and so on. Each function documents which errors it can raise.

Where the CLI treats something as a non-error, so does the library: `install` of an already-installed snap, `refresh` with no update available, and `remove` of an uninstalled snap return a falsy value; `unhold` of an unheld or uninstalled snap, `unset` of a key that isn't set, `connect` of an already-connected pair, and a single-sided `disconnect` with nothing connected are silent no-ops.

See the [reference documentation](https://canonical.com/juju/docs/charmlibs/reference/charmlibs/snap) for the full error hierarchy and the errors each function raises.

## Map from 1.x to 2.0

| 1.x | 2.0 |
| --- | --- |
| `SnapCache()[name]`, `Snap(name)` | Pass `name` to the functions below |
| `add(name, ...)`, `ensure(name, ...)`, `Snap.ensure(state, ...)` | `ensure_installed(name, channel, revision=..., classic=...)`, or `install`/`refresh` directly |
| `remove(names)` | `remove(name, purge=...)`, one snap at a time |
| `Snap.present`, `.latest`, `.state`, `.revision`, `.channel`, `.confinement`, `.version`, `.held` | `list_one(name)` returning `InstalledInfo` (`name`, `classic`, `tracking`, `revision`, `version`, `hold`); `NotInstalledError` if absent |
| `Snap.hold(duration)`, `Snap.unhold()` | `hold(name, duration)`, `unhold(name)` |
| `hold_refresh(days, forever)` (system-wide) | `set('system', {'refresh.hold': ...})` |
| `Snap.start(services, enable)`, `.stop(services, disable)`, `.restart(services)` | `start(name, services, enable=...)`, `stop(name, services, disable=...)`, `restart(name, services)` |
| `Snap.restart(reload=True)` | No replacement |
| `Snap.get(key, typed=...)` | `get(name, keys)` returns `{key: value}`; `get_one(name, key)` returns `value`; always typed |
| `Snap.set(config, typed=...)`, `Snap.unset(key)` | `set(name, config)`, `unset(name, keys)` |
| `Snap.connect(plug, service, slot)` | `connect((name, plug), slot)` where `slot` is `(snap, slot)`, a snap name, or `None`; new `disconnect` |
| `Snap.alias(application, alias)` | `alias(name, app, alias)`; new `unalias(alias)` |
| `Snap.logs(services, num_lines)` returning `str` | `logs(names, limit=...)` returning `list[LogEntry]`; filtering by service is not supported |
| `Snap.apps`, `Snap.services`, `SnapClient.get_installed_snaps`, `SnapClient.get_installed_snap_apps` | No replacement |
| `SnapClient.snapd_installed` | Catch `SocketNotFoundError` |
| `install_local(filename, ...)` | No replacement yet |
| `SnapError`, `SnapAPIError`, `SnapNotFoundError` | The `Error` hierarchy above; `SnapNotFoundError` becomes `NotInstalledError` or `NotInStoreError` |
| `SnapState`, `SnapService`, `SnapServiceDict`, `MetaCache`, `JSONAble`, `JSONType`, `ansi_filter` | Removed |
