# 1.3.0 - 2 June 2026

`PathProtocol.glob` and `LocalPath.glob` now accept a `str | os.PathLike[str]` pattern, matching `ContainerPath.glob` and `pathlib.Path.glob` on Python 3.13+.

# 1.2.1 - 6 February 2026

`PathProtocol` `iterdir` and `glob` now only promise to return an `Iterator` rather than a `Generator`.
This is technically a breaking change for users that expected to be able to use the `Generator` `send` method with these values.
However, this is being treated as a fix rather than a breaking change because:
1. Sending values to these generators was never meaningful -- the values were ignored, both by `LocalPath` and by `ContainerPath`.
2. `LocalPath` on Python 3.13+ already no longer returns a `Generator`, because `pathlib.Path` instead returns a `map` `Iterator`.
3. This is a type-annotation-only change, and only for `PathProtocol` -- `ContainerPath` still returns `Generator` objects and is typed as such, while `LocalPath` returns whatever `pathlib.Path` does.

# 1.2.0.post0 - 14 October 2025

Update project URLs.

# 1.2.0 - 8 September 2025

Drop Python 3.8 and 3.9 support.

# 1.1.1 - 3 Sep 2025

Add `missing_ok` argument to unlink method.

# 1.0.0.post0 - 8 Aug 2025

Small docstring update.

# 1.0.0 - 25 April 2025

Stable release.

# 0.0.0 - 24 April 2025

Beta release.
