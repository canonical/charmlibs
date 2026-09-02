# 2.0.0 - 31 August 2026

A ground-up rewrite of `charmlibs.snap`. The 1.x library was a straight migration of `operator_libs_linux.v2.snap`; 2.0 is a new, deliberately smaller API. It talks to snapd exclusively over the REST API (it no longer shells out to the `snap` CLI), has no caching layer, and has no runtime dependencies (the `opentelemetry-api` dependency and its tracing are gone). Function names, argument semantics, and error behaviour follow the `snap` CLI, so what you know from the command line carries over.

If you can't migrate yet, pin `charmlibs-snap<2`. The 1.x series remains the drop-in replacement for `operator_libs_linux.v2.snap`.

## The new API

Every operation is a module-level function that takes the snap's name. There are no `Snap` objects and no `SnapCache`.

- Installation: `ensure_installed`, `install`, `refresh`, `remove`, and `list_one` (which returns an `InstalledInfo`).
- Automatic refreshes: `hold` and `unhold`.
- Services: `start`, `stop`, and `restart`.
- Configuration: `get`, `get_one`, `set`, and `unset`.
- Interfaces: `connect` and `disconnect`.
- Aliases: `alias` and `unalias`.
- Logs: `logs`, which returns a list of `LogEntry` objects.

Wherever the CLI accepts several names, the library accepts either a single string or an iterable of strings (`start('lxd', 'daemon')` or `start('lxd', ['daemon', 'user-daemon'])`). `None` means "all" where the CLI has such a notion, and an empty iterable means "none": `start('lxd', [])` makes no request (but still raises if `lxd` isn't installed), and `logs([])` returns `[]`.

Every name-like argument is validated before a request is made, and an empty or blank name raises `ValueError` rather than reaching snapd, where it would be silently reinterpreted (an empty snap name used to make `get` return `{}` for an uninstalled snap instead of raising).

`ensure_installed(snap, channel=None, *, revision=None, classic=False, update=True)` is the one-call replacement for `ensure`/`add`: it installs the snap if absent, refreshes it if it's on the wrong channel or revision, and otherwise refreshes it only when `update` is true and no revision was requested. `install`, `refresh`, and `ensure_installed` all return a truthy value if something changed and a falsy value otherwise (not guaranteed to be a `bool`). These operations wait for the snapd change to complete, with no overall deadline, like the CLI; a change that finishes in the `Wait` state (for example, one that needs a reboot) is treated as success and logged as a warning.

`channel` and `revision` may be given together: snapd verifies the revision is available on that channel, installs it, and tracks that channel. A revision on its own isn't a pin: the next refresh moves the snap to the current revision of whatever channel it tracks (`latest/stable` for a fresh install), so combine `revision` with `hold` to keep it. A channel that is only a risk (`edge`) inherits the installed snap's track.

`get` always returns JSON-typed values (the 1.x `typed=` flag is gone), and always returns a dict keyed by what you asked for; `get_one(snap, key)` returns a single value directly. `set` takes a mapping and accepts `None` to unset a key.

`logs` returns structured `LogEntry` objects (`timestamp`, `message`, `sid`, `pid`) in chronological order, rather than a string, and `limit=None` retrieves everything, like `snap logs -n all`.

`hold(snap, duration=None)` accepts a `timedelta` or a number of seconds, and holds indefinitely by default. `InstalledInfo.hold` reports when a hold ends.

## Errors

Every error the library raises is a subclass of `Error`; invalid arguments raise ordinary Python exceptions such as `ValueError`. There are two families:

- Transport errors, for when snapd couldn't be reached or understood: `ConnectionError` (snapd is down; read-only requests are briefly retried, requests that change state are not), its subclass `SocketNotFoundError` (the socket doesn't exist, so snapd is probably not installed; never retried), `TimeoutError` (snapd didn't answer within the 120s the CLI also allows), and `BadResponseError` (snapd sent something the library can't read; its message includes the response so a traceback is enough for a bug report). `ConnectionError` and `TimeoutError` also inherit from their builtin namesakes.
- `APIError`, for an error response from snapd, with specific subclasses for the cases a charm might want to handle: `NotInstalledError`, `NotInStoreError`, `NeedsClassicError`, `ChannelNotAvailableError`, `RevisionNotAvailableError`, `AppNotFoundError`, `OptionNotFoundError`, and `ChangeError` (a change that failed after starting, such as an install hook erroring).

Each function documents the errors it can raise specifically. snapd's "not found" is always narrowed for you: `NotInstalledError` when the snap isn't on the system and `NotInStoreError` when the store has no such snap, so `refresh` and `hold` on an uninstalled snap raise `NotInstalledError` rather than an untyped error. The library probes snapd's state where needed to do this without producing chained "During handling of the above exception" tracebacks.

Where the CLI treats something as a non-error, so does the library: `install` of an already-installed snap, `refresh` with no update available, and `remove` of an uninstalled snap return a falsy value; `unhold` of an unheld or uninstalled snap, `unset` of a key that isn't set, `connect` of an already-connected pair, and a single-sided `disconnect` with nothing connected are silent no-ops.

snapd's raw error `kind` and `value` are not part of the public API: they're inconsistent across endpoints, and the typed error classes are the supported way to tell errors apart. The `message` property carries the error message; `str(error)` may append the offending value.

## Migrating from 1.x

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

## Other changes

- Timestamps from snapd (`InstalledInfo.hold`, `LogEntry.timestamp`) are timezone-aware, where they were previously assumed to be UTC.

# 1.0.1.post0 - 16 June 2026

Update project URLs.

# 1.0.1 - 4 November 2025

Update the type annotation of `log`'s `num_lines` parameter to indicate that `'all'` is accepted.

# 1.0.0.post0 - 14 October 2025

Update project URLs.

# 1.0.0 - 23 September 2025

Initial release of migrated `operator_libs_linux.v2.snap` library (patch version 14).
