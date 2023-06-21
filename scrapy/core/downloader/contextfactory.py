import warnings
from typing import TYPE_CHECKING, Any, List, Optional

from OpenSSL import SSL
from twisted.internet._sslverify import _setAcceptableProtocols
from twisted.internet.ssl import (
    AcceptableCiphers,
    CertificateOptions,
    optionsForClientTLS,
    platformTrust,
)
from twisted.web.client import BrowserLikePolicyForHTTPS
from twisted.web.iweb import IPolicyForHTTPS
from zope.interface.declarations import implementer
from zope.interface.verify import verifyObject

from scrapy.core.downloader.tls import (
    DEFAULT_CIPHERS,
    ScrapyClientTLSOptions,
    openssl_methods,
)
from scrapy.settings import BaseSettings
from scrapy.utils.misc import create_instance, load_object

if TYPE_CHECKING:
    from twisted.internet._sslverify import ClientTLSOptions


@implementer(IPolicyForHTTPS)
class ScrapyClientContextFactory(BrowserLikePolicyForHTTPS):
    """
    Non-peer-certificate verifying HTTPS context factory

    Default OpenSSL method is TLS_METHOD (also called SSLv23_METHOD)
    which allows TLS protocol negotiation

    'A TLS/SSL connection established with [this method] may
     understand the TLSv1, TLSv1.1 and TLSv1.2 protocols.'
    """

    def __init__(
        self,
        method: int = SSL.SSLv23_METHOD,
        tls_verbose_logging: bool = False,
        tls_ciphers: Optional[str] = None,
        *args: Any,
        **kwargs: Any,
    ):
        super().__init__(*args, **kwargs)
        self._ssl_method: int = method
        self.tls_verbose_logging: bool = tls_verbose_logging
        self.tls_ciphers: AcceptableCiphers
        if tls_ciphers:
            self.tls_ciphers = AcceptableCiphers.fromOpenSSLCipherString(tls_ciphers)
        else:
            self.tls_ciphers = DEFAULT_CIPHERS

    @classmethod
    def from_settings(
        cls,
        settings: BaseSettings,
        method: int = SSL.SSLv23_METHOD,
        *args: Any,
        **kwargs: Any,
    ):
        tls_verbose_logging: bool = settings.getbool(
            "DOWNLOADER_CLIENT_TLS_VERBOSE_LOGGING"
        )
        tls_ciphers: Optional[str] = settings["DOWNLOADER_CLIENT_TLS_CIPHERS"]
        return cls(  # type: ignore[misc]
            method=method,
            tls_verbose_logging=tls_verbose_logging,
            tls_ciphers=tls_ciphers,
            *args,
            **kwargs,
        )

    def getCertificateOptions(self) -> CertificateOptions:
        # setting verify=True will require you to provide CAs
        # to verify against; in other words: it's not that simple

        # backward-compatible SSL/TLS method:
        #
        # * this will respect `method` attribute in often recommended
        #   `ScrapyClientContextFactory` subclass
        #   (https://github.com/scrapy/scrapy/issues/1429#issuecomment-131782133)
        #
        # * getattr() for `_ssl_method` attribute for context factories
        #   not calling super().__init__
        return CertificateOptions(
            verify=False,
            method=getattr(self, "method", getattr(self, "_ssl_method", None)),
            fixBrokenPeers=True,
            acceptableCiphers=self.tls_ciphers,
        )

    # kept for old-style HTTP/1.0 downloader context twisted calls,
    # e.g. connectSSL()
    def getContext(self, hostname: Any = None, port: Any = None) -> SSL.Context:
        ctx = self.getCertificateOptions().getContext()
        ctx.set_options(0x4)  # OP_LEGACY_SERVER_CONNECT
        return ctx

    def creatorForNetloc(self, hostname: bytes, port: int) -> "ClientTLSOptions":
        return ScrapyClientTLSOptions(
            hostname.decode("ascii"),
            self.getContext(),
            verbose_logging=self.tls_verbose_logging,
        )


@implementer(IPolicyForHTTPS)
class BrowserLikeContextFactory(ScrapyClientContextFactory):
    """
    Twisted-recommended context factory for web clients.

    Quoting the documentation of the :class:`~twisted.web.client.Agent` class:

        The default is to use a
        :class:`~twisted.web.client.BrowserLikePolicyForHTTPS`, so unless you
        have special requirements you can leave this as-is.

    :meth:`creatorForNetloc` is the same as
    :class:`~twisted.web.client.BrowserLikePolicyForHTTPS` except this context
    factory allows setting the TLS/SSL method to use.

    The default OpenSSL method is ``TLS_METHOD`` (also called
    ``SSLv23_METHOD``) which allows TLS protocol negotiation.
    """

    def creatorForNetloc(self, hostname: bytes, port: int) -> "ClientTLSOptions":
        # trustRoot set to platformTrust() will use the platform's root CAs.
        #
        # This means that a website like https://www.cacert.org will be rejected
        # by default, since CAcert.org CA certificate is seldom shipped.
        return optionsForClientTLS(
            hostname=hostname.decode("ascii"),
            trustRoot=platformTrust(),
            extraCertificateOptions={"method": self._ssl_method},
        )


@implementer(IPolicyForHTTPS)
class AcceptableProtocolsContextFactory:
    """Context factory to used to override the acceptable protocols
    to set up the [OpenSSL.SSL.Context] for doing NPN and/or ALPN
    negotiation.
    """

    def __init__(self, context_factory: Any, acceptable_protocols: List[bytes]):
        verifyObject(IPolicyForHTTPS, context_factory)
        self._wrapped_context_factory: Any = context_factory
        self._acceptable_protocols: List[bytes] = acceptable_protocols

    def creatorForNetloc(self, hostname: bytes, port: int) -> "ClientTLSOptions":
        options: "ClientTLSOptions" = self._wrapped_context_factory.creatorForNetloc(
            hostname, port
        )
        _setAcceptableProtocols(options._ctx, self._acceptable_protocols)
        return options


def load_context_factory_from_settings(settings, crawler):
    ssl_method = openssl_methods[settings.get("DOWNLOADER_CLIENT_TLS_METHOD")]
    context_factory_cls = load_object(settings["DOWNLOADER_CLIENTCONTEXTFACTORY"])
    # try method-aware context factory
    try:
        context_factory = create_instance(
            objcls=context_factory_cls,
            settings=settings,
            crawler=crawler,
            method=ssl_method,
        )
    except TypeError:
        # use context factory defaults
        context_factory = create_instance(
            objcls=context_factory_cls,
            settings=settings,
            crawler=crawler,
        )
        msg = (
            f"{settings['DOWNLOADER_CLIENTCONTEXTFACTORY']} does not accept "
            "a `method` argument (type OpenSSL.SSL method, e.g. "
            "OpenSSL.SSL.SSLv23_METHOD) and/or a `tls_verbose_logging` "
            "argument and/or a `tls_ciphers` argument. Please, upgrade your "
            "context factory class to handle them or ignore them."
        )
        warnings.warn(msg)

    return context_factory
