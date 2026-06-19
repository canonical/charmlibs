# 0.1.1 - 19 June 2026

This includes a small bugfix only.
- Server locations are now sorted, to prevent noisy config diffs which in turn would trigger spurious workload restarts.

# 0.1.0 - 24 October 2025

This includes a few features that were introduced in the parent library while this one was being reviewed, approved and merged.
- extra directive support for locations
- headers and rewrite rule support for locations
- tracing configuration for nginx

Additionally, we renamed 'groups' to more proper nginx terminology: 'address_lookup_key'.

# 0.0.1 - 9 October 2025

Initial library release.
