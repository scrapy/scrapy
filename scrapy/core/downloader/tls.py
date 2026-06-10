from __future__ import annotations

import logging
import warnings
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
from twisted.internet.ssl import AcceptableCiphers, TLSVersion

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils.deprecate import create_deprecated_class

if TYPE_CHECKING:
    from collections.abc import Callable

    from OpenSSL.crypto import X509
    from twisted.protocols.tls import TLSMemoryBIOProtocol


logger = logging.getLogger(__name__)


_openssl_methods: dict[str, int] = {
    "TLS": SSL.SSLv23_METHOD,  # protocol negotiation (recommended)
    "TLSv1.0": SSL.TLSv1_METHOD,  # TLS 1.0 only
    "TLSv1.1": SSL.TLSv1_1_METHOD,  # TLS 1.1 only
    "TLSv1.2": SSL.TLSv1_2_METHOD,  # TLS 1.2 only
}


def __getattr__(name: str) -> Any:
    deprecated = {
        "METHOD_TLS": "TLS",
        "METHOD_TLSv10": "TLSv1.0",
        "METHOD_TLSv11": "TLSv1.1",
        "METHOD_TLSv12": "TLSv1.2",
        "openssl_methods": _openssl_methods,
    }
    if name in deprecated:
        warnings.warn(
            f"scrapy.core.downloader.tls.{name} is deprecated.",
            ScrapyDeprecationWarning,
            stacklevel=2,
        )
        return deprecated[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


_TWISTED_VERSION_MAP: dict[str, TLSVersion] = {
    "TLSv1.0": TLSVersion.TLSv1_0,
    "TLSv1.1": TLSVersion.TLSv1_1,
    "TLSv1.2": TLSVersion.TLSv1_2,
    "TLSv1.3": TLSVersion.TLSv1_3,
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
    :class:`._ScrapyClientContextFactory`.

    This class is used on Twisted 26.4.0 and newer.
    """

    def clientConnectionForTLS(
        self, tlsProtocol: TLSMemoryBIOProtocol
    ) -> SSL.Connection:
        """This method is needed to override the verify callback."""
        conn = super().clientConnectionForTLS(tlsProtocol)
        callback = self._verifyCB(self._hostnameIsDnsName, self._hostnameASCII)
        conn.set_verify(SSL.VERIFY_PEER | SSL.VERIFY_FAIL_IF_NO_PEER_CERT, callback)
        return conn

    @staticmethod
    def _verifyCB(
        hostIsDNS: bool, hostnameASCII: str
    ) -> Callable[[SSL.Connection, X509, int, int, int], bool]:
        svcid: ServiceID = (
            DNS_ID(hostnameASCII) if hostIsDNS else IPAddress_ID(hostnameASCII)
        )

        def verifyCallback(
            conn: SSL.Connection, cert: X509, err: int, depth: int, ok: int
        ) -> bool:
            if depth != 0:
                # We are only verifying the leaf certificate.
                return True

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
