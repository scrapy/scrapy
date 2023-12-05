"""
`pyOpenSSL <https://github.com/pyca/pyopenssl>`_-specific code.
"""

from __future__ import annotations

import contextlib
import warnings

from typing import Sequence

from pyasn1.codec.der.decoder import decode
from pyasn1.type.char import IA5String
from pyasn1.type.univ import ObjectIdentifier
from pyasn1_modules.rfc2459 import GeneralNames

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


with contextlib.suppress(ImportError):
    # We only use it for docstrings -- `if TYPE_CHECKING`` does not work.
    from OpenSSL.crypto import X509
    from OpenSSL.SSL import Connection


__all__ = ["verify_hostname"]


def verify_hostname(connection: Connection, hostname: str) -> None:
    """
    Verify whether the certificate of *connection* is valid for *hostname*.

    :param connection: A pyOpenSSL connection object.
    :param hostname: The hostname that *connection* should be connected to.

    :raises service_identity.VerificationError: If *connection* does not
        provide a certificate that is valid for *hostname*.
    :raises service_identity.CertificateError: If the certificate chain of
        *connection* contains a certificate that contains invalid/unexpected
        data.

    :returns: ``None``
    """
    verify_service_identity(
        cert_patterns=extract_patterns(
            connection.get_peer_certificate()  # type:ignore[arg-type]
        ),
        obligatory_ids=[DNS_ID(hostname)],
        optional_ids=[],
    )


def verify_ip_address(connection: Connection, ip_address: str) -> None:
    """
    Verify whether the certificate of *connection* is valid for *ip_address*.

    :param connection: A pyOpenSSL connection object.
    :param ip_address: The IP address that *connection* should be connected to.
        Can be an IPv4 or IPv6 address.

    :raises service_identity.VerificationError: If *connection* does not
        provide a certificate that is valid for *ip_address*.
    :raises service_identity.CertificateError: If the certificate chain of
        *connection* contains a certificate that contains invalid/unexpected
        data.

    :returns: ``None``

    .. versionadded:: 18.1.0
    """
    verify_service_identity(
        cert_patterns=extract_patterns(
            connection.get_peer_certificate()  # type:ignore[arg-type]
        ),
        obligatory_ids=[IPAddress_ID(ip_address)],
        optional_ids=[],
    )


ID_ON_DNS_SRV = ObjectIdentifier("1.3.6.1.5.5.7.8.7")  # id_on_dnsSRV


def extract_patterns(cert: X509) -> Sequence[CertificatePattern]:
    """
    Extract all valid ID patterns from a certificate for service verification.

    :param cert: The certificate to be dissected.

    :return: List of IDs.

    .. versionchanged:: 23.1.0
       ``commonName`` is not used as a fallback anymore.
    """
    ids: list[CertificatePattern] = []
    for i in range(cert.get_extension_count()):
        ext = cert.get_extension(i)
        if ext.get_short_name() == b"subjectAltName":
            names, _ = decode(ext.get_data(), asn1Spec=GeneralNames())
            for n in names:
                name_string = n.getName()
                if name_string == "dNSName":
                    ids.append(
                        DNSPattern.from_bytes(n.getComponent().asOctets())
                    )
                elif name_string == "iPAddress":
                    ids.append(
                        IPAddressPattern.from_bytes(
                            n.getComponent().asOctets()
                        )
                    )
                elif name_string == "uniformResourceIdentifier":
                    ids.append(
                        URIPattern.from_bytes(n.getComponent().asOctets())
                    )
                elif name_string == "otherName":
                    comp = n.getComponent()
                    oid = comp.getComponentByPosition(0)
                    if oid == ID_ON_DNS_SRV:
                        srv, _ = decode(comp.getComponentByPosition(1))
                        if isinstance(srv, IA5String):
                            ids.append(SRVPattern.from_bytes(srv.asOctets()))
                        else:  # pragma: no cover
                            raise CertificateError(
                                "Unexpected certificate content."
                            )
                    else:  # pragma: no cover
                        pass
                else:  # pragma: no cover
                    pass

    return ids


def extract_ids(cert: X509) -> Sequence[CertificatePattern]:
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
