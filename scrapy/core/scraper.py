"""This module implements the Scraper component which parses responses and
extracts information from them"""

from __future__ import annotations

import logging
import warnings
from collections import deque
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any, TypeAlias, TypeVar

from twisted.internet.defer import Deferred, inlineCallbacks
from twisted.python.failure import Failure

from scrapy import Spider, signals
from scrapy.core.spidermw import SpiderMiddlewareManager
from scrapy.exceptions import (
    CloseSpider,
    DropItem,
    IgnoreRequest,
    ScrapyDeprecationWarning,
)
from scrapy.http import Request, Response
from scrapy.pipelines import ItemPipelineManager
from scrapy.utils.asyncio import _parallel_asyncio, is_asyncio_available
from scrapy.utils.decorators import _warn_spider_arg
from scrapy.utils.defer import (
    _defer_sleep_async,
    _schedule_coro,
    aiter_errback,
    deferred_from_coro,
    ensure_awaitable,
    iter_errback,
    maybe_deferred_to_future,
    parallel,
    parallel_async,
)
from scrapy.utils.deprecate import method_is_overridden
from scrapy.utils.log import failure_to_exc_info, logformatter_adapter
from scrapy.utils.misc import load_object, warn_on_generator_with_return_value
from scrapy.utils.python import global_object_name
from scrapy.utils.spider import iterate_spider_output

if TYPE_CHECKING:
    from collections.abc import Generator, Iterable

    from scrapy.crawler import Crawler
    from scrapy.logformatter import LogFormatter
    from scrapy.signalmanager import SignalManager


logger = logging.getLogger(__name__)


_T = TypeVar("_T")
QueueTuple: TypeAlias = tuple[Response | Failure, Request, Deferred[None]]


class Slot:
    """Scraper slot (one per running spider)"""

    MIN_RESPONSE_SIZE = 1024

    def __init__(self, max_active_size: int = 5000000):
        self.max_active_size: int = max_active_size
        self.queue: deque[QueueTuple] = deque()
        self.active: set[Request] = set()
        self.active_size: int = 0
        self.itemproc_size: int = 0
        self.closing: Deferred[Spider] | None = None

    def add_response_request(
        self, result: Response | Failure, request: Request
    ) -> Deferred[None]:
        # this Deferred will be awaited in enqueue_scrape()
        deferred: Deferred[None] = Deferred()
        self.queue.append((result, request, deferred))
        if isinstance(result, Response):
            self.active_size += max(len(result.body), self.MIN_RESPONSE_SIZE)
        else:
            self.active_size += self.MIN_RESPONSE_SIZE
        return deferred

    def next_response_request_deferred(self) -> QueueTuple:
        result, request, deferred = self.queue.popleft()
        self.active.add(request)
        return result, request, deferred

    def finish_response(self, result: Response | Failure, request: Request) -> None:
        self.active.remove(request)
        if isinstance(result, Response):
            self.active_size -= max(len(result.body), self.MIN_RESPONSE_SIZE)
        else:
            self.active_size -= self.MIN_RESPONSE_SIZE

    def is_idle(self) -> bool:
        return not (self.queue or self.active)

    def needs_backout(self) -> bool:
        return self.active_size > self.max_active_size


class Scraper:
    def __init__(self, crawler: Crawler) -> None:
        self.slot: Slot | None = None
        self.spidermw: SpiderMiddlewareManager = SpiderMiddlewareManager.from_crawler(
            crawler
        )
        itemproc_cls: type[ItemPipelineManager] = load_object(
            crawler.settings["ITEM_PROCESSOR"]
        )
        self.itemproc: ItemPipelineManager = itemproc_cls.from_crawler(crawler)
        self._itemproc_has_async: dict[str, bool] = {}
        for method in [
            "open_spider",
            "close_spider",
            "process_item",
        ]:
            self._check_deprecated_itemproc_method(method)

        self.concurrent_items: int = crawler.settings.getint("CONCURRENT_ITEMS")
        self.crawler: Crawler = crawler
        self.signals: SignalManager = crawler.signals
        assert crawler.logformatter
        self.logformatter: LogFormatter = crawler.logformatter

    def _check_deprecated_itemproc_method(self, method: str) -> None:
        itemproc_cls = type(self.itemproc)
        if not hasattr(self.itemproc, "process_item_async"):
            warnings.warn(
                f"{global_object_name(itemproc_cls)} doesn't define a {method}_async() method,"
                f" this is deprecated and the method will be required in future Scrapy versions.",
                ScrapyDeprecationWarning,
                stacklevel=2,
            )
            self._itemproc_has_async[method] = False
        elif (
            issubclass(itemproc_cls, ItemPipelineManager)
            and method_is_overridden(itemproc_cls, ItemPipelineManager, method)
            and not method_is_overridden(
                itemproc_cls, ItemPipelineManager, f"{method}_async"
            )
        ):
            warnings.warn(
                f"{global_object_name(itemproc_cls)} overrides {method}() but doesn't override {method}_async()."
                f" This is deprecated. {method}() will be used, but in future Scrapy versions {method}_async() will be used instead.",
                ScrapyDeprecationWarning,
                stacklevel=2,
            )
            self._itemproc_has_async[method] = False
        else:
            self._itemproc_has_async[method] = True

    def open_spider(self, spider: Spider | None = None) -> Deferred[None]:
        warnings.warn(
            "Scraper.open_spider() is deprecated, use open_spider_async() instead",
            ScrapyDeprecationWarning,
            stacklevel=2,
        )
        return deferred_from_coro(self.open_spider_async())

    async def open_spider_async(self) -> None:
        """Open the spider for scraping and allocate resources for it.

        .. versionadded:: 2.14
        """
        self.slot = Slot(self.crawler.settings.getint("SCRAPER_SLOT_MAX_ACTIVE_SIZE"))
        if not self.crawler.spider:
            raise RuntimeError(
                "Scraper.open_spider() called before Crawler.spider is set."
            )
        if self._itemproc_has_async["open_spider"]:
            await self.itemproc.open_spider_async()
        else:
            await maybe_deferred_to_future(
                self.itemproc.open_spider(self.crawler.spider)
            )

    def close_spider(self, spider: Spider | None = None) -> Deferred[None]:
        warnings.warn(
            "Scraper.close_spider() is deprecated, use close_spider_async() instead",
            ScrapyDeprecationWarning,
            stacklevel=2,
        )
        return deferred_from_coro(self.close_spider_async())

    async def close_spider_async(self) -> None:
        """Close the spider being scraped and release its resources.

        .. versionadded:: 2.14
        """
        if self.slot is None:
            raise RuntimeError("Scraper slot not assigned")
        self.slot.closing = Deferred()
        self._check_if_closing()
        await maybe_deferred_to_future(self.slot.closing)
        if self._itemproc_has_async["close_spider"]:
            await self.itemproc.close_spider_async()
        else:
            assert self.crawler.spider
            await maybe_deferred_to_future(
                self.itemproc.close_spider(self.crawler.spider)
            )

    def is_idle(self) -> bool:
        """Return True if there isn't any more spiders to process"""
        return not self.slot

    def _check_if_closing(self) -> None:
        assert self.slot is not None  # typing
        if self.slot.closing and self.slot.is_idle():
            assert self.crawler.spider
            self.slot.closing.callback(self.crawler.spider)

    @inlineCallbacks
    @_warn_spider_arg
    def enqueue_scrape(
        self, result: Response | Failure, request: Request, spider: Spider | None = None
    ) -> Generator[Deferred[Any], Any, None]:
        if self.slot is None:
            raise RuntimeError("Scraper slot not assigned")
        dfd = self.slot.add_response_request(result, request)
        self._scrape_next()
        try:
            yield dfd  # fired in _wait_for_processing()
        except Exception:
            logger.error(
                "Scraper bug processing %(request)s",
                {"request": request},
                exc_info=True,
                extra={"spider": self.crawler.spider},
            )
        finally:
            self.slot.finish_response(result, request)
            self._check_if_closing()
            self._scrape_next()

    def _scrape_next(self) -> None:
        assert self.slot is not None  # typing
        while self.slot.queue:
            result, request, queue_dfd = self.slot.next_response_request_deferred()
            _schedule_coro(self._wait_for_processing(result, request, queue_dfd))

    async def _scrape(self, result: Response | Failure, request: Request) -> None:
        """Handle the downloaded response or failure through the spider callback/errback."""
        if not isinstance(result, (Response, Failure)):
            raise TypeError(
                f"Incorrect type: expected Response or Failure, got {type(result)}: {result!r}"
            )

        output: Iterable[Any] | AsyncIterator[Any]
        if isinstance(result, Response):
            try:
                # call the spider middlewares and the request callback with the response
                output = await self.spidermw.scrape_response_async(
                    self.call_spider_async, result, request
                )
            except Exception:
                self.handle_spider_error(Failure(), request, result)
            else:
                await self.handle_spider_output_async(output, request, result)
            return

        try:
            # call the request errback with the downloader error
            output = await self.call_spider_async(result, request)
        except Exception as spider_exc:
            # the errback didn't silence the exception
            assert self.crawler.spider
            if not result.check(IgnoreRequest):
                logkws = self.logformatter.download_error(
                    result, request, self.crawler.spider
                )
                logger.log(
                    *logformatter_adapter(logkws),
                    extra={"spider": self.crawler.spider},
                    exc_info=failure_to_exc_info(result),
                )
            if spider_exc is not result.value:
                # the errback raised a different exception, handle it
                self.handle_spider_error(Failure(), request, result)
        else:
            await self.handle_spider_output_async(output, request, result)

    async def _wait_for_processing(
        self, result: Response | Failure, request: Request, queue_dfd: Deferred[None]
    ) -> None:
        try:
            await self._scrape(result, request)
        except Exception:
            queue_dfd.errback(Failure())
        else:
            queue_dfd.callback(None)  # awaited in enqueue_scrape()

    def call_spider(
        self, result: Response | Failure, request: Request, spider: Spider | None = None
    ) -> Deferred[Iterable[Any] | AsyncIterator[Any]]:
        warnings.warn(
            "Scraper.call_spider() is deprecated, use call_spider_async() instead",
            ScrapyDeprecationWarning,
            stacklevel=2,
        )
        return deferred_from_coro(self.call_spider_async(result, request))

    async def call_spider_async(
        self, result: Response | Failure, request: Request
    ) -> Iterable[Any] | AsyncIterator[Any]:
        """Call the request callback or errback with the response or failure.

        .. versionadded:: 2.13
        """
        await _defer_sleep_async()
        assert self.crawler.spider
        if isinstance(result, Response):
            if getattr(result, "request", None) is None:
                result.request = request
            assert result.request
            callback = result.request.callback or self.crawler.spider._parse
            warn_on_generator_with_return_value(self.crawler.spider, callback)
            output = callback(result, **result.request.cb_kwargs)
            if isinstance(output, Deferred):
                warnings.warn(
                    f"{callback} returned a Deferred."
                    f" Returning Deferreds from spider callbacks is deprecated.",
                    ScrapyDeprecationWarning,
                    stacklevel=2,
                )
        else:  # result is a Failure
            # TODO: properly type adding this attribute to a Failure
            result.request = request  # type: ignore[attr-defined]
            if not request.errback:
                result.raiseException()
            warn_on_generator_with_return_value(self.crawler.spider, request.errback)
            output = request.errback(result)
            if isinstance(output, Failure):
                output.raiseException()
            # else the errback returned actual output (like a callback),
            # which needs to be passed to iterate_spider_output()
            if isinstance(output, Deferred):
                warnings.warn(
                    f"{request.errback} returned a Deferred."
                    f" Returning Deferreds from spider errbacks is deprecated.",
                    ScrapyDeprecationWarning,
                    stacklevel=2,
                )
        return await ensure_awaitable(iterate_spider_output(output))

    @_warn_spider_arg
    def handle_spider_error(
        self,
        _failure: Failure,
        request: Request,
        response: Response | Failure,
        spider: Spider | None = None,
    ) -> None:
        """Handle an exception raised by a spider callback or errback."""
        assert self.crawler.spider
        exc = _failure.value
        if isinstance(exc, CloseSpider):
            assert self.crawler.engine is not None  # typing
            _schedule_coro(
                self.crawler.engine.close_spider_async(reason=exc.reason or "cancelled")
            )
            return
        logkws = self.logformatter.spider_error(
            _failure, request, response, self.crawler.spider
        )
        logger.log(
            *logformatter_adapter(logkws),
            exc_info=failure_to_exc_info(_failure),
            extra={"spider": self.crawler.spider},
        )
        self.signals.send_catch_log(
            signal=signals.spider_error,
            failure=_failure,
            response=response,
            spider=self.crawler.spider,
        )
        assert self.crawler.stats
        self.crawler.stats.inc_value("spider_exceptions/count")
        self.crawler.stats.inc_value(
            f"spider_exceptions/{_failure.value.__class__.__name__}"
        )

    def handle_spider_output(
        self,
        result: Iterable[_T] | AsyncIterator[_T],
        request: Request,
        response: Response | Failure,
        spider: Spider | None = None,
    ) -> Deferred[None]:
        """Pass items/requests produced by a callback to ``_process_spidermw_output()`` in parallel."""
        warnings.warn(
            "Scraper.handle_spider_output() is deprecated, use handle_spider_output_async() instead",
            ScrapyDeprecationWarning,
            stacklevel=2,
        )
        return deferred_from_coro(
            self.handle_spider_output_async(result, request, response)
        )

    async def handle_spider_output_async(
        self,
        result: Iterable[_T] | AsyncIterator[_T],
        request: Request,
        response: Response | Failure,
    ) -> None:
        """Pass items/requests produced by a callback to ``_process_spidermw_output()`` in parallel.

        .. versionadded:: 2.13
        """
        it: Iterable[_T] | AsyncIterator[_T]
        if is_asyncio_available():
            if isinstance(result, AsyncIterator):
                it = aiter_errback(result, self.handle_spider_error, request, response)
            else:
                it = iter_errback(result, self.handle_spider_error, request, response)
            await _parallel_asyncio(
                it, self.concurrent_items, self._process_spidermw_output_async, response
            )
            return
        if isinstance(result, AsyncIterator):
            it = aiter_errback(result, self.handle_spider_error, request, response)
            await maybe_deferred_to_future(
                parallel_async(
                    it,
                    self.concurrent_items,
                    self._process_spidermw_output,
                    response,
                )
            )
            return
        it = iter_errback(result, self.handle_spider_error, request, response)
        await maybe_deferred_to_future(
            parallel(
                it,
                self.concurrent_items,
                self._process_spidermw_output,
                response,
            )
        )

    def _process_spidermw_output(
        self, output: Any, response: Response | Failure
    ) -> Deferred[None]:
        """Process each Request/Item (given in the output parameter) returned
        from the given spider.

        Items are sent to the item pipelines, requests are scheduled.
        """
        return deferred_from_coro(self._process_spidermw_output_async(output, response))

    async def _process_spidermw_output_async(
        self, output: Any, response: Response | Failure
    ) -> None:
        """Process each Request/Item (given in the output parameter) returned
        from the given spider.

        Items are sent to the item pipelines, requests are scheduled.
        """
        if isinstance(output, Request):
            assert self.crawler.engine is not None  # typing
            self.crawler.engine.crawl(request=output)
            return
        if output is not None:
            await self.start_itemproc_async(output, response=response)

    def start_itemproc(
        self, item: Any, *, response: Response | Failure | None
    ) -> Deferred[None]:
        """Send *item* to the item pipelines for processing.

        *response* is the source of the item data. If the item does not come
        from response data, e.g. it was hard-coded, set it to ``None``.
        """
        warnings.warn(
            "Scraper.start_itemproc() is deprecated, use start_itemproc_async() instead",
            ScrapyDeprecationWarning,
            stacklevel=2,
        )
        return deferred_from_coro(self.start_itemproc_async(item, response=response))

    async def start_itemproc_async(
        self, item: Any, *, response: Response | Failure | None
    ) -> None:
        """Send *item* to the item pipelines for processing.

        *response* is the source of the item data. If the item does not come
        from response data, e.g. it was hard-coded, set it to ``None``.

        .. versionadded:: 2.14
        """
        assert self.slot is not None  # typing
        assert self.crawler.spider is not None  # typing
        self.slot.itemproc_size += 1
        try:
            if self._itemproc_has_async["process_item"]:
                output = await self.itemproc.process_item_async(item)
            else:
                output = await maybe_deferred_to_future(
                    self.itemproc.process_item(item, self.crawler.spider)
                )
        except DropItem as ex:
            logkws = self.logformatter.dropped(item, ex, response, self.crawler.spider)
            if logkws is not None:
                logger.log(
                    *logformatter_adapter(logkws), extra={"spider": self.crawler.spider}
                )
            await self.signals.send_catch_log_async(
                signal=signals.item_dropped,
                item=item,
                response=response,
                spider=self.crawler.spider,
                exception=ex,
            )
        except Exception as ex:
            logkws = self.logformatter.item_error(
                item, ex, response, self.crawler.spider
            )
            logger.log(
                *logformatter_adapter(logkws),
                extra={"spider": self.crawler.spider},
                exc_info=True,
            )
            await self.signals.send_catch_log_async(
                signal=signals.item_error,
                item=item,
                response=response,
                spider=self.crawler.spider,
                failure=Failure(),
            )
        else:
            logkws = self.logformatter.scraped(output, response, self.crawler.spider)
            if logkws is not None:
                logger.log(
                    *logformatter_adapter(logkws), extra={"spider": self.crawler.spider}
                )
            await self.signals.send_catch_log_async(
                signal=signals.item_scraped,
                item=output,
                response=response,
                spider=self.crawler.spider,
            )
        finally:
            self.slot.itemproc_size -= 1
