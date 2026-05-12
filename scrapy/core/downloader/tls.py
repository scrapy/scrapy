from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from OpenSSL import SSL
from service_identity import VerificationError
from service_identity.exceptions import CertificateError
from service_identity.hazmat import (
    DNS_ID,
    IPAddress_ID,
    ServiceID,
    verify_service_identity,
)
from service_identity.pyopenssl import (
    extract_patterns,
    verify_hostname,
    verify_ip_address,
)
from twisted.internet._sslverify import ClientTLSOptions
from twisted.internet.ssl import AcceptableCiphers

from scrapy.utils.deprecate import create_deprecated_class

if TYPE_CHECKING:
    from collections.abc import Callable

    from OpenSSL.crypto import X509
    from twisted.protocols.tls import TLSMemoryBIOProtocol


logger = logging.getLogger(__name__)


METHOD_TLS = "TLS"
METHOD_TLSv10 = "TLSv1.0"
METHOD_TLSv11 = "TLSv1.1"
METHOD_TLSv12 = "TLSv1.2"


openssl_methods: dict[str, int] = {
    METHOD_TLS: SSL.SSLv23_METHOD,  # protocol negotiation (recommended)
    METHOD_TLSv10: SSL.TLSv1_METHOD,  # TLS 1.0 only
    METHOD_TLSv11: SSL.TLSv1_1_METHOD,  # TLS 1.1 only
    METHOD_TLSv12: SSL.TLSv1_2_METHOD,  # TLS 1.2 only
}


class _ScrapyClientTLSOptions(ClientTLSOptions):
    """
    SSL Client connection creator ignoring certificate verification errors
    (for genuinely invalid certificates or bugs in verification code).

    Same as Twisted's private _sslverify.ClientTLSOptions,
    except that VerificationError, CertificateError and ValueError
    exceptions are caught, so that the connection is not closed, only
    logging warnings.

    Instances of this class are returned from
    :class:`._ScrapyClientContextFactory`.

    This class is used on Twisted older than 26.4.0.
    """

    def _identityVerifyingInfoCallback(
        self, connection: SSL.Connection, where: int, ret: Any
    ) -> None:
        if where & SSL.SSL_CB_HANDSHAKE_DONE:
            try:
                if self._hostnameIsDnsName:
                    verify_hostname(connection, self._hostnameASCII)
                else:
                    verify_ip_address(connection, self._hostnameASCII)
            except (CertificateError, VerificationError) as e:
                logger.warning(
                    'Remote certificate is not valid for hostname "%s"; %s',
                    self._hostnameASCII,
                    e,
                )
            except ValueError as e:
                logger.warning(
                    "Ignoring error while verifying certificate "
                    'from host "%s" (exception: %r)',
                    self._hostnameASCII,
                    e,
                )
        else:
            super()._identityVerifyingInfoCallback(connection, where, ret)  # type: ignore[misc]


ScrapyClientTLSOptions = create_deprecated_class(
    "ScrapyClientTLSOptions",
    _ScrapyClientTLSOptions,
    subclass_warn_message="{old} is deprecated.",
    instance_warn_message="{cls} is deprecated.",
)


class _ScrapyClientTLSOptions26(ClientTLSOptions):
    """
    SSL Client connection creator ignoring certificate verification errors
    (for genuinely invalid certificates or bugs in verification code).

    Same as Twisted's private _sslverify.ClientTLSOptions,
    except that VerificationError, CertificateError and ValueError
    exceptions are caught, so that the connection is not closed, only
    logging warnings.

    Instances of this class are returned from
    :class:`.ScrapyClientContextFactory`.

    This class is used on Twisted 26.4.0 and newer.
    """

    def __init__(
        self,
        createConnection: Callable[[TLSMemoryBIOProtocol], SSL.Connection],
        hostname: str,
        verbose_logging: bool = False,
    ):
        super().__init__(createConnection, hostname)
        self.verbose_logging: bool = verbose_logging

    def clientConnectionForTLS(
        self, tlsProtocol: TLSMemoryBIOProtocol
    ) -> SSL.Connection:
        """This method is needed to override the verify callback."""
        conn = super().clientConnectionForTLS(tlsProtocol)
        callback = self._verifyCB(
            self._hostnameIsDnsName, self._hostnameASCII, self.verbose_logging
        )
        conn.set_verify(SSL.VERIFY_PEER | SSL.VERIFY_FAIL_IF_NO_PEER_CERT, callback)
        return conn

    @staticmethod
    def _verifyCB(
        hostIsDNS: bool, hostnameASCII: str, verbose_logging: bool
    ) -> Callable[[SSL.Connection, X509, int, int, int], bool]:
        svcid: ServiceID = (
            DNS_ID(hostnameASCII) if hostIsDNS else IPAddress_ID(hostnameASCII)
        )

        def verifyCallback(
            conn: SSL.Connection, cert: X509, err: int, depth: int, ok: int
        ) -> bool:
            if depth != 0:
                # We are only verifying the leaf certificate.
                return bool(ok)

            try:
                verify_service_identity(extract_patterns(cert), [svcid], [])
            except (CertificateError, VerificationError) as e:
                logger.warning(
                    'Remote certificate is not valid for hostname "%s"; %s',
                    hostnameASCII,
                    e,
                )
            except ValueError as e:
                logger.warning(
                    "Ignoring error while verifying certificate "
                    'from host "%s" (exception: %r)',
                    hostnameASCII,
                    e,
                )

            return True

        return verifyCallback


DEFAULT_CIPHERS: AcceptableCiphers = AcceptableCiphers.fromOpenSSLCipherString(
    "DEFAULT"
)
