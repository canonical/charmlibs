# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-01-20

### Added
- Initial migration of SLO library from sloth-k8s-operator to charmlibs monorepo
- `SLOProvider` class for charms to provide SLO specifications as raw YAML strings
- `SLORequirer` class for Sloth charm to collect and validate SLO specifications
- Automatic Juju topology label injection into Prometheus queries
- Pydantic-based SLO specification validation (on requirer side)
- Support for single and multiple SLO specifications via YAML document separators
- `inject_topology_labels` utility function for manual topology injection

### Changed
- Provider now accepts raw YAML strings instead of dictionaries
- Validation moved from provider to requirer side
- Removed event handling (SLOsChangedEvent, SLOProviderEvents, SLORequirerEvents)
- Removed `provide_slo()` method - only `provide_slos()` remains
- Early exit if no relations present (before validation)
