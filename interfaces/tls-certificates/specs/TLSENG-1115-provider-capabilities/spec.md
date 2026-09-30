**Input**: Extend the tls-certificates interface (v4) so providers can share their certificate server's capabilities in relation data, and requirers can read them. The library only provides awareness; how a requirer reacts is entirely up to the charm. To let a requirer adapt its requests to the shared capabilities, the library accepts `certificate_requests` (and `certificate_requests_by_mode`) as a callable that the library resolves, passing it the currently shared capabilities, when it builds requests. The change is additive only.

## User Scenarios & Testing _(mandatory)_

### User Story 1 - Provider shares capabilities (Priority: P1)

A provider charm describes what its backing certificate server can issue (for example, whether it supports IP SANs, wildcard DNS, or which domains it will issue for). The library publishes this description in the relation application data so related requirers can see it.

**Independent Test**: Initialize a provider with a capability set and confirm the leader writes it to the relation application data.

**Acceptance Scenarios**:

1. **Given** a provider configured with a capability set, **When** a relation hook runs on the leader, **Then** the capabilities appear in the relation application data.
2. **Given** a provider that shares nothing, **When** a relation hook runs, **Then** no capability data is written and related requirers see "unavailable".

### User Story 2 - Requirer reads capabilities (Priority: P1)

A requirer charm reads the provider's shared capabilities so it can decide for itself how to build its certificate requests. The library returns the parsed capabilities (or "unavailable") and takes no further action.

**Independent Test**: Relate a requirer to a capability-sharing provider and confirm the requirer reads back the same capability set the provider published.

**Acceptance Scenarios**:

1. **Given** a provider sharing capabilities, **When** the requirer reads them, **Then** it receives the same capability set the provider published.
2. **Given** no relation, no remote app, or invalid data, **When** the requirer reads capabilities, **Then** it receives "unavailable" rather than an error.

### User Story 3 - Requirer adapts requests via a callable (Priority: P2)

A requirer charm passes its certificate requests as a callable instead of a static list. The library invokes the callable with the currently shared capabilities each time it builds requests, so the charm can tailor its requests to what the provider advertises. The library only resolves the callable; the request content it returns is entirely the charm's decision.

**Independent Test**: Configure a requirer with a callable that varies its requests by capability; confirm the library invokes it with the current capabilities and sends exactly what it returns.

**Acceptance Scenarios**:

1. **Given** a requirer configured with a callable, **When** the library builds requests, **Then** it invokes the callable with the currently shared capabilities (or "unavailable" when none) and uses the returned requests verbatim.
2. **Given** a requirer configured with a static list, **When** the library builds requests, **Then** behavior is unchanged from before this feature.

## Requirements _(mandatory)_

### Functional Requirements

- **FR-001**: A provider MUST be able to share a set of capabilities, each field independently optional: `supports_ip_sans`, `supports_wildcard_dns`, `supports_subdomain`, `supports_ca_certificates`, `allowed_domains`, and a `provider_type` hint. An omitted field means "unspecified/unknown", never an assumed value.
- **FR-002**: Only the **leader** provider writes the capabilities to the relation application data, and writes MUST be no-op-if-unchanged to avoid relation churn.
- **FR-003**: A requirer MUST be able to read the shared capabilities via a getter. Reading MUST be best-effort: a missing relation, missing remote app, or data that fails validation MUST return "unavailable" rather than raising.
- **FR-004**: `certificate_requests` and `certificate_requests_by_mode` MUST accept a callable in addition to a static list/dict. When a callable is provided, the library MUST resolve it by invoking it with the currently shared capabilities (or "unavailable" when none) each time it builds requests, including on the renewal path, and use the returned requests verbatim.
- **FR-005**: The library MUST NOT inspect, mutate, or auto-adapt the requests it sends. The only adaptation surface is the charm-supplied callable (FR-004); the library never decides request content, sets status, or makes any reaction decision on the charm's behalf.
- **FR-006**: The library MUST treat shared capabilities as untrusted, best-effort remote-app input.
- **FR-007**: `allowed_domains` is an optional list of DNS domain names the provider shares it will issue for; the library transports it verbatim and defines no matching semantics. Omitted means unconstrained.
- **FR-008**: The change MUST be additive and fully backwards compatible: the callable form and capability field are optional, unknown databag fields are ignored, and omitted/default fields are not written, so capability-aware and legacy peers interoperate unchanged in both directions.
- **FR-009**: The capability field and the callable request forms MUST be optional, so adding them is a backwards-compatible (MINOR) change.

### Out of library scope (charm responsibility)

The library provides the mechanism (sharing capabilities, reading them, and resolving the callable), but not the policy. What the callable returns, whether to adapt requests, how to surface conflicts via status, and any `allowed_domains` matching semantics are the consuming charm's decisions and are documented separately in a charm how-to.

### Key Entities _(include if feature involves data)_

- **ProviderCapabilities** (relation data, snake_case): `supports_ip_sans`, `supports_wildcard_dns`, `supports_subdomain`, `supports_ca_certificates`, `allowed_domains`, `provider_type`. Every field optional; omission = unknown.
- **Provider application data**: existing issued certificates and request errors, plus the new optional `capabilities` element.

## Success Criteria _(mandatory)_

### Measurable Outcomes

- **SC-001**: A provider can share capabilities and a related requirer reads back the same set.
- **SC-002**: 100% of pre-feature requirer↔provider combinations keep working when only one side is upgraded (verified by a backwards-compatibility contract test).
- **SC-003**: Reading capabilities when none are shared, the relation is absent, or the data is invalid returns "unavailable" and never raises.
- **SC-004**: A requirer configured with a callable has it invoked with the current capabilities when requests are built, and the library sends exactly what the callable returns; a requirer configured with a static list behaves exactly as before this feature.
- **SC-005**: The library never decides request content or sets status on the charm's behalf; all request content originates from the charm's static list or its callable.

## Assumptions

- Targets the `tls-certificates` interface v4 and its provider/requirer library classes.
- The library provides the mechanism (share, read, and resolve the callable); all reaction policy lives in the consuming charm.
- The callable is resolved on every hook that builds requests (reconcile and renewal), since shared capabilities are not readable at construction time.
- Integration tests cover both upgrade paths (old requirer + new provider, new requirer + old provider).
