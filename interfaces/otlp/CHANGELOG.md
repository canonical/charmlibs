# Changelog

All notable changes to the charmlibs.interfaces.otlp library will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0]

### Added

- Initial release of charmlibs.interfaces.otlp
- `OtlpRequirer` for consuming OTLP endpoints from a provider relation
- `OtlpProvider` for publishing OTLP endpoints to requirer relations
- `OtlpEndpoint` pydantic model representing a single OTLP endpoint (protocol, URL, telemetries); used to communicate the required information for a server offering an OTLP API endpoint
- Support for filtering endpoints by protocol (`http`, `grpc`) and telemetry type (`logs`, `metrics`, `traces`)
- `gRPC` is favoured over `HTTP` when multiple endpoints are available
- Support for publishing LogQL and PromQL rules via `OtlpRequirer.publish()`
- LZMA+base64 compression of rules in the requirer databag to avoid Juju databag size limits
- `OtlpProvider.rules()` for fetching rules from all requirer relations with injected Juju topology and validation
- Generic aggregator rules automatically included in every requirer's published rule set
- Python 3.10+ compatibility

## [0.2.0]

### Updated

- Replace the requirer's rule path interface with an interface accepting an object containing rules
- Generic PromQL alert rules for requirer charms that are of the aggregator or application type
