# 1.1.1 - 30 November 2026

- Require `ops>=2.23.0,<4` and `pydantic>=1.10.0`. Previously neither dependency had a lower bound. 2.23 is the oldest ops 2 series that's still maintained.
- Don't write a `model_config` key to the relation databag when using pydantic v1.

# 1.1.0 - 7 October 2026

- Make certificate reads repeatable and publish a v0 provider's certificate snapshot in the application databag.
- Sort certificates consistently and avoid emitting update events when the certificate set is unchanged.

# 1.0.0 - 6 February 2025

Migration of `certificate_transfer_interface.certificate_transfer` v1.15.
