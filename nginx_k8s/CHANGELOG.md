# 1.0.1 - 22 June 2026

This change ensures that _tls_config checks the correct path for a CA cert. If the module checks the wrong path, it cannot correctly determine whether TLS is enabled or not.

# 1.0.0 - 22 June 2026

This change introduces necessary fixes to logic related to the Nginx Prometheus Exporter. As part of this fix, a breaking change is introduced, warranting a bump of the major version. The changes include:
- ensure that the NginxPrometheusExporter correctly configures based on the availability of TLS certificates

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
