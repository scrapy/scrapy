from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Any, cast

from OpenSSL import SSL
from twisted.internet.ssl import (
    AcceptableCiphers,
    CertificateOptions,
    TLSVersion,
    optionsForClientTLS,
)
from twisted.web.client import BrowserLikePolicyForHTTPS
from twisted.web.iweb import IPolicyForHTTPS
from zope.interface.declarations import implementer
from zope.interface.verify import verifyObject

from scrapy.core.downloader.tls import (
    _TWISTED_VERSION_MAP,
    DEFAULT_CIPHERS,
    _openssl_methods,
    _ScrapyClientTLSOptions,
    _ScrapyClientTLSOptions26,
)
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils._deps_compat import TWISTED_TLS_NEW_IMPL
from scrapy.utils.deprecate import create_deprecated_class
from scrapy.utils.misc import build_from_crawler, load_object
from scrapy.utils.ssl import _get_cert_options_version_kwargs, _get_tls_version_limits

if TYPE_CHECKING:
    from twisted.internet._sslverify import ClientTLSOptions

    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.crawler import Crawler
    from scrapy.settings import BaseSettings


@implementer(IPolicyForHTTPS)
class _ScrapyClientContextFactory(BrowserLikePolicyForHTTPS):
    """Non-peer-certificate verifying HTTPS context factory.

    Uses :setting:`DOWNLOADER_CLIENT_TLS_CIPHERS`,
    :setting:`DOWNLOAD_TLS_MIN_VERSION` and :setting:`DOWNLOAD_TLS_MAX_VERSION`
    to configure the :class:`~twisted.internet.ssl.CertificateOptions`
    instance.

    The purpose of this custom class is to provide a ``creatorForNetloc()``
    method that returns a ``_ScrapyClientTLSOptions`` instance configured based
    on TLS settings provided to the factory.
    """

    def __init__(
        self,
        method: int | None = SSL.SSLv23_METHOD,  # noqa: S503
        tls_verbose_logging: bool = False,
        tls_ciphers: str | None = None,
        *args: Any,
        verify_certificates: bool = False,
        tls_min_version: TLSVersion | None = None,
        tls_max_version: TLSVersion | None = None,
        **kwargs: Any,
    ):
        super().__init__(*args, **kwargs)  # type: ignore[no-untyped-call]
        self._ssl_method: int | None = method
        self.tls_min_version: TLSVersion | None = tls_min_version
        self.tls_max_version: TLSVersion | None = tls_max_version
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
        method: int | None = SSL.SSLv23_METHOD,  # noqa: S503
        *args: Any,
        **kwargs: Any,
    ) -> Self:
        tls_verbose_logging: bool = crawler.settings.getbool(
            "DOWNLOADER_CLIENT_TLS_VERBOSE_LOGGING"
        )
        tls_ciphers: str | None = crawler.settings["DOWNLOADER_CLIENT_TLS_CIPHERS"]
        # DOWNLOADER_CLIENT_TLS_METHOD reading and handling should be also moved here
        # when the deprecated load_context_factory_from_settings() is removed
        tls_min_ver, tls_max_ver = _get_tls_version_limits(
            crawler.settings, _TWISTED_VERSION_MAP.__getitem__
        )
        if tls_min_ver or tls_max_ver:
            method = None
        verify_certificates = crawler.settings.getbool("DOWNLOAD_VERIFY_CERTIFICATES")
        return cls(  # type: ignore[misc]
            *args,
            method=method,
            tls_verbose_logging=tls_verbose_logging,
            tls_ciphers=tls_ciphers,
            tls_min_version=tls_min_ver,
            tls_max_version=tls_max_ver,
            verify_certificates=verify_certificates,
            **kwargs,
        )

    # should be removed together with ScrapyClientContextFactory
    def getCertificateOptions(self) -> CertificateOptions:  # pragma: no cover
        return self._get_cert_options()

    def _get_cert_options(self) -> CertificateOptions:
        return _ScrapyCertificateOptions(**self._get_cert_options_kwargs())

    def _get_cert_options_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "fixBrokenPeers": True,
            "acceptableCiphers": self.tls_ciphers,
        }
        if self.tls_min_version or self.tls_max_version:
            kwargs.update(
                _get_cert_options_version_kwargs(
                    self.tls_min_version, self.tls_max_version
                )
            )
        # when ScrapyClientContextFactory is removed self._ssl_method can just be None by default
        elif self._ssl_method != SSL.SSLv23_METHOD:
            kwargs["method"] = self._ssl_method
        return kwargs

    # should be removed together with ScrapyClientContextFactory
    def getContext(
        self, hostname: Any = None, port: Any = None
    ) -> SSL.Context:  # pragma: no cover
        return self._get_context()

    def _get_context(self) -> SSL.Context:
        return self._get_cert_options().getContext()

    def creatorForNetloc(self, hostname: bytes, port: int) -> ClientTLSOptions:
        if not self._verify_certificates:
            # Our options class is needed to skip verification errors
            if TWISTED_TLS_NEW_IMPL:
                return _ScrapyClientTLSOptions26(
                    self._get_cert_options()._makeTLSConnection,
                    hostname.decode("ascii"),
                )
            return _ScrapyClientTLSOptions(
                hostname.decode("ascii"),  # type: ignore[arg-type]
                self._get_context(),  # type: ignore[arg-type]
            )
        # Otherwise use the normal Twisted function.
        return optionsForClientTLS(  # type: ignore[no-any-return]
            hostname=hostname.decode("ascii"),
            extraCertificateOptions=self._get_cert_options_kwargs(),
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
        return optionsForClientTLS(  # type: ignore[no-any-return]
            hostname=hostname.decode("ascii"),
            extraCertificateOptions=self._get_cert_options_kwargs(),
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

    It's a no-op on Twisted 26.4.0+, though using it with custom
    factories on those Twisted versions may be not enough for HTTP/2 support.
    """

    # Something needs to call set_alpn_protos() for ALPN to work.
    #
    # Twisted < 26.4.0 does it in OpenSSLCertificateOptions._makeContext()
    # (requires passing acceptableProtocols from the factory to
    # OpenSSLCertificateOptions) and in TLSMemoryBIOFactory._createConnection()
    # based on H2ClientFactory.acceptableProtocols (too late, it seems).
    #
    # Newer Twisted does it in OpenSSLCertificateOptions._makeContext() as
    # well, and in OpenSSLCertificateOptions._makeTLSConnection() based on
    # H2ClientFactory.acceptableProtocols (which now works).
    #
    # When we drop DOWNLOADER_CLIENTCONTEXTFACTORY it looks like we can replace
    # all of this with _ScrapyClientContextFactory.acceptableProtocols.

    def __init__(self, context_factory: Any, acceptable_protocols: list[bytes]):
        verifyObject(IPolicyForHTTPS, context_factory)
        self._wrapped_context_factory: Any = context_factory
        self._acceptable_protocols: list[bytes] = acceptable_protocols

    def creatorForNetloc(self, hostname: bytes, port: int) -> ClientTLSOptions:
        options: ClientTLSOptions = self._wrapped_context_factory.creatorForNetloc(
            hostname, port
        )
        if not TWISTED_TLS_NEW_IMPL:
            from twisted.internet._sslverify import (  # type: ignore[attr-defined]  # noqa: PLC0415  # pylint: disable=no-name-in-module
                _setAcceptableProtocols,
            )

            _setAcceptableProtocols(options._ctx, self._acceptable_protocols)  # type: ignore[attr-defined]
        return options


AcceptableProtocolsContextFactory = create_deprecated_class(
    "AcceptableProtocolsContextFactory",
    _AcceptableProtocolsContextFactory,
    subclass_warn_message="{old} is deprecated.",
    instance_warn_message="{cls} is deprecated.",
)


class _ScrapyCertificateOptions(CertificateOptions):
    """A wrapper needed to add flags to the SSL context before it's used."""

    def _makeContext(self, skipCiphers: bool = False) -> SSL.Context:
        if TWISTED_TLS_NEW_IMPL:
            ctx = super()._makeContext(skipCiphers)
        else:
            ctx = super()._makeContext()
        ctx.set_options(0x4)  # OP_LEGACY_SERVER_CONNECT
        return ctx


def _load_context_factory_from_settings(crawler: Crawler) -> IPolicyForHTTPS:
    """Create an instance of :setting:`DOWNLOADER_CLIENTCONTEXTFACTORY`.

    Also passes values of other relevant settings to the factory class.
    """
    tls_method_setting: str = crawler.settings["DOWNLOADER_CLIENT_TLS_METHOD"]
    if tls_method_setting != "TLS":
        warnings.warn(
            "Setting DOWNLOADER_CLIENT_TLS_METHOD to a non-default value is"
            " deprecated, please use DOWNLOAD_TLS_MIN_VERSION and/or"
            " DOWNLOAD_TLS_MAX_VERSION instead.",
            ScrapyDeprecationWarning,
            stacklevel=2,
        )
    tls_method = _openssl_methods[tls_method_setting]
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
    return cast(
        "IPolicyForHTTPS",
        build_from_crawler(
            context_factory_cls,
            crawler,
            method=tls_method,
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
