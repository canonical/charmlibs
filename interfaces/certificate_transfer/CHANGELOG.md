# 1.1.1 - 24 November 2026

- Skip relations that Juju reports as not found when adding or removing certificates, instead of failing the hook. This can happen, for example, after a cross-model relation is torn down uncleanly. This requires ops 3.9 or later, which raises `RelationNotFoundError` in this case (see [canonical/operator#2748](https://github.com/canonical/operator/pull/2748)).

# 1.1.0 - 7 October 2026

- Make certificate reads repeatable and publish a v0 provider's certificate snapshot in the application databag.
- Sort certificates consistently and avoid emitting update events when the certificate set is unchanged.

# 1.0.0 - 6 February 2025

Migration of `certificate_transfer_interface.certificate_transfer` v1.15.
