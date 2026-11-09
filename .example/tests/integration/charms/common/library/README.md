# Placeholder README for the library under test

This directory is a local copy of the library under test. Test charms depend on it by creating a symlink to it and pointing their `tool.uv.sources` there.

We need this local copy rather than just symlinking to the parent library directory because `cp --recursive --dereference` (run on the test charm to prepare it for packing) forbids cyclic links.

- `pyproject.toml` and `src/` are symlinks to the real library at the package root so the charm always builds against the current source.
- `README.md` is this placeholder. A readme is required because the library declares `readme = "README.md"`, and hatchling fails the build if that file is missing.
