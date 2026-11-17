---
myst:
  html_meta:
    description: Migrate charm code from charmlibs.snap 1.x or operator_libs_linux.v2.snap to charmlibs.snap 2.0.
---

# Migrate to 2.0

`charmlibs.snap` 2.0 is a ground-up rewrite. The 1.x library was a straight migration of `operator_libs_linux.v2.snap`; 2.0 is a new, deliberately smaller API. It talks to snapd exclusively over the REST API (it no longer shells out to the `snap` CLI), has no caching layer, and has no runtime dependencies. Function names, argument semantics, and error behaviour follow the `snap` CLI, so what you know from the command line carries over.

The 1.x series was a drop-in replacement for `operator_libs_linux.v2.snap`, so the same table applies if you're migrating directly from the Charmhub-hosted library. If you can't migrate yet, pin `charmlibs-snap<2`.

One notable gap in the initial 2.0 release is support for installing local snaps. We hope to provide this functionality soon, with the addition of support for `snap ack` to allow charms to smoothly refresh between local and store revisions of their snap.

## The new API

Every operation is a module-level function that takes the snap's name. There are no `Snap` objects and no `SnapCache`. Every name-like argument is validated before a request is made, and an empty or blank name raises `ValueError` rather than reaching snapd.

{py:func}`snap.ensure_installed` is the one-call replacement for `ensure`/`add`: it installs the snap if absent, refreshes it if it's on the wrong channel or revision, and otherwise refreshes it only when `update` is true and no revision was requested. {py:func}`snap.install`, {py:func}`snap.refresh`, and `ensure_installed` all return a truthy value if something changed and a falsy value otherwise (not guaranteed to be a `bool`). These operations wait for the snapd change to complete, with no overall deadline, like the CLI. A change that finishes in the `Wait` state (for example, one that needs a reboot) is treated as success and logged as a warning.

Use {py:func}`snap.hold` to prevent snap auto-refreshes. Use {py:func}`snap.list_one` to query (list) information about an installed snap -- for example, {py:class}`snap.InstalledInfo` (e.g. `InstalledInfo.hold`) reports when a hold ends. Use {py:func}`snap.get` to check an installed snap's config -- this always returns JSON-typed snap config values (the 1.x `typed=` flag is gone), and always returns a dict keyed by what you asked for; {py:func}`snap.get_one` returns a single value directly.

The previous library versions automatically appended some logs when errors were raised. This version provides an explicit {py:func}`snap.logs` function, which returns structured {py:class}`snap.LogEntry` objects (`timestamp`, `message`, `sid`, `pid`) in chronological order. You can fetch and log these on errors, or rely on the hopefully improved error taxonomy below.

## Errors

Every error the library raises is a subclass of {py:class}`snap.Error`; invalid arguments raise ordinary Python exceptions such as `ValueError`. There are two families:

- Transport errors, for when snapd couldn't be reached or understood: {py:class}`snap.ConnectionError` (snapd is down; read-only requests are briefly retried, requests that change state are not), {py:class}`snap.TimeoutError` (snapd didn't answer within the 120s the CLI also allows), and {py:class}`snap.BadResponseError` (snapd sent something the library can't read; report this to the developers if you see it in the wild). `ConnectionError` and `TimeoutError` also inherit from their builtin namesakes to facilitate generic networking retry logic.
- {py:class}`snap.APIError`, for an error response from snapd, with specific subclasses for the cases a charm might want to handle: {py:class}`snap.NotInstalledError`, {py:class}`snap.NotInStoreError`, {py:class}`snap.NeedsClassicError`, and so on. Each function documents which errors it can raise.

Where the CLI treats something as a non-error, so does the library: `install` of an already-installed snap, `refresh` with no update available, and `remove` of an uninstalled snap return a falsy value; `unhold` of an unheld or uninstalled snap, `unset` of a key that isn't set, `connect` of an already-connected pair, and a single-sided `disconnect` with nothing connected are silent no-ops.

See the [reference documentation](https://canonical.com/juju/docs/charmlibs/reference/charmlibs/snap) for the full error hierarchy and the errors each function raises.

## Map from 1.x to 2.0

| 1.x | 2.0 |
| --- | --- |
| `SnapCache()[name]`, `Snap(name)` | Pass `name` to the functions below |
| `add(name, ...)`, `ensure(name, ...)`, `Snap.ensure(state, ...)` | {py:func}`snap.ensure_installed` (`name`, `channel`, `revision=...`, `classic=...`), or `install`/`refresh` directly |
| `remove(names)` | {py:func}`snap.remove` (`name`, `purge=...`), one snap at a time |
| `Snap.present`, `.latest`, `.state`, `.revision`, `.channel`, `.confinement`, `.version`, `.held` | {py:func}`snap.list_one` returning {py:class}`snap.InstalledInfo` (`name`, `classic`, `tracking`, `revision`, `version`, `hold`); raises {py:class}`snap.NotInstalledError` if absent |
| `Snap.hold(duration)`, `Snap.unhold()` | {py:func}`snap.hold` (`name`, `duration`), {py:func}`snap.unhold` (`name`) |
| `hold_refresh(days, forever)` (system-wide) | {py:func}`snap.set` (`'system'`, `{'refresh.hold': ...}`) |
| `Snap.start(services, enable)`, `.stop(services, disable)`, `.restart(services)` | {py:func}`snap.start`, {py:func}`snap.stop`, {py:func}`snap.restart` |
| `Snap.restart(reload=True)` | No replacement |
| `Snap.get(key, typed=...)` | {py:func}`snap.get` returns `{key: value}`; {py:func}`snap.get_one` returns `value`; always typed |
| `Snap.set(config, typed=...)`, `Snap.unset(key)` | {py:func}`snap.set` (`name`, `config`), {py:func}`snap.unset` (`name`, `keys`) |
| `Snap.connect(plug, service, slot)` | {py:func}`snap.connect` plus new {py:func}`snap.disconnect` |
| `Snap.alias(application, alias)` | {py:func}`snap.alias` (`name`, `app`, `alias`); new {py:func}`snap.unalias` |
| `Snap.logs(services, num_lines)` returning `str` | {py:func}`snap.logs` returning `list[LogEntry]`; filtering by service is not supported |
| `Snap.apps`, `Snap.services`, `SnapClient.get_installed_snaps`, `SnapClient.get_installed_snap_apps` | No replacement; query individual snaps with `list_one` |
| `SnapClient.snapd_installed` | Catch {py:class}`snap.SocketNotFoundError` |
| `install_local(filename, ...)` | No replacement yet |
| `SnapError`, `SnapAPIError`, `SnapNotFoundError` | The {py:class}`snap.Error` hierarchy above; `SnapNotFoundError` becomes `NotInstalledError` or `NotInStoreError` |
| `SnapState`, `SnapService`, `SnapServiceDict`, `MetaCache`, `JSONAble`, `JSONType`, `ansi_filter` | Removed |
