## 0.0.1 - 22 April 2026

Initial release.

The initial `istio-request-auth` interface library provides the following features:

- Lets charms share their trusted JWT issuers and header-claim mappings as jwt_rules with the `istio-ingress-k8s` charms
- Lets charms specify multiple trusted issuers and their corresponding header-claim mappings as a list of jwt_rules
- Provides convienience data models for describing JWTRules
- Models the top level data bag as datamodel

