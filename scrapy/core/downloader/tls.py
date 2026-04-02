import logging
from typing import Any

from OpenSSL import SSL
from service_identity import VerificationError
from service_identity.exceptions import CertificateError
from service_identity.pyopenssl import verify_hostname, verify_ip_address
from twisted.internet._sslverify import ClientTLSOptions
from twisted.internet.ssl import AcceptableCiphers

from scrapy.utils.deprecate import create_deprecated_class

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
            super()._identityVerifyingInfoCallback(connection, where, ret)  # type: ignore[no-untyped-call]


ScrapyClientTLSOptions = create_deprecated_class(
    "ScrapyClientTLSOptions",
    _ScrapyClientTLSOptions,
    subclass_warn_message="{old} is deprecated.",
    instance_warn_message="{cls} is deprecated.",
)


DEFAULT_CIPHERS: AcceptableCiphers = AcceptableCiphers.fromOpenSSLCipherString(
    "DEFAULT"
)
