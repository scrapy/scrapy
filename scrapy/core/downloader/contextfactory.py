from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Any

from OpenSSL import SSL
from twisted.internet._sslverify import _setAcceptableProtocols
from twisted.internet.ssl import (
    AcceptableCiphers,
    CertificateOptions,
    optionsForClientTLS,
)
from twisted.web.client import BrowserLikePolicyForHTTPS
from twisted.web.iweb import IPolicyForHTTPS
from zope.interface.declarations import implementer
from zope.interface.verify import verifyObject

from scrapy.core.downloader.tls import (
    DEFAULT_CIPHERS,
    _ScrapyClientTLSOptions,
    openssl_methods,
)
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils.deprecate import create_deprecated_class, method_is_overridden
from scrapy.utils.misc import build_from_crawler, load_object

if TYPE_CHECKING:
    from twisted.internet._sslverify import ClientTLSOptions

    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.crawler import Crawler
    from scrapy.settings import BaseSettings


@implementer(IPolicyForHTTPS)
class ScrapyClientContextFactory(BrowserLikePolicyForHTTPS):
    """Non-peer-certificate verifying HTTPS context factory.

    Default OpenSSL method is ``TLS_METHOD`` (also called ``SSLv23_METHOD``)
    which allows TLS protocol negotiation.

    The purpose of this custom class is to provide a ``creatorForNetloc()``
    method that returns a ``_ScrapyClientTLSOptions`` instance configured based
    on TLS settings provided to the factory.
    """

    def __init__(
        self,
        method: int = SSL.SSLv23_METHOD,  # noqa: S503
        tls_verbose_logging: bool = False,
        tls_ciphers: str | None = None,
        *args: Any,
        **kwargs: Any,
    ):
        super().__init__(*args, **kwargs)  # type: ignore[no-untyped-call]
        self._ssl_method: int = method
        self.tls_verbose_logging: bool = tls_verbose_logging
        self.tls_ciphers: AcceptableCiphers
        if tls_ciphers:
            self.tls_ciphers = AcceptableCiphers.fromOpenSSLCipherString(tls_ciphers)
        else:
            self.tls_ciphers = DEFAULT_CIPHERS
        self._certificate_options = CertificateOptions(
            method=self._ssl_method,
            fixBrokenPeers=True,
            acceptableCiphers=self.tls_ciphers,
        )
        self._ctx = self._get_context()
        if method_is_overridden(type(self), ScrapyClientContextFactory, "getContext"):
            warnings.warn(
                "Overriding ScrapyClientContextFactory.getContext() is deprecated and that method"
                " will be removed in a future Scrapy version. Override creatorForNetloc() instead.",
                category=ScrapyDeprecationWarning,
                stacklevel=2,
            )
        if method_is_overridden(
            type(self), ScrapyClientContextFactory, "getCertificateOptions"
        ):  # pragma: no cover
            warnings.warn(
                "Overriding ScrapyClientContextFactory.getCertificateOptions() is deprecated and that method"
                " will be removed in a future Scrapy version. Override creatorForNetloc() instead.",
                category=ScrapyDeprecationWarning,
                stacklevel=2,
            )

    @classmethod
    def from_crawler(
        cls,
        crawler: Crawler,
        method: int = SSL.SSLv23_METHOD,  # noqa: S503
        *args: Any,
        **kwargs: Any,
    ) -> Self:
        tls_verbose_logging: bool = crawler.settings.getbool(
            "DOWNLOADER_CLIENT_TLS_VERBOSE_LOGGING"
        )
        tls_ciphers: str | None = crawler.settings["DOWNLOADER_CLIENT_TLS_CIPHERS"]
        return cls(  # type: ignore[misc]
            *args,
            method=method,
            tls_verbose_logging=tls_verbose_logging,
            tls_ciphers=tls_ciphers,
            **kwargs,
        )

    def getCertificateOptions(self) -> CertificateOptions:  # pragma: no cover
        warnings.warn(
            "ScrapyClientContextFactory.getCertificateOptions() is deprecated.",
            ScrapyDeprecationWarning,
            stacklevel=2,
        )
        return self._certificate_options

    # kept for old-style HTTP/1.0 downloader context twisted calls,
    # e.g. connectSSL()
    def getContext(self, hostname: Any = None, port: Any = None) -> SSL.Context:
        warnings.warn(
            "ScrapyClientContextFactory.getContext() is deprecated.",
            ScrapyDeprecationWarning,
            stacklevel=2,
        )
        return self._ctx

    def _get_context(self) -> SSL.Context:
        ctx = self._certificate_options.getContext()
        ctx.set_options(0x4)  # OP_LEGACY_SERVER_CONNECT
        return ctx

    def creatorForNetloc(self, hostname: bytes, port: int) -> ClientTLSOptions:
        return _ScrapyClientTLSOptions(
            hostname.decode("ascii"),
            self._ctx,
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

    As this overrides the parent ``creatorForNetloc()`` method, only
    ``self._ssl_method`` is used from the parent class.
    """

    def creatorForNetloc(self, hostname: bytes, port: int) -> ClientTLSOptions:
        return optionsForClientTLS(
            hostname=hostname.decode("ascii"),
            extraCertificateOptions={"method": self._ssl_method},
        )


@implementer(IPolicyForHTTPS)
class _AcceptableProtocolsContextFactory:
    """Context factory to used to override the acceptable protocols
    to set up the :class:`OpenSSL.SSL.Context` for doing ALPN negotiation.
    It's a private class for :class:`~.H2DownloadHandler`.

    This class wraps ``creatorForNetloc()`` of another factory class, setting
    the acceptable protocols on the :class:`.ClientTLSOptions` instance
    returned by it. It's only needed because we support custom factories via
    :setting:`DOWNLOADER_CLIENTCONTEXTFACTORY`.
    """

    def __init__(self, context_factory: Any, acceptable_protocols: list[bytes]):
        verifyObject(IPolicyForHTTPS, context_factory)
        self._wrapped_context_factory: Any = context_factory
        self._acceptable_protocols: list[bytes] = acceptable_protocols

    def creatorForNetloc(self, hostname: bytes, port: int) -> ClientTLSOptions:
        options: ClientTLSOptions = self._wrapped_context_factory.creatorForNetloc(
            hostname, port
        )
        _setAcceptableProtocols(options._ctx, self._acceptable_protocols)
        return options


AcceptableProtocolsContextFactory = create_deprecated_class(
    "AcceptableProtocolsContextFactory",
    _AcceptableProtocolsContextFactory,
    subclass_warn_message="{old} is deprecated.",
    instance_warn_message="{cls} is deprecated.",
)


def _load_context_factory_from_settings(crawler: Crawler) -> IPolicyForHTTPS:
    """Create an instance of :setting:`DOWNLOADER_CLIENTCONTEXTFACTORY`.

    Also passes values of other relevant settings to the factory class.
    """
    ssl_method = openssl_methods[crawler.settings.get("DOWNLOADER_CLIENT_TLS_METHOD")]
    context_factory_cls = load_object(
        crawler.settings["DOWNLOADER_CLIENTCONTEXTFACTORY"]
    )
    return build_from_crawler(
        context_factory_cls,
        crawler,
        method=ssl_method,
    )


def load_context_factory_from_settings(
    settings: BaseSettings, crawler: Crawler
) -> IPolicyForHTTPS:  # pragma: no cover
    warnings.warn(
        "load_context_factory_from_settings() is deprecated.",
        ScrapyDeprecationWarning,
        stacklevel=2,
    )
    return _load_context_factory_from_settings(crawler)
