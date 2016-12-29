import logging
from OpenSSL import SSL


logger = logging.getLogger(__name__)

METHOD_SSLv3 = 'SSLv3'
METHOD_TLS = 'TLS'
METHOD_TLSv10 = 'TLSv1.0'
METHOD_TLSv11 = 'TLSv1.1'
METHOD_TLSv12 = 'TLSv1.2'

openssl_methods = {
    METHOD_TLS:    SSL.SSLv23_METHOD,                   # protocol negotiation (recommended)
    METHOD_SSLv3:  SSL.SSLv3_METHOD,                    # SSL 3 (NOT recommended)
    METHOD_TLSv10: SSL.TLSv1_METHOD,                    # TLS 1.0 only
    METHOD_TLSv11: getattr(SSL, 'TLSv1_1_METHOD', 5),   # TLS 1.1 only
    METHOD_TLSv12: getattr(SSL, 'TLSv1_2_METHOD', 6),   # TLS 1.2 only
}

# ClientTLSOptions requires a recent-enough version of Twisted
try:

    # taken from twisted/twisted/internet/_sslverify.py
    try:
        from OpenSSL.SSL import SSL_CB_HANDSHAKE_DONE, SSL_CB_HANDSHAKE_START
    except ImportError:
        SSL_CB_HANDSHAKE_START = 0x10
        SSL_CB_HANDSHAKE_DONE = 0x20

    from twisted.internet.ssl import AcceptableCiphers
    from twisted.internet._sslverify import (ClientTLSOptions,
                                             _maybeSetHostNameIndication,
                                             verifyHostname,
                                             VerificationError)

    class ScrapyClientTLSOptions(ClientTLSOptions):
        """
        SSL Client connection creator ignoring certificate verification errors
        (for genuinely invalid certificates or bugs in verification code).

        Same as Twisted's private _sslverify.ClientTLSOptions,
        except that VerificationError and ValueError exceptions are caught,
        so that the connection is not closed, only logging warnings.
        """

        def _identityVerifyingInfoCallback(self, connection, where, ret):
            if where & SSL_CB_HANDSHAKE_START:
                _maybeSetHostNameIndication(connection, self._hostnameBytes)
            elif where & SSL_CB_HANDSHAKE_DONE:
                try:
                    verifyHostname(connection, self._hostnameASCII)
                except VerificationError as e:
                    logger.warning(
                        'Remote certificate is not valid for hostname "{}"; {}'.format(
                            self._hostnameASCII, e))

                except ValueError as e:
                    logger.warning(
                        'Ignoring error while verifying certificate '
                        'from host "{}" (exception: {})'.format(
                            self._hostnameASCII, repr(e)))

    DEFAULT_CIPHERS = AcceptableCiphers.fromOpenSSLCipherString('DEFAULT')

except ImportError:
    # ImportError should not matter for older Twisted versions
    # as the above is not used in the fallback ScrapyClientContextFactory
    pass
