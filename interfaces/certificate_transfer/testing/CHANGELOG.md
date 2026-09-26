# 1.1.0 - 22 September 2026

First release. Provides `RemoteProvider` and `RemoteRequirer`, which stand in for the application on the other end of a `certificate_transfer` relation and run the charm under test to build the state, and `mocked()`, which is required by every state-producing call although this library currently has nothing to mock.

This package is versioned in lockstep with `charmlibs-interfaces-certificate-transfer` and pins it exactly, because it reuses the library's private databag models. Install it as the library's `testing` extra rather than directly.
