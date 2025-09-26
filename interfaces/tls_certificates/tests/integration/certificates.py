#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.


import datetime

from cryptography import x509


class Certificate:
    def __init__(self, certificate_str: str):
        """Initialize the Certificate class.

        Args:
          certificate_str (str): The certificate in PEM format.
        """
        self.certificate_str = certificate_str
        self.certificate = x509.load_pem_x509_certificate(self.certificate_str.encode("utf-8"))

    @property
    def expiry(self) -> datetime.datetime:
        return self.certificate.not_valid_after_utc
