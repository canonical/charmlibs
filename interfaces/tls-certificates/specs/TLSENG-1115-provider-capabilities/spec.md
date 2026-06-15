# Feature Specification: Provider Capability Advertisement

**Feature Branch**: `TLSENG-1115`  
**Created**: 2026-06-15  
**Status**: Draft  
**Input**: User description: "Extend the tls-certificates interface (v4) to allow provider charms to advertise their certificate server's capabilities and constraints, so requirer charms can automatically adapt certificate signing requests (CSRs) while preserving operator control."

## User Scenarios & Testing _(mandatory)_

### User Story 1 - Requirer auto-adapts certificate requests to provider capabilities (Priority: P1)

An operator deploys a requirer charm and relates it to any certificate provider (e.g. an ACME/Let's Encrypt-backed provider, a Vault-backed provider, or a self-signed generator) without knowing that provider's specific constraints. The requirer reads the capabilities the provider advertises over the relation and shapes its certificate requests so they are compatible with what the provider can actually issue — without the operator needing to manually configure the requirer per provider.

**Why this priority**: This is the core value of the feature. It removes the manual, error-prone, per-provider configuration burden and eliminates silent CSR rejections, which is the primary problem being solved.

**Independent Test**: Relate a requirer to a provider that advertises a restrictive capability set (e.g. `supports_ip_sans: false`). Confirm that, when relying on defaults, the requirer produces a request that omits IP SANs and successfully obtains a certificate without any operator configuration changes.

**Acceptance Scenarios**:

1. **Given** a provider that advertises a capability set and a requirer using default (non-operator-overridden) attributes, **When** the relation is established, **Then** the requirer constructs certificate request attributes that are compatible with the advertised capabilities and obtains a certificate without operator intervention.
2. **Given** a provider that has not (yet) advertised any capabilities, **When** the requirer builds its certificate requests, **Then** the requirer falls back to its originally configured/default attributes and continues to function.
3. **Given** an operator has explicitly configured a certificate attribute, **When** the requirer builds certificate requests, **Then** the explicit operator configuration takes precedence over any capability-driven adaptation.

---

### User Story 2 - Provider advertises its capabilities and constraints (Priority: P1)

A provider charm publishes a structured, best-effort description of what its backing certificate server can and cannot do (IP SANs, wildcard DNS, CA issuance, subdomains, allowed domains, provider type) into the relation databag. It does this on every hook so that configuration changes on the provider side are reflected to relating requirers.

**Why this priority**: Without the provider publishing capabilities, requirers have nothing to adapt to. This is the data-producing half of the contract and is required for Story 1 to deliver value.

**Independent Test**: Initialize a provider with a known capability set and inspect the relation application databag. Confirm the advertised capabilities match the provider's configuration, and that they update when the provider's configuration changes across hooks.

**Acceptance Scenarios**:

1. **Given** a provider initialized with a capability set, **When** any relation/hook event runs, **Then** the provider writes its capabilities into the relation application data.
2. **Given** a provider whose configuration changes, **When** the next hook executes, **Then** the advertised capabilities reflect the updated configuration.
3. **Given** a provider that chooses not to advertise capabilities, **When** the relation is established, **Then** no capabilities are present in the databag and relating requirers behave as in the pre-feature (legacy) behavior.

---

### User Story 3 - Requirer recovers from a denied request by adapting to capabilities (Priority: P2)

When a requirer's initially configured attributes cannot be fulfilled by the provider (capabilities were unknown at request time, or the operator's intent could not be satisfied), the request is denied. The requirer is notified, adjusts its certificate attributes according to the now-known provider capabilities, and resubmits.

**Why this priority**: This is the resilience/recovery path. It is valuable but secondary to the happy-path adaptation in Stories 1 and 2; the MVP can deliver value without automatic recovery, though recovery substantially improves robustness.

**Independent Test**: Submit a request that the provider will deny (e.g. contains an IP SAN against a provider that rejects IP SANs). Confirm a denial is surfaced to the requirer, and that after the requirer adapts and resubmits, a compatible certificate is issued.

**Acceptance Scenarios**:

1. **Given** a requirer that submitted an incompatible request, **When** the provider denies it, **Then** a certificate-denied notification is surfaced to the requirer.
2. **Given** a requirer that has received a denial and can read the provider's capabilities, **When** it re-derives its attributes from those capabilities and resubmits, **Then** a compatible certificate is issued.
3. **Given** a requirer's attributes were already compatible with the provider's capabilities, **When** capabilities later become available, **Then** no certificate rotation is triggered (capabilities only become more restrictive and do not introduce conflicting changes for an already-compatible request).

---

### Edge Cases

- **Capabilities not yet present**: The requirer MUST fall back to its original configuration and continue to operate.
- **Individual capability unspecified**: When the provider advertises some capabilities but omits others, each omitted attribute is treated as unknown — the requirer MUST NOT assume a value for it and falls back to its configured behavior for that single attribute (it does not discard the capabilities that _were_ advertised).
- **Legacy provider (no capabilities support)**: A requirer related to a provider that never advertises capabilities behaves exactly as before this feature; nothing breaks.
- **Legacy requirer (ignores capabilities)**: A provider advertising capabilities to a requirer that does not read them MUST not change that requirer's existing behavior.
- **Malformed / invalid capabilities data**: When advertised capability data fails validation, the requirer treats it as "capabilities unavailable" (logs a warning and falls back to configuration) rather than failing.
- **Capabilities change after a certificate is issued**: Because capabilities can only become more restrictive, an already-compatible certificate is unaffected and does not need rotation; an attribute that is no longer compatible surfaces via the denial/recovery path on the next request cycle.
- **Operator intent incompatible with capabilities**: The operator's explicit configuration takes precedence; the resulting (possibly incompatible) request may be denied, which then feeds the recovery path. (See clarification below on the exact precedence vs. recovery interaction.)
- **Avoiding rotation churn**: Because provider configuration changes can alter advertised capabilities — which could in turn change requirer attributes and trigger rotation — the requirer must only react to capability changes on deliberate events (e.g. an explicit sync or a denial), not on every attribute/relation change.

## Requirements _(mandatory)_

### Functional Requirements

- **FR-001**: The interface MUST allow a provider to advertise a structured set of certificate-server capabilities and constraints in the relation application data, as an additive and optional element alongside existing relation data (certificates, request errors).
- **FR-002**: The advertised capability set MUST support the following attributes: whether IP addresses are accepted in SANs, whether wildcard DNS entries are accepted, whether subdomain certificates can be issued, whether CA certificates can be issued, an optional list of allowed DNS domains, and an optional provider-type hint string.
- **FR-003**: The provider is the sole source of truth for its capabilities. Each capability attribute MUST be independently optional, and an attribute the provider does not advertise MUST be treated as "unspecified / unknown" — NOT as a default value. The requirer MUST NOT assume any value (neither permissive nor restrictive) for an unspecified attribute; for any attribute the provider has not advertised, the requirer falls back to its own configured/default behavior for the corresponding request attribute.
- **FR-004**: A provider MUST be able to supply its capability set at initialization time, and the library MUST publish/refresh those capabilities into the relation data on relation/hook events so that provider configuration changes are reflected to requirers.
- **FR-005**: A requirer MUST be able to retrieve the provider's currently advertised capabilities through a single library call.
- **FR-006**: When no relation, no remote application, or no valid capability data is available, the requirer's capability retrieval MUST return an "unavailable" result (rather than raising), and the requirer MUST fall back to its original configuration.
- **FR-007**: When advertised capability data cannot be validated, the requirer MUST log a warning and treat capabilities as unavailable.
- **FR-008**: Explicit operator configuration MUST always take precedence over capability-driven adaptation when the requirer constructs certificate request attributes.
- **FR-009**: Capability awareness MUST be best-effort on both sides: requirers MUST NOT assume capabilities are present, and providers MUST NOT be required to advertise them.
- **FR-010**: The change MUST be fully backwards compatible: a capability-aware requirer interoperates with a legacy provider, and a legacy requirer interoperates with a capability-advertising provider, with no behavioral change to existing flows.
- **FR-011**: When a request is denied, the requirer MUST be able to re-derive compatible attributes from the provider's capabilities and resubmit, with rotation/cleanup performed only on deliberate events (e.g. an explicit sync or the denial event), not on every attribute change.
- **FR-012**: An already-compatible certificate request MUST NOT trigger rotation when capabilities later become available, because capabilities only become more restrictive over time.
- **FR-013**: The library MUST provide guidance/affordances so that consuming charms can subscribe to capability/denial-driven refreshes deliberately, to avoid unintended certificate rotations.

### Key Entities _(include if feature involves data)_

- **Provider Capabilities**: The best-effort, structured description a provider advertises about its certificate server. Every attribute is independently optional; an omitted attribute means "not advertised / unknown", never an assumed default. Attributes: supports-IP-SANs (bool), supports-wildcard-DNS (bool), supports-subdomain (bool), supports-CA-certificates (bool), allowed-domains (list of DNS names), provider-type (hint such as "acme", "vault", "self-signed").
- **Provider Application Data**: The provider's relation application data. Extended to carry, in addition to the existing issued certificates and request errors, an optional capabilities element.
- **Certificate Request Attributes**: The set of attributes a requirer asks for (common name, SANs/DNS, organization, etc.). The requirer derives these from operator configuration and, when relying on defaults, adapts them to the advertised capabilities.

## Success Criteria _(mandatory)_

### Measurable Outcomes

- **SC-001**: An operator can relate a default-configured requirer to a capability-advertising provider and obtain a usable certificate with zero provider-specific manual configuration in the common cases (IP SANs, wildcard, subdomain, allowed-domain constraints).
- **SC-002**: Existing deployments are unaffected: 100% of pre-feature requirer↔provider combinations continue to function unchanged when one side is upgraded and the other is not.
- **SC-003**: When a requirer's initial request is incompatible with the provider, the requirer surfaces a denial and, after adaptation, obtains a compatible certificate without operator intervention.
- **SC-004**: An already-compatible certificate request results in zero unnecessary certificate rotations when provider capabilities subsequently become available or change within still-compatible bounds.
- **SC-005**: Invalid or absent capability data never causes a requirer error; in 100% of such cases the requirer falls back to its configured behavior.

## Assumptions

- This work targets the `tls-certificates` interface v4 and its corresponding library classes (provider-side and requirer-side), in line with the existing repository structure.
- Capability adaptation logic that maps a capability set onto concrete request attributes lives in the consuming requirer charm (best-effort), while the library provides the data model, the provider-side setter, and the requirer-side getter.
- "Operator configuration takes precedence" means explicitly set configuration values; values left at their defaults are eligible for capability-driven adaptation.
- The provider is the source of truth: the capability data model represents each attribute as optional with no assumed value, so absence on the wire means "unspecified" rather than a concrete true/false. Any implementation sketch that shows field-level defaults must be reconciled to this rule — a value the provider never advertised is treated by the requirer as unknown, not as that default.
- Capabilities are assumed to only ever become more restrictive over the lifetime of a relation; this assumption underpins the no-unnecessary-rotation guarantees.
- Integration tests covering both upgrade paths (old requirer + new provider, new requirer + old provider) are required by Constitution Principle III and are in scope for this feature.
