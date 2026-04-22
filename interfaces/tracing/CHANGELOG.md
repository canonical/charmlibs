# Changelog

All notable changes to the charmlibs.interfaces.tracing library will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-04-XX

The `tracing` library migrated from the `tempo-operators` repository here:
- Feature parity with `tempo_coordinator_k8s/v0/tracing.py`
- That's `LIBID = "d2f02b1f8d1244b5989fd55bc3a28943"; LIBAPI = 0; LIBPATCH = 11`
- Python3.10 or later is now required by the library
- Thus, Ubuntu base 22.04 or later now required by charms that use this library
- Pydantic2 is now required by the library
