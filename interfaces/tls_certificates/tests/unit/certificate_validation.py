#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

# pyright: reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false

from collections.abc import Iterable

from pkilint import loader
from pkilint.pkix import certificate as certificate_lint
from pkilint.pkix import extension, name
from pkilint.validation import (
    ValidationFindingDescription,
    ValidationFindingSeverity,
    ValidationResult,
)

from charmlibs.interfaces.tls_certificates import Certificate

SEVERITY_THRESHOLD = ValidationFindingSeverity.WARNING

validator = certificate_lint.create_pkix_certificate_validator_container(
    certificate_lint.create_decoding_validators(
        name.ATTRIBUTE_TYPE_MAPPINGS, extension.EXTENSION_MAPPINGS
    ),
    [
        certificate_lint.create_issuer_validator_container(),
        certificate_lint.create_validity_validator_container(),
        certificate_lint.create_subject_validator_container(),
        certificate_lint.create_extensions_validator_container(),
        certificate_lint.create_spki_validator_container(),
    ],
)


def _get_violations_from_results(
    results: Iterable[ValidationResult],
) -> list[ValidationFindingDescription]:
    violations = []
    for result in results:
        for finding in result.finding_descriptions:
            if finding.finding.severity <= SEVERITY_THRESHOLD:
                violations += finding

    return violations


def get_violations(
    certificate: str | Certificate,
) -> list[ValidationFindingDescription]:
    """Get violations for the provided certificate.

    Returns a list of RFC5280 violations found in the certificate, including
    both errors and best practices (warnings).
    """
    if isinstance(certificate, Certificate):
        certificate = str(certificate)

    cert = loader.RFC5280CertificateDocumentLoader().load_pem_document(certificate)
    results = validator.validate(cert.root)
    return _get_violations_from_results(results)
