"""
`cryptography.x509 <https://github.com/pyca/cryptography>`_-specific code.
"""

from __future__ import annotations

import warnings

from typing import Sequence

from cryptography.x509 import (
    Certificate,
    DNSName,
    ExtensionOID,
    IPAddress,
    ObjectIdentifier,
    OtherName,
    UniformResourceIdentifier,
)
from cryptography.x509.extensions import ExtensionNotFound
from pyasn1.codec.der.decoder import decode
from pyasn1.type.char import IA5String

from .exceptions import CertificateError
from .hazmat import (
    DNS_ID,
    CertificatePattern,
    DNSPattern,
    IPAddress_ID,
    IPAddressPattern,
    SRVPattern,
    URIPattern,
    verify_service_identity,
)


__all__ = ["verify_certificate_hostname"]


def verify_certificate_hostname(
    certificate: Certificate, hostname: str
) -> None:
    """
    Verify whether *certificate* is valid for *hostname*.

    .. note:: Nothing is verified about the *authority* of the certificate;
       the caller must verify that the certificate chains to an appropriate
       trust root themselves.

    :param certificate: A *cryptography* X509 certificate object.
    :param hostname: The hostname that *certificate* should be valid for.

    :raises service_identity.VerificationError: If *certificate* is not valid
        for *hostname*.
    :raises service_identity.CertificateError: If *certificate* contains
        invalid / unexpected data.

    :returns: ``None``
    """
    verify_service_identity(
        cert_patterns=extract_patterns(certificate),
        obligatory_ids=[DNS_ID(hostname)],
        optional_ids=[],
    )


def verify_certificate_ip_address(
    certificate: Certificate, ip_address: str
) -> None:
    """
    Verify whether *certificate* is valid for *ip_address*.

    .. note:: Nothing is verified about the *authority* of the certificate;
       the caller must verify that the certificate chains to an appropriate
       trust root themselves.

    :param certificate: A *cryptography* X509 certificate object.
    :param ip_address: The IP address that *connection* should be valid
        for.  Can be an IPv4 or IPv6 address.

    :raises service_identity.VerificationError: If *certificate* is not valid
        for *ip_address*.
    :raises service_identity.CertificateError: If *certificate* contains
        invalid / unexpected data.

    :returns: ``None``

    .. versionadded:: 18.1.0
    """
    verify_service_identity(
        cert_patterns=extract_patterns(certificate),
        obligatory_ids=[IPAddress_ID(ip_address)],
        optional_ids=[],
    )


ID_ON_DNS_SRV = ObjectIdentifier("1.3.6.1.5.5.7.8.7")  # id_on_dnsSRV


def extract_patterns(cert: Certificate) -> Sequence[CertificatePattern]:
    """
    Extract all valid ID patterns from a certificate for service verification.

    :param cert: The certificate to be dissected.

    :return: List of IDs.

    .. versionchanged:: 23.1.0
       ``commonName`` is not used as a fallback anymore.
    """
    ids: list[CertificatePattern] = []
    try:
        ext = cert.extensions.get_extension_for_oid(
            ExtensionOID.SUBJECT_ALTERNATIVE_NAME
        )
    except ExtensionNotFound:
        pass
    else:
        ids.extend(
            [
                DNSPattern.from_bytes(name.encode("utf-8"))
                for name in ext.value.get_values_for_type(DNSName)
            ]
        )
        ids.extend(
            [
                URIPattern.from_bytes(uri.encode("utf-8"))
                for uri in ext.value.get_values_for_type(
                    UniformResourceIdentifier
                )
            ]
        )
        ids.extend(
            [
                IPAddressPattern(ip)
                for ip in ext.value.get_values_for_type(IPAddress)
            ]
        )
        for other in ext.value.get_values_for_type(OtherName):
            if other.type_id == ID_ON_DNS_SRV:
                srv, _ = decode(other.value)
                if isinstance(srv, IA5String):
                    ids.append(SRVPattern.from_bytes(srv.asOctets()))
                else:  # pragma: no cover
                    raise CertificateError("Unexpected certificate content.")

    return ids


def extract_ids(cert: Certificate) -> Sequence[CertificatePattern]:
    """
    Deprecated and never public API.  Use :func:`extract_patterns` instead.

    .. deprecated:: 23.1.0
    """
    warnings.warn(
        category=DeprecationWarning,
        message="`extract_ids()` is deprecated, please use `extract_patterns()`.",
        stacklevel=2,
    )
    return extract_patterns(cert)
