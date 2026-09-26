# 1.11.0 - 21 September 2026

First release. Provides `RemoteProvider` and `RemoteRequirer`, which stand in for the application on the other end of a `tls-certificates` relation and run the charm under test to build the state, and `mocked()`, which replaces the library's private key generation with a pre-generated key for the duration of a test.

This package is versioned in lockstep with `charmlibs-interfaces-tls-certificates` and pins it exactly, because it reuses the library's private wire format. Install it as the library's `testing` extra rather than directly.
