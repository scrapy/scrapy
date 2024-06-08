"""Download handlers for different schemes"""

from __future__ import annotations

import logging
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    Generator,
    Optional,
    Protocol,
    Type,
    Union,
    cast,
)

from twisted.internet import defer
from twisted.internet.defer import Deferred

from scrapy import Request, Spider, signals
from scrapy.exceptions import NotConfigured, NotSupported
from scrapy.http import Response
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.misc import build_from_crawler, load_object
from scrapy.utils.python import without_none_values

if TYPE_CHECKING:
    from scrapy.crawler import Crawler

logger = logging.getLogger(__name__)


class DownloadHandlerProtocol(Protocol):
    def download_request(
        self, request: Request, spider: Spider
    ) -> Deferred[Response]: ...


class DownloadHandlers:
    def __init__(self, crawler: Crawler):
        self._crawler: Crawler = crawler
        self._schemes: Dict[str, Union[str, Callable[..., Any]]] = (
            {}
        )  # stores acceptable schemes on instancing
        self._handlers: Dict[str, DownloadHandlerProtocol] = (
            {}
        )  # stores instanced handlers for schemes
        self._notconfigured: Dict[str, str] = {}  # remembers failed handlers
        handlers: Dict[str, Union[str, Callable[..., Any]]] = without_none_values(
            cast(
                Dict[str, Union[str, Callable[..., Any]]],
                crawler.settings.getwithbase("DOWNLOAD_HANDLERS"),
            )
        )
        for scheme, clspath in handlers.items():
            self._schemes[scheme] = clspath
            self._load_handler(scheme, skip_lazy=True)

        crawler.signals.connect(self._close, signals.engine_stopped)

    def _get_handler(self, scheme: str) -> Optional[DownloadHandlerProtocol]:
        """Lazy-load the downloadhandler for a scheme
        only on the first request for that scheme.
        """
        if scheme in self._handlers:
            return self._handlers[scheme]
        if scheme in self._notconfigured:
            return None
        if scheme not in self._schemes:
            self._notconfigured[scheme] = "no handler available for that scheme"
            return None

        return self._load_handler(scheme)

    def _load_handler(
        self, scheme: str, skip_lazy: bool = False
    ) -> Optional[DownloadHandlerProtocol]:
        path = self._schemes[scheme]
        try:
            dhcls: Type[DownloadHandlerProtocol] = load_object(path)
            if skip_lazy and getattr(dhcls, "lazy", True):
                return None
            dh = build_from_crawler(
                dhcls,
                self._crawler,
            )
        except NotConfigured as ex:
            self._notconfigured[scheme] = str(ex)
            return None
        except Exception as ex:
            logger.error(
                'Loading "%(clspath)s" for scheme "%(scheme)s"',
                {"clspath": path, "scheme": scheme},
                exc_info=True,
                extra={"crawler": self._crawler},
            )
            self._notconfigured[scheme] = str(ex)
            return None
        else:
            self._handlers[scheme] = dh
            return dh

    def download_request(self, request: Request, spider: Spider) -> Deferred[Response]:
        scheme = urlparse_cached(request).scheme
        handler = self._get_handler(scheme)
        if not handler:
            raise NotSupported(
                f"Unsupported URL scheme '{scheme}': {self._notconfigured[scheme]}"
            )
        return handler.download_request(request, spider)

    @defer.inlineCallbacks
    def _close(self, *_a: Any, **_kw: Any) -> Generator[Deferred[Any], Any, None]:
        for dh in self._handlers.values():
            if hasattr(dh, "close"):
                yield dh.close()
