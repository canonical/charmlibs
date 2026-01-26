# Changelog

All notable changes to the charmlibs.interfaces.slo library will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial release of charmlibs.interfaces.slo (migrated from charmlibs.slo)
- SLOProvider class for providing SLO specifications
- SLORequirer class for consuming SLO specifications
- Automatic Juju topology label injection into Prometheus queries
- Support for multi-document YAML specifications
- Pydantic-based validation of SLO specifications
- Python 3.8+ compatibility

### Changed
- Package name changed from `charmlibs-slo` to `charmlibs-interfaces-slo`
- Import path changed from `charmlibs.slo` to `charmlibs.interfaces.slo`
- Updated type hints to use `typing.Dict`, `typing.List` for Python 3.8 compatibility
- Requires Python >= 3.8 (previously >= 3.10)
