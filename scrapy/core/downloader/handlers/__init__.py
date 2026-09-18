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
    """Interface that :ref:`download handlers <topics-download-handlers>` must
    implement.

    Besides implementing this protocol, the contract of a download handler
    includes **never** calling :meth:`crawler.engine.download_async()
    <scrapy.core.engine.ExecutionEngine.download_async>`.
    """

    lazy: bool
    """Whether to delay instantiation of the handler; see :ref:`lazy
    <lazy-download-handlers>`."""

    async def download_request(self, request: Request) -> Response:
        """Download *request* and return a response."""

    async def close(self) -> None:
        """Clean up any resources used by the handler."""


class DownloadHandlers:
    def __init__(self, crawler: Crawler):
        self._crawler: Crawler = crawler
        # stores class paths by handler ID
        self._paths: dict[str, str | Callable[..., Any]] = {}
        # handler IDs that are also acceptable URL schemes
        self._schemes: set[str] = set()
        # stores instanced handlers by handler ID
        self._handlers: dict[str, DownloadHandlerProtocol] = {}
        # remembers failed handlers
        self._notconfigured: dict[str, str] = {}
        # remembers handlers with Deferred-based download_request()
        self._old_style_handlers: set[str] = set()
        scheme_handlers: dict[str, str | Callable[..., Any]] = without_none_values(
            cast(
                "dict[str, str | Callable[..., Any]]",
                crawler.settings.getwithbase("DOWNLOAD_HANDLERS"),
            )
        )
        named_handlers: dict[str, str | Callable[..., Any]] = without_none_values(
            cast(
                "dict[str, str | Callable[..., Any]]",
                crawler.settings.getdict("DOWNLOAD_HANDLERS_BY_NAME"),
            )
        )
        if clashes := scheme_handlers.keys() & named_handlers.keys():
            raise ValueError(
                f"The following download handler IDs are defined both in "
                f"DOWNLOAD_HANDLERS and in DOWNLOAD_HANDLERS_BY_NAME: "
                f"{', '.join(sorted(clashes))}."
            )
        self._schemes.update(scheme_handlers)
        for handler_id, clspath in (scheme_handlers | named_handlers).items():
            self._paths[handler_id] = clspath
            self._load_handler(handler_id, skip_lazy=True)

        crawler.signals.connect(self._close, signals.engine_stopped)

    def _get_handler(self, handler_id: str) -> DownloadHandlerProtocol | None:
        """Lazy-load the download handler with the given ID only on its first
        request.
        """
        if handler_id in self._handlers:
            return self._handlers[handler_id]
        if handler_id in self._notconfigured:
            return None
        if handler_id not in self._paths:
            self._notconfigured[handler_id] = "no handler with that ID"
            return None

        return self._load_handler(handler_id)

    def _load_handler(
        self, handler_id: str, skip_lazy: bool = False
    ) -> DownloadHandlerProtocol | None:
        path = self._paths[handler_id]
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
            self._notconfigured[handler_id] = str(ex)
            return None
        except Exception as ex:
            logger.error(
                'Loading "%(clspath)s" for handler ID "%(handler_id)s"',
                {"clspath": path, "handler_id": handler_id},
                exc_info=True,
                extra={"crawler": self._crawler},
            )
            self._notconfigured[handler_id] = str(ex)
            return None
        self._handlers[handler_id] = dh
        if not inspect.iscoroutinefunction(dh.download_request):  # pragma: no cover
            warnings.warn(
                f"{global_object_name(dh.download_request)} is not a coroutine function."
                f" This is deprecated, please rewrite it to return a coroutine and remove"
                f" the 'spider' argument.",
                category=ScrapyDeprecationWarning,
                stacklevel=1,
            )
            self._old_style_handlers.add(handler_id)
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
        handler_id = request.meta.get("download_handler")
        if handler_id is None:
            scheme = urlparse_cached(request).scheme
            # Handler IDs from DOWNLOAD_HANDLERS_BY_NAME are only reachable
            # through the download_handler request metadata key, so that
            # registering one does not make a new URL scheme downloadable.
            if scheme in self._schemes:
                handler = self._get_handler(scheme)
            else:
                handler = None
                self._notconfigured.setdefault(
                    scheme, "no handler available for that scheme"
                )
            if not handler:
                raise NotSupported(
                    f"Unsupported URL scheme '{scheme}': {self._notconfigured[scheme]}"
                )
            handler_id = scheme
        else:
            handler = self._get_handler(handler_id)
            if not handler:
                raise NotSupported(
                    f"Unusable download handler {handler_id!r}: "
                    f"{self._notconfigured[handler_id]}"
                )
        assert self._crawler.spider
        if handler_id in self._old_style_handlers:  # pragma: no cover
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
