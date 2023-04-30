"""Download handlers for different schemes"""

import logging
from typing import TYPE_CHECKING, Any, Callable, Dict, Generator, Union, cast

from twisted.internet import defer
from twisted.internet.defer import Deferred

from scrapy import Request, Spider, signals
from scrapy.exceptions import NotConfigured, NotSupported
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.misc import create_instance, load_object
from scrapy.utils.python import without_none_values

if TYPE_CHECKING:
    from scrapy.crawler import Crawler

logger = logging.getLogger(__name__)


class DownloadHandlers:
    def __init__(self, crawler: "Crawler"):
        self._crawler: "Crawler" = crawler
        self._schemes: Dict[
            str, Union[str, Callable]
        ] = {}  # stores acceptable schemes on instancing
        self._handlers: Dict[str, Any] = {}  # stores instanced handlers for schemes
        self._notconfigured: Dict[str, str] = {}  # remembers failed handlers
        handlers: Dict[str, Union[str, Callable]] = without_none_values(
            crawler.settings.getwithbase("DOWNLOAD_HANDLERS")
        )
        for scheme, clspath in handlers.items():
            self._schemes[scheme] = clspath
            self._load_handler(scheme, skip_lazy=True)

        crawler.signals.connect(self._close, signals.engine_stopped)

    def _get_handler(self, scheme: str) -> Any:
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

    def _load_handler(self, scheme: str, skip_lazy: bool = False) -> Any:
        path = self._schemes[scheme]
        try:
            dhcls = load_object(path)
            if skip_lazy and getattr(dhcls, "lazy", True):
                return None
            dh = create_instance(
                objcls=dhcls,
                settings=self._crawler.settings,
                crawler=self._crawler,
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

    def download_request(self, request: Request, spider: Spider) -> Deferred:
        scheme = urlparse_cached(request).scheme
        handler = self._get_handler(scheme)
        if not handler:
            raise NotSupported(
                f"Unsupported URL scheme '{scheme}': {self._notconfigured[scheme]}"
            )
        return cast(Deferred, handler.download_request(request, spider))

    @defer.inlineCallbacks
    def _close(self, *_a: Any, **_kw: Any) -> Generator[Deferred, Any, None]:
        for dh in self._handlers.values():
            if hasattr(dh, "close"):
                yield dh.close()
