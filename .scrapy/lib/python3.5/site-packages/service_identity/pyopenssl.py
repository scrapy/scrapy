"""
`pyOpenSSL <https://github.com/pyca/pyopenssl>`_-specific code.
"""

from __future__ import absolute_import, division, print_function

import warnings

from pyasn1.codec.der.decoder import decode
from pyasn1.type.char import IA5String
from pyasn1.type.univ import ObjectIdentifier
from pyasn1_modules.rfc2459 import GeneralNames

from .exceptions import SubjectAltNameWarning
from ._common import (
    CertificateError,
    DNSPattern,
    DNS_ID,
    SRVPattern,
    URIPattern,
    verify_service_identity,
)


def verify_hostname(connection, hostname):
    """
    Verify whether the certificate of *connection* is valid for *hostname*.

    :param connection: A pyOpenSSL connection object.
    :type connection: :class:`OpenSSL.SSL.Connection`

    :param hostname: The hostname that *connection* should be connected to.
    :type hostname: :class:`unicode`

    :raises service_identity.VerificationError: If *connection* does not
        provide a certificate that is valid for *hostname*.
    :raises service_identity.CertificateError: If the certificate chain of
        *connection* contains a certificate that contains invalid/unexpected
        data.

    :returns: ``None``
    """
    verify_service_identity(
        cert_patterns=extract_ids(connection.get_peer_certificate()),
        obligatory_ids=[DNS_ID(hostname)],
        optional_ids=[],
    )


ID_ON_DNS_SRV = ObjectIdentifier('1.3.6.1.5.5.7.8.7')  # id_on_dnsSRV


def extract_ids(cert):
    """
    Extract all valid IDs from a certificate for service verification.

    If *cert* doesn't contain any identifiers, the ``CN``s are used as DNS-IDs
    as fallback.

    :param cert: The certificate to be dissected.
    :type cert: :class:`OpenSSL.SSL.X509`

    :return: List of IDs.
    """
    ids = []
    for i in range(cert.get_extension_count()):
        ext = cert.get_extension(i)
        if ext.get_short_name() == b"subjectAltName":
            names, _ = decode(ext.get_data(), asn1Spec=GeneralNames())
            for n in names:
                name_string = n.getName()
                if name_string == "dNSName":
                    ids.append(DNSPattern(n.getComponent().asOctets()))
                elif name_string == "uniformResourceIdentifier":
                    ids.append(URIPattern(n.getComponent().asOctets()))
                elif name_string == "otherName":
                    comp = n.getComponent()
                    oid = comp.getComponentByPosition(0)
                    if oid == ID_ON_DNS_SRV:
                        srv, _ = decode(comp.getComponentByPosition(1))
                        if isinstance(srv, IA5String):
                            ids.append(SRVPattern(srv.asOctets()))
                        else:  # pragma: nocover
                            raise CertificateError(
                                "Unexpected certificate content."
                            )

    if not ids:
        # http://tools.ietf.org/search/rfc6125#section-6.4.4
        # A client MUST NOT seek a match for a reference identifier of CN-ID if
        # the presented identifiers include a DNS-ID, SRV-ID, URI-ID, or any
        # application-specific identifier types supported by the client.
        warnings.warn(
            "Certificate has no `subjectAltName`, falling back to check for a "
            "`commonName` for now.  This feature is being removed by major "
            "browsers and deprecated by RFC 2818.",
            SubjectAltNameWarning
        )
        ids = [DNSPattern(c[1])
               for c
               in cert.get_subject().get_components()
               if c[0] == b"CN"]
    return ids


__all__ = [
    "verify_hostname",
]
