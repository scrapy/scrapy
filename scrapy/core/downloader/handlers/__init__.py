"""Download handlers for different schemes"""

from __future__ import annotations

import inspect
import logging
import warnings
from typing import TYPE_CHECKING, Any, Protocol, cast

from scrapy import Request, Spider, signals
from scrapy.exceptions import NotConfigured, NotSupported, ScrapyDeprecationWarning
from scrapy.utils.defer import (
    deferred_from_coro,
    ensure_awaitable,
    maybe_deferred_to_future,
)
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.misc import build_from_crawler, load_object
from scrapy.utils.python import global_object_name, without_none_values

if TYPE_CHECKING:
    from collections.abc import Callable

    from twisted.internet.defer import Deferred

    from scrapy.crawler import Crawler
    from scrapy.http import Response


logger = logging.getLogger(__name__)


# This is the official API but we temporarily support the old deprecated one:
# * lazy is not mandatory (defaults to True).
# * download_request() can return a Deferred[Response] instead of a coroutine,
# and takes a spider argument in this case.
# * close() can return None or Deferred[None] instead of a coroutine.
# * close() is not mandatory.


class DownloadHandlerProtocol(Protocol):
    lazy: bool

    async def download_request(self, request: Request) -> Response: ...

    async def close(self) -> None: ...


class DownloadHandlers:
    def __init__(self, crawler: Crawler):
        self._crawler: Crawler = crawler
        # stores acceptable schemes on instancing
        self._schemes: dict[str, str | Callable[..., Any]] = {}
        # stores instanced handlers for schemes
        self._handlers: dict[str, DownloadHandlerProtocol] = {}
        # remembers failed handlers
        self._notconfigured: dict[str, str] = {}
        # remembers handlers with Deferred-based download_request()
        self._old_style_handlers: set[str] = set()
        handlers: dict[str, str | Callable[..., Any]] = without_none_values(
            cast(
                "dict[str, str | Callable[..., Any]]",
                crawler.settings.getwithbase("DOWNLOAD_HANDLERS"),
            )
        )
        for scheme, clspath in handlers.items():
            self._schemes[scheme] = clspath
            self._load_handler(scheme, skip_lazy=True)

        crawler.signals.connect(self._close, signals.engine_stopped)

    def _get_handler(self, scheme: str) -> DownloadHandlerProtocol | None:
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
    ) -> DownloadHandlerProtocol | None:
        path = self._schemes[scheme]
        try:
            dhcls: type[DownloadHandlerProtocol] = load_object(path)
            if skip_lazy:
                if not hasattr(dhcls, "lazy"):
                    warnings.warn(
                        f"{global_object_name(dhcls)} doesn't define a 'lazy' attribute."
                        f" This is deprecated, please add 'lazy = True' (which is the current"
                        f" default value) to the class definition.",
                        category=ScrapyDeprecationWarning,
                        stacklevel=1,
                    )
                if getattr(dhcls, "lazy", True):
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
        self._handlers[scheme] = dh
        if not inspect.iscoroutinefunction(dh.download_request):  # pragma: no cover
            warnings.warn(
                f"{global_object_name(dh.download_request)} is not a coroutine function."
                f" This is deprecated, please rewrite it to return a coroutine and remove"
                f" the 'spider' argument.",
                category=ScrapyDeprecationWarning,
                stacklevel=1,
            )
            self._old_style_handlers.add(scheme)
        return dh

    def download_request(
        self, request: Request, spider: Spider | None = None
    ) -> Deferred[Response]:  # pragma: no cover
        warnings.warn(
            "DownloadHandlers.download_request() is deprecated, use download_request_async() instead",
            category=ScrapyDeprecationWarning,
            stacklevel=2,
        )
        return deferred_from_coro(self.download_request_async(request))

    async def download_request_async(self, request: Request) -> Response:
        scheme = urlparse_cached(request).scheme
        handler = self._get_handler(scheme)
        if not handler:
            raise NotSupported(
                f"Unsupported URL scheme '{scheme}': {self._notconfigured[scheme]}"
            )
        assert self._crawler.spider
        if scheme in self._old_style_handlers:  # pragma: no cover
            return await maybe_deferred_to_future(
                cast(
                    "Deferred[Response]",
                    handler.download_request(request, self._crawler.spider),  # type: ignore[call-arg]
                )
            )
        return await handler.download_request(request)

    async def _close(self) -> None:
        for dh in self._handlers.values():
            if not hasattr(dh, "close"):  # pragma: no cover
                warnings.warn(
                    f"{global_object_name(dh)} doesn't define a close() method."
                    f" This is deprecated, please add an empty 'async def close()' method.",
                    category=ScrapyDeprecationWarning,
                    stacklevel=1,
                )
                continue

            if inspect.iscoroutinefunction(dh.close):
                await dh.close()
            else:  # pragma: no cover
                warnings.warn(
                    f"{global_object_name(dh.close)} is not a coroutine function."
                    f" This is deprecated, please rewrite it to return a coroutine.",
                    category=ScrapyDeprecationWarning,
                    stacklevel=1,
                )
                await ensure_awaitable(dh.close())
