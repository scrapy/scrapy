from __future__ import annotations

import logging
import warnings
from typing import TYPE_CHECKING, Any

from OpenSSL import SSL
from twisted.internet._sslverify import _setAcceptableProtocols
from twisted.internet.ssl import (
    AcceptableCiphers,
    CertificateOptions,
    TLSVersion,
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
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils.misc import build_from_crawler, load_object
from scrapy.utils.python import global_object_name

if TYPE_CHECKING:
    from twisted.internet._sslverify import ClientTLSOptions

    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.crawler import Crawler
    from scrapy.settings import BaseSettings


logger = logging.getLogger(__name__)


@implementer(IPolicyForHTTPS)
class ScrapyClientContextFactory(BrowserLikePolicyForHTTPS):
    """
    Non-peer-certificate verifying HTTPS context factory.

    TODO update the docstring

    Default OpenSSL method is TLS_METHOD (also called SSLv23_METHOD)
    which allows TLS protocol negotiation

    'A TLS/SSL connection established with [this method] may
     understand the TLSv1, TLSv1.1 and TLSv1.2 protocols.'
    """

    def __init__(
        self,
        method: int | None = SSL.SSLv23_METHOD,
        tls_verbose_logging: bool = False,
        tls_ciphers: str | None = None,
        *args: Any,
        tls_min_version: TLSVersion | None = None,
        tls_max_version: TLSVersion | None = None,
        **kwargs: Any,
    ):
        super().__init__(*args, **kwargs)
        if method not in {SSL.SSLv23_METHOD, None}:
            if tls_min_version or tls_max_version:
                logger.warning(
                    "Using both 'method' and 'tls_min_version'/'tls_max_version' arguments"
                    " to set the TLS version is unsupported, the 'method' argument will be ignored."
                )
            else:
                warnings.warn(
                    "Passing a non-default TLS method value to ScrapyClientContextFactory is deprecated,"
                    "the 'method' argument will be removed in a future Scrapy version. Please use"
                    " 'tls_min_version' and/or 'tls_max_version' arguments if you want"
                    " to change the supported TLS versions.",
                    ScrapyDeprecationWarning,
                    stacklevel=2,
                )
        if method is not None and (tls_min_version or tls_max_version):
            method = None
        self._ssl_method: int | None = method
        self.tls_min_version: TLSVersion | None = tls_min_version
        self.tls_max_version: TLSVersion | None = tls_max_version
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
        method: int | None = SSL.SSLv23_METHOD,
        *args: Any,
        **kwargs: Any,
    ) -> Self:
        warnings.warn(
            f"{cls.__name__}.from_settings() is deprecated, use from_crawler() instead.",
            category=ScrapyDeprecationWarning,
            stacklevel=2,
        )
        return cls._from_settings(settings, method, *args, **kwargs)

    @classmethod
    def from_crawler(
        cls,
        crawler: Crawler,
        method: int | None = SSL.SSLv23_METHOD,
        *args: Any,
        **kwargs: Any,
    ) -> Self:
        return cls._from_settings(crawler.settings, method, *args, **kwargs)

    @classmethod
    def _from_settings(
        cls,
        settings: BaseSettings,
        method: int | None = SSL.SSLv23_METHOD,
        *args: Any,
        **kwargs: Any,
    ) -> Self:
        tls_verbose_logging: bool = settings.getbool(
            "DOWNLOADER_CLIENT_TLS_VERBOSE_LOGGING"
        )
        tls_ciphers: str | None = settings["DOWNLOADER_CLIENT_TLS_CIPHERS"]

        tls_min_ver: TLSVersion | None = None
        tls_max_ver: TLSVersion | None = None
        tls_min_ver_setting: str | None = settings.get(
            "DOWNLOADER_CLIENT_TLS_MIN_VERSION"
        )
        if tls_min_ver_setting:
            try:
                tls_min_ver = TLSVersion.lookupByName(tls_min_ver_setting)
            except ValueError:
                logger.error(
                    f"Unknown DOWNLOADER_CLIENT_TLS_MIN_VERSION value: {tls_min_ver_setting}"
                )
        tls_max_ver_setting: str | None = settings.get(
            "DOWNLOADER_CLIENT_TLS_MAX_VERSION"
        )
        if tls_max_ver_setting:
            try:
                tls_max_ver = TLSVersion.lookupByName(tls_max_ver_setting)
            except ValueError:
                logger.error(
                    f"Unknown DOWNLOADER_CLIENT_TLS_MAX_VERSION value: {tls_max_ver_setting}"
                )

        return cls(  # type: ignore[misc]
            method=method,
            tls_verbose_logging=tls_verbose_logging,
            tls_ciphers=tls_ciphers,
            tls_min_version=tls_min_ver,
            tls_max_version=tls_max_ver,
            *args,
            **kwargs,
        )

    def getCertificateOptions(self) -> CertificateOptions:
        # setting verify=True will require you to provide CAs
        # to verify against; in other words: it's not that simple

        # TODO update the following comment
        # backward-compatible SSL/TLS method:
        #
        # * this will respect `method` attribute in often recommended
        #   `ScrapyClientContextFactory` subclass
        #   (https://github.com/scrapy/scrapy/issues/1429#issuecomment-131782133)
        #
        # * getattr() for `_ssl_method` attribute for context factories
        #   not calling super().__init__
        if not hasattr(self, "tls_min_version") and not getattr(
            self, "_bad_init_warned", False
        ):
            warnings.warn(
                f"{global_object_name(self.__class__)} was initialized"
                f" without calling ScrapyClientContextFactory.__init__(), this is deprecated.",
                category=ScrapyDeprecationWarning,
            )
            self._bad_init_warned = True
            method = getattr(self, "method", getattr(self, "_ssl_method", None))
            tls_min_version = None
            tls_max_version = None
        else:
            method = self._ssl_method
            tls_min_version = self.tls_min_version
            tls_max_version = self.tls_max_version

        kwargs: dict[str, Any] = {}
        if tls_min_version or tls_max_version:
            if tls_max_version:
                kwargs["lowerMaximumSecurityTo"] = tls_max_version
            if tls_min_version:
                # we cannot pass both insecurelyLowerMinimumTo and raiseMinimumTo,
                # so we need to know the direction
                default_min = CertificateOptions._defaultMinimumTLSVersion
                if tls_min_version < default_min:
                    kwargs["insecurelyLowerMinimumTo"] = tls_min_version
                elif tls_min_version > default_min:
                    kwargs["raiseMinimumTo"] = tls_min_version
        else:
            kwargs["method"] = method

        return CertificateOptions(
            verify=False,
            fixBrokenPeers=True,
            acceptableCiphers=self.tls_ciphers,
            **kwargs,
        )

    # kept for old-style HTTP/1.0 downloader context twisted calls,
    # e.g. connectSSL()
    def getContext(self, hostname: Any = None, port: Any = None) -> SSL.Context:
        ctx: SSL.Context = self.getCertificateOptions().getContext()
        ctx.set_options(0x4)  # OP_LEGACY_SERVER_CONNECT
        return ctx

    def creatorForNetloc(self, hostname: bytes, port: int) -> ClientTLSOptions:
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

    def creatorForNetloc(self, hostname: bytes, port: int) -> ClientTLSOptions:
        # trustRoot set to platformTrust() will use the platform's root CAs.
        #
        # This means that a website like https://www.cacert.org will be rejected
        # by default, since CAcert.org CA certificate is seldom shipped.
        return optionsForClientTLS(
            hostname=hostname.decode("ascii"),
            trustRoot=platformTrust(),
            extraCertificateOptions={"method": self._ssl_method},  # TODO
        )


@implementer(IPolicyForHTTPS)
class AcceptableProtocolsContextFactory:
    """Context factory to used to override the acceptable protocols
    to set up the [OpenSSL.SSL.Context] for doing NPN and/or ALPN
    negotiation.
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


def load_context_factory_from_settings(
    settings: BaseSettings, crawler: Crawler
) -> IPolicyForHTTPS:
    # TODO: this function should be deprecated in favor of simple build_from_crawler()
    # when the method handling is removed
    ssl_method_setting = settings.get("DOWNLOADER_CLIENT_TLS_METHOD")
    if ssl_method_setting not in {"TLS", None}:
        warnings.warn(
            "Setting DOWNLOADER_CLIENT_TLS_METHOD to a non-default value is"
            " deprecated, please use DOWNLOADER_CLIENT_TLS_MIN_VERSION and/or"
            " DOWNLOADER_CLIENT_TLS_MAX_VERSION instead.",
            ScrapyDeprecationWarning,
        )
    ssl_method = openssl_methods[ssl_method_setting]
    context_factory_cls = load_object(settings["DOWNLOADER_CLIENTCONTEXTFACTORY"])
    # try method-aware context factory
    try:
        context_factory = build_from_crawler(
            context_factory_cls,
            crawler,
            method=ssl_method,
        )
    except TypeError:
        # use context factory defaults
        context_factory = build_from_crawler(
            context_factory_cls,
            crawler,
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
