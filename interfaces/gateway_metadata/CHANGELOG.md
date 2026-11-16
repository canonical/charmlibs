# Changelog

## 1.0.2 - 16 November 2026

- Require `ops>=2.17.0`. Without a lower bound, a charm could resolve an ops release too old to provide the APIs this library uses. 2.17.0 is the oldest release the unit tests can run against, since it's the first with the `testing` extra.

## 1.0.1 - 16 June 2026

- Minor docstring and README updates.

## 1.0.0.post0 - 16 April 2026

Correct package metadata URLs.

## 1.0.0 - 16 April 2026

Initial release. Migrated from `charmed-service-mesh-helpers` (v0.6.0) `interfaces.gateway_metadata` module.
