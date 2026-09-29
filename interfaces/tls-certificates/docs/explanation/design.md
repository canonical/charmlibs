# Library design

The TLS Certificates interface allows charms to request TLS certificates without sharing their private key.

This library began life as a port of ``tls_certificates_interface.tls_certificates`` v4.22.

## What the library does for you

When a charm uses `TLSCertificatesRequiresV4`, the library:

- Generates an RSA-2048 private key by default on first use and stores it in a Juju secret owned by
  the requiring charm. Requirers can select RSA-3072, RSA-4096, ECDSA P-256, or ECDSA P-384 with
  the `key_algorithm` and `key_size` constructor arguments.
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

Private keys use RSA-2048 by default. A requirer can choose another algorithm with the
`KeyAlgorithm` enum:

| `key_algorithm` | Supported `key_size` | Default `key_size` |
|---|---|---|
| `KeyAlgorithm.RSA` (default) | 2048, 3072, 4096 | 2048 |
| `KeyAlgorithm.ECDSA` | 256 (P-256), 384 (P-384) | 256 |

```python
from charmlibs.interfaces.tls_certificates import KeyAlgorithm

self.certificates = TLSCertificatesRequiresV4(
    charm=self,
    relationship_name="certificates",
    certificate_requests=[CertificateRequestAttributes(common_name="example.com")],
    key_algorithm=KeyAlgorithm.ECDSA,
    key_size=384,  # optional; omit to use P-256
)
```

Plain strings (`"rsa"`, `"ecdsa"`) are also accepted. An unsupported algorithm or size raises
`TLSCertificatesError` when the object is created.

The selected algorithm and size apply when the library first generates a key, or when
`regenerate_private_key` is called. Existing persisted keys are kept, and normal certificate
renewal reuses the current key. This means changing the configuration of a deployed charm doesn't
rotate its key by itself. `PrivateKey` has read-only `algorithm` and `key_size` properties, so the
charm can detect a mismatch and rotate the key itself. The tutorial shows how.

### Signature hash

The library chooses the signature hash from the signing key: SHA-384 for ECDSA P-384 keys and
SHA-256 for all other keys. This applies to CSRs, issued certificates and self-signed CAs. For
issued certificates, the hash depends on the CA's key, not the subject's key.

### Key usage for ECDSA certificates

An EC key can't be used for RSA-style key encipherment. When the library issues a non-CA
certificate for an EC CSR that doesn't request a `KeyUsage` extension, it adds a critical
`KeyUsage(digital_signature=True)`. This applies to any EC CSR, including CSRs that weren't
created by this library. A `KeyUsage` extension requested in the CSR is kept as-is. CA
certificates always get `key_cert_sign` and `crl_sign`.

### Out of scope: Ed25519

Ed25519 isn't supported. It needs a different signing call (no separate hash) and PKCS#8 key
serialization, and support for it varies across certificate providers and TLS consumers. It can be
added later if a deployment needs it end to end.

### Key labelling and multiple integrations

When a requirer charm participates in more than one `tls-certificates` integration, the library stores one private key per relation. The Juju secret labels include both the unit number and the relation name, so each integration gets its own key and certificate without collisions.

### Manual key rotation

Charm authors can rotate the private key by calling the `regenerate_private_key` method, which generates a new private key, removes the old certificate requests, and sends new ones to the TLS provider.
