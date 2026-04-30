from __future__ import annotations

import warnings
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, cast

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
from scrapy.utils.deprecate import create_deprecated_class
from scrapy.utils.misc import build_from_crawler, load_object

if TYPE_CHECKING:
    from collections.abc import Generator

    from twisted.internet._sslverify import ClientTLSOptions

    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.crawler import Crawler
    from scrapy.settings import BaseSettings


@contextmanager
def _filter_method_warning() -> Generator[None]:
    with warnings.catch_warnings():
        # Twisted deprecation, https://github.com/scrapy/scrapy/issues/3288
        warnings.filterwarnings(
            "ignore",
            message=r"Passing method to twisted\.internet\.ssl\.CertificateOptions",
            category=DeprecationWarning,
        )
        yield


@implementer(IPolicyForHTTPS)
class _ScrapyClientContextFactory(BrowserLikePolicyForHTTPS):
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
        verify_certificates: bool = False,
        **kwargs: Any,
    ):
        super().__init__(*args, **kwargs)  # type: ignore[no-untyped-call]
        self._ssl_method: int = method
        self.tls_verbose_logging: bool = tls_verbose_logging  # unused
        self.tls_ciphers: AcceptableCiphers
        if tls_ciphers:
            self.tls_ciphers = AcceptableCiphers.fromOpenSSLCipherString(tls_ciphers)
        else:
            self.tls_ciphers = DEFAULT_CIPHERS
        self._verify_certificates = verify_certificates

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
        verify_certificates = crawler.settings.getbool("DOWNLOAD_VERIFY_CERTIFICATES")
        return cls(  # type: ignore[misc]
            *args,
            method=method,
            tls_verbose_logging=tls_verbose_logging,
            tls_ciphers=tls_ciphers,
            verify_certificates=verify_certificates,
            **kwargs,
        )

    # should be removed together with ScrapyClientContextFactory
    def getCertificateOptions(self) -> CertificateOptions:  # pragma: no cover
        return self._get_cert_options()

    def _get_cert_options(self) -> CertificateOptions:
        with _filter_method_warning():
            return CertificateOptions(
                method=self._ssl_method,
                fixBrokenPeers=True,
                acceptableCiphers=self.tls_ciphers,
            )

    # kept for old-style HTTP/1.0 downloader context twisted calls,
    # e.g. connectSSL()
    # should be removed together with ScrapyClientContextFactory
    def getContext(self, hostname: Any = None, port: Any = None) -> SSL.Context:
        return self._get_context()

    def _get_context(self) -> SSL.Context:
        cert_options = self._get_cert_options()
        ctx = cert_options.getContext()
        ctx.set_options(0x4)  # OP_LEGACY_SERVER_CONNECT
        return ctx

    def creatorForNetloc(self, hostname: bytes, port: int) -> ClientTLSOptions:
        if not self._verify_certificates:
            # _ScrapyClientTLSOptions is needed to skip verification errors
            return _ScrapyClientTLSOptions(
                hostname.decode("ascii"), self._get_context()
            )  # type: ignore[no-untyped-call]
        # Otherwise use the normal Twisted function.
        # Note that this doesn't use self._get_context().
        with _filter_method_warning():
            return optionsForClientTLS(
                hostname=hostname.decode("ascii"),
                extraCertificateOptions={
                    "method": self._ssl_method,
                    "acceptableCiphers": self.tls_ciphers,
                },
            )


ScrapyClientContextFactory = create_deprecated_class(
    "ScrapyClientContextFactory",
    _ScrapyClientContextFactory,
    subclass_warn_message="{old} is deprecated.",
    instance_warn_message="{cls} is deprecated.",
)


@implementer(IPolicyForHTTPS)
class BrowserLikeContextFactory(_ScrapyClientContextFactory):
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

    def __init__(self, *args: Any, **kwargs: Any):
        warnings.warn(
            "BrowserLikeContextFactory is deprecated."
            " You can set DOWNLOAD_VERIFY_CERTIFICATES=True to enable"
            " certificate verification instead of using it.",
            category=ScrapyDeprecationWarning,
            stacklevel=2,
        )
        super().__init__(*args, **kwargs)

    def creatorForNetloc(self, hostname: bytes, port: int) -> ClientTLSOptions:
        with _filter_method_warning():
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
    if crawler.settings["DOWNLOADER_CLIENTCONTEXTFACTORY"] == "SENTINEL":
        context_factory_cls = _ScrapyClientContextFactory
    else:  # pragma: no cover
        warnings.warn(
            "The 'DOWNLOADER_CLIENTCONTEXTFACTORY' setting is deprecated.",
            category=ScrapyDeprecationWarning,
            stacklevel=2,
        )
        context_factory_cls = load_object(
            crawler.settings["DOWNLOADER_CLIENTCONTEXTFACTORY"]
        )
    ssl_method = openssl_methods[crawler.settings.get("DOWNLOADER_CLIENT_TLS_METHOD")]
    return cast(
        "IPolicyForHTTPS",
        build_from_crawler(
            context_factory_cls,
            crawler,
            method=ssl_method,
        ),
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
