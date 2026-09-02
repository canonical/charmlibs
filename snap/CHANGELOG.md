# 2.0.0 - 31 August 2026

A ground-up rewrite of `charmlibs.snap`. The 1.x library was a straight migration of `operator_libs_linux.v2.snap`; 2.0 is a new, deliberately smaller API. It talks to snapd exclusively over the REST API (it no longer shells out to the `snap` CLI), has no caching layer, and has no runtime dependencies (the `opentelemetry-api` dependency and its tracing are gone). Function names, argument semantics, and error behaviour follow the `snap` CLI, so what you know from the command line carries over.

Every operation is a module-level function that takes the snap's name -- there are no `Snap` objects and no `SnapCache`. Every error the library raises is a subclass of `Error`, with typed subclasses for the cases a charm might want to handle. See the [reference documentation](https://canonical.com/juju/docs/charmlibs/reference/charmlibs/snap) for the full API, and [how to migrate from 1.x to 2.0](https://canonical.com/juju/docs/charmlibs/how-to/charmlibs/snap/migrate-from-1x) for a walkthrough of the changes and a table mapping each 1.x name to its replacement.

If you can't migrate yet, pin `charmlibs-snap<2`. The 1.x series remains the drop-in replacement for `operator_libs_linux.v2.snap`.

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
