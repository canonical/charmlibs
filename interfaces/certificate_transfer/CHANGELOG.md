# Unreleased

Write the provided certificates in sorted order, so that the databag doesn't change (and trigger a `relation-changed` event on the requirer) when the set of certificates hasn't.

Make certificate reads repeatable, and have v0 providers also publish the certificates in the app databag (#697).

# 1.0.0 - 6 February 2025

Migration of `certificate_transfer_interface.certificate_transfer` v1.15.
