# Unreleased

`ContainerPath` now matches `pathlib.Path` in more cases for paths where a parent exists but can't be traversed as a directory, because it's a non-directory (for example `/some/file.txt/child`) or a symlink to one:
- `exists`, `is_dir`, `is_file`, `is_fifo` and `is_socket` now return `False` instead of raising `NotADirectoryError`.
- `glob` now yields nothing instead of raising `NotADirectoryError`.
- `read_text` and `read_bytes` now raise `NotADirectoryError` instead of `ops.pebble.PathError`.
- For paths with a more distant non-directory parent (for example `/some/file.txt/child/child`), `is_symlink` now returns `False`, and `rmdir` and `unlink` now raise `NotADirectoryError`, instead of raising `ops.pebble.APIError`.
- For paths with the same name as their non-directory parent (for example `/some/file.txt/file.txt`), `is_symlink` now returns `False`, instead of describing the parent, and `rmdir` and `unlink` now raise `FileNotFoundError` like other children of a non-directory.

For paths under a symlink loop, `is_symlink` now returns `False`, and `read_text`, `read_bytes`, `rmdir`, `unlink` and `mkdir` now raise `OSError` (`errno.ELOOP`), instead of raising `ops.pebble.APIError` or `ops.pebble.PathError`, or `NotADirectoryError` for `mkdir(parents=True)`.

`ContainerPath.mkdir(parents=True)` now raises `FileExistsError` instead of `NotADirectoryError` when a parent is a broken symlink, matching `pathlib.Path`.

`ContainerPath.mkdir(exist_ok=True)` no longer calls `exists()` on the parent. Unit tests that patch `ContainerPath.exists` to fake a parent directory now need that directory to exist, for example in the `ops.testing` container filesystem.

`ContainerPath.rmdir` and `unlink` now raise `NotADirectoryError` instead of `FileNotFoundError` for paths whose parent is a non-directory or a symlink to one, matching `pathlib.Path`.

`ContainerPath.unlink(missing_ok=True)` now raises `NotADirectoryError` instead of succeeding silently for paths whose parent is a non-directory or a symlink to one, matching `pathlib.Path`.

# 1.4.1 - 10 November 2026

`ContainerPath.is_symlink`, `rmdir` and `unlink` now treat the path's name literally, rather than as a glob pattern. Previously, names containing `*`, `?`, `[` or `\` could match the wrong entry, or none, and a name matching several entries raised an `AssertionError`.

# 1.4.0 - 9 November 2026

`ContainerPath` now provides `is_relative_to` and `with_stem`, matching `pathlib.Path` on Python 3.9+.
`with_stem` is also part of `PathProtocol`; `is_relative_to` is not, because `pathlib`'s signature doesn't settle until Python 3.12.
`ContainerPath.match` now accepts a `str | os.PathLike[str]` pattern, matching `pathlib.Path.match` on Python 3.12+.
`ContainerPath.match` also explicitly rejects `ContainerPath` arguments with a `TypeError` (since `ContainerPath` is not `os.PathLike`), restoring the pre-3.14 behaviour: Python 3.14's `pathlib.PurePath.match` accepts any object that implements `with_segments`, which would otherwise silently let a `ContainerPath` through.

# 1.3.0.post0 - 16 June 2026

Update project URLs.

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
