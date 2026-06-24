**Input**: Extend the tls-certificates interface (v4) so providers can advertise their certificate server's capabilities, and requirers can **react** to them while preserving operator control.

## Current State (baseline)

The library already provides the mechanism; this feature is about the **reaction policy** built on top of it. Already implemented:

- `ProviderCapabilities` model and an optional `capabilities` field in the provider's application databag (`extra="ignore"`; default/`None` values omitted on the wire).
- `get_provider_capabilities()` getter on the requirer.
- `CertificateDenied` events.
- `certificate_requests` accepting a **callable** (resolved per hook), in addition to a static list.

The remaining work (the delta): charm-side **reaction** policy, status handling, the security/logging behavior, and contract/integration tests + docs.

## Reaction model (key concept)

The library only **exposes** capabilities (getter), denial events, and the callable `certificate_requests` hook. It does **not** prescribe or perform adaptation — all policy lives in the consuming charm. A "reaction" is a charm decision and MAY be:

- **(a)** adapt the certificate request (only for default-valued attributes),
- **(b)** set a unit/app status (e.g. `Blocked`) to surface incompatibility, or
- **(c)** do nothing.

## User Scenarios & Testing _(mandatory)_

### User Story 1 - Capability exchange (Priority: P1)

A leader provider publishes a best-effort, structured description of what its backing server can issue. A requirer reads it via `get_provider_capabilities()` and reacts per its own policy, with no operator configuration required in the common case.

**Independent Test**: Initialize a provider with a known capability set; confirm the leader writes it to the app databag. Relate a default-configured requirer; confirm it reads the same set and produces a compatible request.

**Acceptance Scenarios**:

1. **Given** a provider initialized with a capability set, **When** a hook runs on the leader, **Then** the capabilities appear in the relation application data, and a re-run with unchanged config writes nothing new.
2. **Given** a provider that advertises nothing (or invalid data), **When** the requirer builds requests, **Then** `get_provider_capabilities()` returns "unavailable" and the requirer falls back to its configured behavior.

---

### User Story 2 - Reacting to a denial (Priority: P2)

When a request cannot be fulfilled, the requirer receives a `CertificateDenied` event, re-resolves its `certificate_requests` callable against the now-known capabilities, and either resubmits a compatible request or surfaces the conflict via status.

**Independent Test**: Submit a request incompatible with the provider; confirm a denial is surfaced, and that after re-resolution the requirer either obtains a compatible certificate or enters `Blocked` (depending on whether the conflicting attribute was operator-set).

**Acceptance Scenarios**:

1. **Given** a denial on a **default**-valued attribute, **When** the callable re-resolves, **Then** a compatible request is submitted and a certificate is issued.
2. **Given** a denial caused by an **operator-set** attribute that conflicts with capabilities, **When** the callable re-resolves, **Then** the request is left intact and the charm sets `Blocked` rather than silently dropping the operator's value.

## Requirements _(mandatory)_

### Functional Requirements

- **FR-001**: The `capabilities` set MUST support, as independently optional fields: `supports_ip_sans`, `supports_wildcard_dns`, `supports_subdomain`, `supports_ca_certificates`, `allowed_domains` (see FR-010), and a `provider_type` hint. An omitted field means "unspecified/unknown" — never an assumed value; the requirer falls back to its configured behavior for that field.
- **FR-002**: Only the **leader** provider writes the app databag, and writes MUST be no-op-if-unchanged to avoid `relation-changed` churn on requirers.
- **FR-003**: Capability awareness MUST be best-effort on both sides. Absent relation/remote-app, or data that fails validation, MUST yield an "unavailable" result (logged at WARNING) rather than raising; the requirer then falls back to its configuration.
- **FR-004**: Explicit operator configuration MUST never be silently overridden. Only **default-valued** request attributes are eligible for capability-driven adaptation. An operator-set value that conflicts with capabilities MUST be preserved and surfaced via status (e.g. `Blocked`).
- **FR-005**: Any capability-driven **removal** of a requested attribute (e.g. dropping an IP SAN) MUST be logged at WARNING and surfaced in status, because capability data is untrusted remote-app input and could weaken the resulting certificate.
- **FR-006**: Re-resolution MUST be triggered only on deliberate events (a denial or an explicit sync), not on every attribute/relation change.
- **FR-007**: No new certificate request is issued when a currently-held certificate still satisfies the requirer's resolved request (direction-agnostic; no assumption that capabilities only tighten).
- **FR-008**: The change MUST be additive and fully backwards compatible: unknown databag fields are ignored (`extra="ignore"`) and default/`None` fields omitted, so capability-aware and legacy peers interoperate unchanged in both directions. This MUST be pinned by a contract test.
- **FR-009**: This is a **PATCH**-level, additive change; the `capabilities` field stays optional permanently.
- **FR-010**: `allowed_domains` is an optional list of DNS domain names the provider will issue for. Match semantics this iteration are the **simplest**: **exact** — a requested DNS name (CN or DNS SAN) is covered only if it appears verbatim in the list; no wildcard or suffix matching is implied. An omitted/`None` `allowed_domains` means unconstrained. A requested name not covered is an incompatibility the requirer reacts to under the same rules as any other capability (FR-004/FR-005).

### Scope

- **Deferred**: richer `allowed_domains` matching (suffix/wildcard semantics) is out of scope; only exact membership is defined this iteration.

### Key Entities _(include if feature involves data)_

- **ProviderCapabilities** (wire form, snake_case): `supports_ip_sans`, `supports_wildcard_dns`, `supports_subdomain`, `supports_ca_certificates`, `allowed_domains`, `provider_type`. Every field optional; omission = unknown.
- **Provider application data**: existing issued certificates and request errors, plus the optional `capabilities` element.
- **Certificate request attributes**: what the requirer asks for; default-valued attributes are eligible for adaptation, operator-set ones are not.

## Success Criteria _(mandatory)_

### Measurable Outcomes

- **SC-001**: A default-configured requirer related to a capability-advertising provider obtains a usable certificate with zero provider-specific operator configuration in the common cases.
- **SC-002**: 100% of pre-feature requirer↔provider combinations keep working when only one side is upgraded (verified by the FR-008 contract test).
- **SC-003**: A conflict on an operator-set attribute yields a visible `Blocked` status and zero silent attribute removal; any capability-driven removal is logged at WARNING.
- **SC-004**: A held certificate that still satisfies the resolved request triggers zero new requests when capabilities later change in either direction.

## Assumptions

- Targets the `tls-certificates` interface v4 and its provider/requirer library classes.
- Reaction policy lives in the consuming charm; the library only exposes the getter, denial events, and the callable hook. Churn avoidance (keeping the request stable while a compatible certificate is held) is the charm's responsibility.
- "Operator configuration takes precedence" means explicitly set values; values left at defaults are eligible for adaptation.
- Integration tests covering both upgrade paths (old requirer + new provider, new requirer + old provider) are required and in scope.
