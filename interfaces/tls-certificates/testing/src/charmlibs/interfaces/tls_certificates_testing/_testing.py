# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

from __future__ import annotations

import datetime
import typing

from ops import testing

from charmlibs.interfaces import tls_certificates

from . import _raw

if typing.TYPE_CHECKING:
    from collections.abc import Iterable

DEFAULT_PRIVATE_KEY = tls_certificates.PrivateKey(raw=_raw.KEY)
_INTERFACE_NAME = "tls-certificates"
_REQUEST = tls_certificates.CertificateRequestAttributes(common_name="example.com")
_CA_CERT = tls_certificates.Certificate(raw=_raw.CERT)


class _RelationKwargs(typing.TypedDict, total=False):
    local_app_data: dict[str, str]
    local_unit_data: dict[str, str]
    remote_app_data: dict[str, str]
    remote_units_data: dict[int, dict[str, str]]


def relation_for_requirer(
    # testing.Relation args
    endpoint: str,
    *,
    # charmlibs.interfaces.tls_certificates args
    mode: tls_certificates.Mode = tls_certificates.Mode.UNIT,
    certificate_requests: Iterable[tls_certificates.CertificateRequestAttributes] = (_REQUEST,),
    # interface 'conversation' args
    provider: bool = True,
) -> testing.Relation:
    kwargs: _RelationKwargs = {}
    csrs = _make_csrs(certificate_requests, key=DEFAULT_PRIVATE_KEY)
    # local requirer
    if mode is tls_certificates.Mode.APP:
        kwargs["local_app_data"] = _dump_requirer(csrs)
    else:
        kwargs["local_unit_data"] = _dump_requirer(csrs)
    # remote provider
    if provider:
        kwargs["remote_app_data"] = _dump_provider(csrs, key=DEFAULT_PRIVATE_KEY)
    return _relation(endpoint, kwargs=kwargs)


def relation_for_provider(
    # testing.Relation args
    endpoint: str,
    *,
    # charmlibs.interfaces.tls_certificates args
    mode: tls_certificates.Mode = tls_certificates.Mode.UNIT,
    certificate_requests: Iterable[tls_certificates.CertificateRequestAttributes] = (_REQUEST,),
    private_key: tls_certificates.PrivateKey = DEFAULT_PRIVATE_KEY,
    # interface 'conversation' args
    provider: bool = True,
) -> testing.Relation:
    kwargs: _RelationKwargs = {}
    csrs = _make_csrs(certificate_requests, key=private_key)
    # remote requirer
    if mode is tls_certificates.Mode.APP:
        kwargs["remote_app_data"] = _dump_requirer(csrs)
    else:
        kwargs["remote_units_data"] = {0: _dump_requirer(csrs)}
    # local provider
    if provider:
        kwargs["local_app_data"] = _dump_provider(csrs, key=private_key)
    return _relation(endpoint, kwargs=kwargs)


def _make_csrs(
    certificate_requests: Iterable[tls_certificates.CertificateRequestAttributes],
    key: tls_certificates.PrivateKey,
) -> list[tls_certificates.CertificateSigningRequest]:
    return [
        tls_certificates.CertificateSigningRequest.generate(attributes=r, private_key=key)
        for r in certificate_requests
    ]


def _dump_requirer(csrs: Iterable[tls_certificates.CertificateSigningRequest]) -> dict[str, str]:
    requirer = tls_certificates._tls_certificates._RequirerData(
        certificate_signing_requests=[
            tls_certificates._tls_certificates._CertificateSigningRequest(
                certificate_signing_request=str(csr).strip(),
                ca=False,
            )
            for csr in csrs
        ]
    )
    ret: dict[str, str] = {}
    requirer.dump(ret)
    return ret


def _dump_provider(
    csrs: Iterable[tls_certificates.CertificateSigningRequest], key: tls_certificates.PrivateKey
) -> dict[str, str]:
    provider = tls_certificates._tls_certificates._ProviderApplicationData(
        certificates=[
            tls_certificates._tls_certificates._Certificate(
                certificate=str(_sign(csr, key=key)),
                certificate_signing_request=str(csr),
                ca=str(_CA_CERT),
                chain=[],
            )
            for csr in csrs
        ]
    )
    ret: dict[str, str] = {}
    provider.dump(ret)
    return ret


def _sign(
    csr: tls_certificates.CertificateSigningRequest, key: tls_certificates.PrivateKey
) -> tls_certificates.Certificate:
    return csr.sign(ca=_CA_CERT, ca_private_key=key, validity=datetime.timedelta(days=42))


def _relation(endpoint: str, kwargs: _RelationKwargs) -> testing.Relation:
    return testing.Relation(endpoint, interface=_INTERFACE_NAME, **kwargs)
