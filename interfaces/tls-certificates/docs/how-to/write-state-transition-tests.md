---
myst:
  html_meta:
    description: Write state-transition tests for a charm that uses charmlibs.interfaces.tls_certificates, using the library's testing package.
---

# Write state-transition tests for your charm

The `tls-certificates` testing package stands in for the application on the other end of the relation while you test your charm, so that your tests never need to know the relation's wire format.

Add `charmlibs-interfaces-tls-certificates[testing]` to your test dependencies — not `charmlibs-interfaces-tls-certificates-testing` directly, so that the testing package version always matches the library itself. Then import it alongside the library:

```py
from charmlibs.interfaces import tls_certificates, tls_certificates_testing
```

This page covers what is specific to `tls-certificates`. For the shape shared by every `charmlibs.interfaces` testing package — the four methods on a simulated remote, what `end` means, when to open the `mocked()` scope, and the limitations they all share — read [how to use a testing package in state-transition tests](../../../../.docs/how-to/use-a-testing-package.md) first.

## Test a requirer charm

A requirer charm — one that asks for certificates — is tested with a `RemoteProvider`:

```py
import pytest
from ops import testing

from charmlibs.interfaces import tls_certificates_testing

import my_charm

CERTS = tls_certificates_testing.RemoteProvider("certificates")


@pytest.fixture()
def ctx():
    return testing.Context(my_charm.MyCharm)


@pytest.fixture()
def mocked():
    with tls_certificates_testing.mocked():
        yield


def test_requirer_receives_certificates(ctx: testing.Context, mocked: None):
    state_out = CERTS.integrate(ctx, testing.State.from_context(ctx))
    assert isinstance(state_out.unit_status, testing.ActiveStatus)
```

That single `integrate` call runs the whole conversation: it adds the relation, runs the charm for `relation-created`, `relation-joined` and `relation-changed` — during which the charm generates its key and publishes its certificate signing requests — then writes the provider's certificates, then runs the charm again so it picks them up.

**Nothing has to agree between the fixture and your charm.** The provider signs whatever your charm actually asked for, so there is no request list to keep in step and no private key to seed. This holds whether your charm lets the library manage its key (the recommended configuration) or passes `private_key=` itself.

The interface name, for the relations you build by hand rather than through `integrate`, is `tls-certificates`:

```py
relation = testing.Relation(
    CERTS.endpoint, interface="tls-certificates", remote_app_name=CERTS.remote_app_name
)
```

A requirer charm in `Mode.APP` or `Mode.APP_AND_UNIT` writes its requests to the application databag, which a non-leader unit cannot do — so such a charm publishes nothing at all unless the state is the leader. `publish` logs a warning when it finds nothing to answer in a non-leader state, because that is the likeliest explanation; pass `leader=True` to `ops.testing.State` to rule it out.

## What the provider does with each request

`outcome` takes an `Outcome`, or a callable choosing one per request. `Outcome` is a class with five classmethod constructors, not an enumeration, so each is called:

- `Outcome.issued()` (the default) — a certificate, valid from now.
- `Outcome.denied()` — an error instead. Reaches your charm through `get_request_errors()`, `get_request_error()`, and the `certificate_denied` event. Customise it with `code`, `message` and `reason`.
- `Outcome.renewing()` — a certificate far enough through its validity period that the library's renewal safety net re-requests it on your charm's next reconcile.
- `Outcome.expired()` — a certificate whose validity period is entirely in the past, for testing what your charm does when renewal has *failed*. The library won't rescue it: the safety net stops at expiry.
- `Outcome.revoked()` — a certificate flagged revoked, which makes the library remove its Juju secret.

The callable receives the `CertificateRequestAttributes` your charm asked for, so it can select on whatever distinguishes your requests:

```py
STRICT = tls_certificates_testing.RemoteProvider(
    "certificates",
    outcome=lambda request: (
        tls_certificates_testing.Outcome.denied(
            code=tls_certificates.CertificateRequestErrorCode.WILDCARD_NOT_ALLOWED
        )
        if request.common_name.startswith("*")
        else tls_certificates_testing.Outcome.issued()
    ),
)
```

A request with `is_ca=True` is answered with a CA certificate, and every issued certificate is published with its real chain, leaf to root, signed by a genuine testing CA — so a charm that verifies chains properly is satisfied.

## Advertised capabilities

`capabilities` is what the provider has advertised about its certificate server. Leave it out and the provider hasn't advertised at all, which `get_provider_capabilities()` reports as `None` ("not known yet") — and which the capability-aware callable form of the library's `certificate_requests` is resolved against. Pass a `ProviderCapabilities`, even an empty one, to model a provider that has advertised:

```py
WILDCARDS = tls_certificates_testing.RemoteProvider(
    "certificates",
    capabilities=tls_certificates.ProviderCapabilities(supports_wildcard_dns=True),
)
```

Each field carries its own three-way meaning: `True` is supported, `False` is advertised-as-unsupported, and `None` is left unspecified.

## When one `integrate` isn't enough

For almost every requirer charm, `integrate`'s default `end="received"` leaves the relation genuinely settled: an extra `publish` and `run_changed` changes nothing. That holds for the happy path and for each of `Outcome.denied()`, `Outcome.expired()` and `Outcome.revoked()`, and it holds for a provider charm tested with a `RemoteRequirer`.

There is one shape where it does not, and it's the one the general guide warns about: a charm whose requests *depend on what it received*. Two cases arise with this library.

**A capability-aware `certificate_requests` callable that returns different requests for different capabilities.** During `integrate` the charm first publishes with capabilities still unknown, because the provider hasn't advertised yet. The provider then advertises and answers; the charm's next run resolves the callable against the capabilities it can now see, withdraws its original request and publishes a different one — which nothing has answered. After `integrate` alone, such a charm holds **no certificates at all**. One more round settles it:

```py
def test_wildcard_request(ctx: testing.Context, mocked: None):
    state = WILDCARDS.integrate(ctx, testing.State.from_context(ctx))
    state = WILDCARDS.publish(state)            # answer the capability-aware request
    state_out = WILDCARDS.run_changed(ctx, state)
    assert isinstance(state_out.unit_status, testing.ActiveStatus)
```

A callable that returns the same requests whichever capabilities it is given needs no extra round, and neither does a static `certificate_requests` list.

**`Outcome.renewing()`**, where the charm's reconcile deliberately withdraws the request and asks again. That is not a surprise but the point of the outcome, and the pattern below is how it's completed.

If you're unsure which case your charm is in, look rather than guess — run the extra round and compare, as the general guide shows.

## Renewal

Because a remote is immutable and depends only on its arguments and the state, two remotes for the same application are just two ways of answering. Use a stale one to make the charm re-request, and a fresh one to answer properly:

```py
STALE = tls_certificates_testing.RemoteProvider(
    "certificates", outcome=tls_certificates_testing.Outcome.renewing()
)
FRESH = tls_certificates_testing.RemoteProvider("certificates")


def test_renewal(ctx: testing.Context, mocked: None):
    st = STALE.integrate(ctx, testing.State.from_context(ctx))  # reconcile re-requests
    st = FRESH.publish(st)                                      # answered properly
    state_out = FRESH.run_changed(ctx, st)
```

Every later turn of the conversation has this shape — after a config change, a key rotation, or anything else that makes your charm publish again:

```py
def test_key_rotation(ctx: testing.Context, mocked: None):
    st = CERTS.integrate(ctx, testing.State.from_context(ctx))
    with ctx(ctx.on.update_status(), st) as manager:
        manager.charm.certificates.regenerate_private_key()  # withdraws the old requests
        st = manager.run()
    st = CERTS.publish(st)               # the provider answers the new requests
    state_out = CERTS.run_changed(ctx, st)  # your charm picks the new certificates up
    assert isinstance(state_out.unit_status, testing.ActiveStatus)
```

`publish` answers what your charm now asks for, keeps what it has already answered, and drops answers to requests your charm has withdrawn — which is what the real provider's library does.

## Test a provider charm

A provider charm is tested with a `RemoteRequirer`. Here the remote writes first, so there's nothing to derive from your charm and the requests are ordinary fixture configuration:

```py
WORKLOAD = tls_certificates_testing.RemoteRequirer(
    "certificates",
    certificate_requests=[
        tls_certificates.CertificateRequestAttributes(common_name="workload.example.com")
    ],
)


def test_provider_issues_certificates(ctx: testing.Context, mocked: None):
    st = testing.State.from_context(ctx, leader=True)
    state_out = WORKLOAD.integrate(ctx, st)
    assert isinstance(state_out.unit_status, testing.ActiveStatus)
```

Note `leader=True`. `TLSCertificatesProvidesV4` writes to the application databag, so a non-leader provider charm answers nothing — which is invisible in the resulting state and easily mistaken for a bug in your charm.

`mode` mirrors the `mode` a real requirer would pass to `TLSCertificatesRequiresV4`: `Mode.UNIT` (the default) puts the requests in the remote unit's databag, `Mode.APP` in the remote application's, and `Mode.APP_AND_UNIT` splits them per `certificate_requests_by_mode`. `private_key` is the key the simulated requirer signs with; a provider charm never sees it, so it's rarely worth setting.

A provider charm may serve several requirer applications on one endpoint, so construct one remote per application:

```py
WORKERS = [
    tls_certificates_testing.RemoteRequirer("certificates", remote_app_name=f"worker{n}")
    for n in range(3)
]


@pytest.fixture()
def clustered(ctx: testing.Context, mocked: None):
    st = testing.State.from_context(ctx, leader=True)
    for worker in WORKERS:
        st = worker.integrate(ctx, st)
    return st
```

A *requirer* charm can have only one provider per endpoint: the library reads its relation with `Model.get_relation`, which raises when an endpoint carries more than one, so a second `RemoteProvider` on the same endpoint raises `ValueError` rather than building a state the charm can't survive. Several endpoints, one remote each, is fine.

`publish` recomputes the requirer's requests from `certificate_requests`, adding what isn't there and removing what this remote no longer asks for, so a test can change what the requirer wants and watch the charm reconcile. The certificates your charm has issued are left alone.

## What `mocked()` does for this library

It replaces the library's private key generation with a pre-generated RSA key. Generating a 2048-bit key takes a noticeable fraction of a second, and a charm that lets the library manage its key generates one on its first reconcile and again on every rotation, so a suite of a few hundred state-transition tests would otherwise spend most of its time on key generation.

It also replaces two values the library would otherwise draw at random — a new certificate's serial number, and the identifier that distinguishes one certificate request from another — with counters that restart for each scope. Both are *sequences*, never constants, and the distinction matters: the library tells requests apart by that identifier, so a constant would make a re-request identical to the request it replaces, and a renewal would look like a request that had already been answered.

**Certificates are still not reproducible between separately-arranged states.** Their validity dates come from the clock, which the library reads directly, and mocking that would mean mocking something outside the library — which would change the behaviour of charm code that never touches it. So two runs of the same arrangement agree only if they land in the same second. Assert on what the library reports rather than on certificate bytes, and use `publish`'s idempotence, not byte equality, to check that a certificate was not reissued.

Nothing outside the library is patched, so a charm that generates its own keys — through `cryptography` or anything else — is unaffected. The key is a real RSA key, so everything that depends on having one keeps working: signing, `matches_private_key`, chain verification. The only observable difference is that a charm which lets the library manage its key gets the same key in every test.

Key *rotation* still produces a distinct key: the mock returns a fresh key for each call after the first, so a test asserting that `regenerate_private_key()` changed the key still tests something.

## Limitation: the secret-expiry renewal route

`Outcome.renewing()` reaches the library's renewal safety net, not its `secret-expired` path. The certificate's secret is created by the library as the charm runs, so a state built before the charm has run holds none and there is nothing to fire `ctx.on.secret_expired` at. Both routes withdraw the request and re-request, so the charm ends up in the same place; to exercise the secret-expiry route specifically, run the charm until it holds certificates and fire the event at the secret it created.

Read more:
- [Testing package reference](https://canonical.com/juju/docs/charmlibs/reference/testing/charmlibs-interfaces-tls-certificates-testing/)
- [Library reference](https://canonical.com/juju/docs/charmlibs/reference/charmlibs/interfaces/tls-certificates/)
