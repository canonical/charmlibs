# Library design

The TLS Certificates interface allows charms to request TLS certificates without sharing their private key.

This library began life as a port of ``tls_certificates_interface.tls_certificates`` v4.22.

## What the library does for you

When a charm uses `TLSCertificatesRequiresV4`, the library:

- Generates an RSA private key on first use and stores it in a Juju secret owned by the requiring charm.
- Builds a CSR from the `CertificateRequestAttributes` you supply and writes it to relation data.
- Receives the signed certificate from the provider and emits a `certificate_available` event.
- Tracks certificate expiry and triggers renewal automatically (see below).

Because the library generates the private key, upgrading a charm that previously managed its own key will cause one certificate rotation: the library generates a new key, the previous CSR no longer matches, and a new certificate is issued. If you need to retain a specific key — for example, to avoid that rotation — you can pass it to `TLSCertificatesRequiresV4` at instantiation time.

## How automatic renewals work

The library renews certificates without any code in the requirer charm:

1. When the requirer receives a certificate from the provider, it stores the certificate in a Juju secret with an expiry set ahead of the certificate's own expiry.
2. A `certificate_available` event is emitted, prompting the requiring charm to write the certificate where its workload expects it.
3. When the Juju secret expires, the library removes the old CSR from the relation data, deletes the secret, generates a new CSR, and writes the new CSR to the relation data.
4. The provider reads the new CSR, issues a new certificate, and writes it to relation data.
5. The requirer reads the new certificate, stores it in a fresh Juju secret, and re-emits `certificate_available`.

The requiring charm only ever has to handle `certificate_available`; the rest is managed by the library.

## Private key handling

The library never transmits the requirer's private key over the relation. Only CSRs and the resulting certificates cross the relation; the private key stays inside the requiring charm's data.

### Storage at rest

The library stores the private key in a Juju secret owned by the requiring charm. Only the charm itself and a Juju administrator can read the secret. For details of the secret backend Juju uses, see the [Juju documentation on secret backends](https://documentation.ubuntu.com/juju/3.6/howto/manage-secret-backends/#manage-secret-backends).

### Key generation

Private keys are generated using the [RSA algorithm](https://en.wikipedia.org/wiki/RSA_(cryptosystem)).

### Key labelling and multiple integrations

When a requirer charm participates in more than one `tls-certificates` integration, the library stores one private key per relation. The Juju secret labels include both the unit number and the relation name, so each integration gets its own key and certificate without collisions.

### Manual key rotation

Charm authors can rotate the private key by calling the `regenerate_private_key` method, which generates a new private key, removes the old certificate requests, and sends new ones to the TLS provider.
