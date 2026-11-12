import asyncio
import gc
import logging
import warnings
from pathlib import Path
from typing import Any

import pytest
from twisted.internet.defer import Deferred
from twisted.python.failure import Failure

from scrapy import Request, Spider, signals
from scrapy.core.downloader import Downloader
from scrapy.core.downloader.handlers.datauri import DataURIDownloadHandler
from scrapy.core.engine import ExecutionEngine
from scrapy.crawler import Crawler
from scrapy.exceptions import IgnoreRequest, ScrapyDeprecationWarning
from scrapy.http import BodyFileResponse, HtmlResponse, Response
from scrapy.http.request import NO_CALLBACK
from scrapy.pipelines.files import FilesPipeline
from scrapy.utils.asyncio import call_later, sleep
from scrapy.utils.defer import deferred_from_coro, maybe_deferred_to_future
from scrapy.utils.test import get_crawler
from tests.utils.decorators import coroutine_test


def _count_backout_logs(caplog: pytest.LogCaptureFixture) -> int:
    return sum(
        1
        for record in caplog.records
        if record.levelname == "INFO"
        and str(record.msg).startswith("Pausing request processing")
    )


def _backout_stats(crawler: Crawler) -> dict[str, Any]:
    assert crawler.stats
    return {
        k: v
        for k, v in crawler.stats.get_stats().items()
        if k.startswith("request_backout_seconds/")
    }


class OfflineSpider(Spider):
    name = "offline"
    start_urls = ["data:,"]

    def parse(self, response):
        pass


def _assert_scraper_slot_deprecation(
    warning_messages: pytest.WarningsRecorder, *, ignored: bool = False
) -> None:
    """Assert that a crawl emitted exactly one Scrapy deprecation warning, the
    one about SCRAPER_SLOT_MAX_ACTIVE_SIZE.

    Only Scrapy deprecation warnings are counted: a crawl may emit unrelated
    warnings (e.g. a ResourceWarning for a socket garbage-collected while the
    recorder is active), and those must not make the assertion flaky.

    Pass ``ignored=True`` when RESPONSE_MAX_ACTIVE_SIZE is set with an equal or
    higher priority and therefore SCRAPER_SLOT_MAX_ACTIVE_SIZE is being
    ignored."""
    deprecations = [
        message
        for message in warning_messages
        if issubclass(message.category, ScrapyDeprecationWarning)
    ]
    assert len(deprecations) == 1
    if ignored:
        assert str(deprecations[0].message) == (
            "The SCRAPER_SLOT_MAX_ACTIVE_SIZE setting is deprecated and is "
            "being ignored because RESPONSE_MAX_ACTIVE_SIZE is set with an "
            "equal or higher priority. Remove SCRAPER_SLOT_MAX_ACTIVE_SIZE "
            "from your settings."
        )
    else:
        assert str(deprecations[0].message) == (
            "The SCRAPER_SLOT_MAX_ACTIVE_SIZE setting is deprecated, use "
            "RESPONSE_MAX_ACTIVE_SIZE instead."
        )


def _raise(response: Response) -> None:
    raise ValueError(response.url)


def _ignore(failure: Failure) -> None:
    pass


class _RaiseOnSpiderInput:
    def process_spider_input(self, response: Response) -> None:
        raise ValueError(response.url)


class _IgnoreResponse:
    def process_response(self, request: Request, response: Response) -> Response:
        raise IgnoreRequest


class _BodyFileHandler:
    lazy = False

    async def download_request(self, request: Request) -> BodyFileResponse:
        await sleep(0.01)
        body_file = request.meta["body_file"]
        Path(body_file).write_bytes(b"a" * 2048)
        return BodyFileResponse(request.url, body_file=body_file)


async def _crawl_without_gc(crawler: Crawler) -> None:
    # The log capture of pytest keeps the tracebacks of logged errors, and with
    # them the responses they refer to.
    logging.disable()
    gc.disable()
    try:
        crawl_deferred = crawler.crawl()
        # A stall would otherwise hang the test.
        timeout = call_later(10, crawl_deferred.cancel)
        try:
            await maybe_deferred_to_future(crawl_deferred)
        finally:
            timeout.cancel()
    finally:
        gc.enable()
        logging.disable(logging.NOTSET)


class gt:
    __hash__ = None  # type: ignore[assignment]

    def __init__(self, value: float):
        self.value = value

    def __eq__(self, other: object) -> bool:
        return isinstance(other, (int, float)) and other > self.value

    def __repr__(self) -> str:
        return f">{self.value}"


class TestResponseMaxActiveSize:
    @coroutine_test
    async def test_default(self):
        """A crawl without custom settings has its effective response max
        active size set to 5 000 000, and triggers no deprecation warning."""
        crawler = get_crawler(OfflineSpider)
        with warnings.catch_warnings():
            warnings.simplefilter("error", ScrapyDeprecationWarning)
            await maybe_deferred_to_future(crawler.crawl())
        assert crawler.engine
        assert crawler.engine.downloader.middleware._max_active_size == 5_000_000

    @coroutine_test
    async def test_custom(self):
        """Setting RESPONSE_MAX_ACTIVE_SIZE to a custom value changes the
        effective response max active size."""
        crawler = get_crawler(
            OfflineSpider, settings_dict={"RESPONSE_MAX_ACTIVE_SIZE": 0}
        )
        with warnings.catch_warnings():
            warnings.simplefilter("error", ScrapyDeprecationWarning)
            await maybe_deferred_to_future(crawler.crawl())
        assert crawler.engine
        assert crawler.engine.downloader.middleware._max_active_size == 0

    @coroutine_test
    async def test_deprecated_default(self):
        """Setting SCRAPER_SLOT_MAX_ACTIVE_SIZE triggers a deprecation warning,
        even if it is the default value."""
        crawler = get_crawler(
            OfflineSpider, settings_dict={"SCRAPER_SLOT_MAX_ACTIVE_SIZE": 5_000_000}
        )
        with pytest.warns(ScrapyDeprecationWarning) as warning_messages:
            await maybe_deferred_to_future(crawler.crawl())
        assert crawler.engine
        assert crawler.engine.downloader.middleware._max_active_size == 5_000_000
        _assert_scraper_slot_deprecation(warning_messages)

    @coroutine_test
    async def test_deprecated_custom(self):
        """Setting SCRAPER_SLOT_MAX_ACTIVE_SIZE to a custom value triggers a
        deprecation warning, and changes the effective response max active
        size."""
        crawler = get_crawler(
            OfflineSpider, settings_dict={"SCRAPER_SLOT_MAX_ACTIVE_SIZE": 0}
        )
        with pytest.warns(ScrapyDeprecationWarning) as warning_messages:
            await maybe_deferred_to_future(crawler.crawl())
        assert crawler.engine
        assert crawler.engine.downloader.middleware._max_active_size == 0
        _assert_scraper_slot_deprecation(warning_messages)

    @coroutine_test
    async def test_both(self):
        """Setting RESPONSE_MAX_ACTIVE_SIZE and SCRAPER_SLOT_MAX_ACTIVE_SIZE to
        different values with the same setting priority triggers a deprecation
        warning about SCRAPER_SLOT_MAX_ACTIVE_SIZE being ignored, and makes
        the value of RESPONSE_MAX_ACTIVE_SIZE the effective response max active
        size."""
        crawler = get_crawler(
            OfflineSpider,
            settings_dict={
                "RESPONSE_MAX_ACTIVE_SIZE": 1,
                "SCRAPER_SLOT_MAX_ACTIVE_SIZE": 2,
            },
        )
        with pytest.warns(ScrapyDeprecationWarning) as warning_messages:
            await maybe_deferred_to_future(crawler.crawl())
        assert crawler.engine
        assert crawler.engine.downloader.middleware._max_active_size == 1
        _assert_scraper_slot_deprecation(warning_messages, ignored=True)

    @coroutine_test
    async def test_both_deprecated_priority(self):
        """Setting RESPONSE_MAX_ACTIVE_SIZE and SCRAPER_SLOT_MAX_ACTIVE_SIZE to
        different values and SCRAPER_SLOT_MAX_ACTIVE_SIZE with a higher
        priority triggers a deprecation warning about
        SCRAPER_SLOT_MAX_ACTIVE_SIZE but also makes the value of
        SCRAPER_SLOT_MAX_ACTIVE_SIZE the effective response max active size."""

        class TestSpider(Spider):
            name = "test"
            start_urls = ["data:,"]

            @classmethod
            def update_settings(cls, settings):
                settings.set("RESPONSE_MAX_ACTIVE_SIZE", 1, priority=100)
                settings.set("SCRAPER_SLOT_MAX_ACTIVE_SIZE", 2, priority=101)

            def parse(self, response):
                pass

        crawler = get_crawler(TestSpider)
        with pytest.warns(ScrapyDeprecationWarning) as warning_messages:
            await maybe_deferred_to_future(crawler.crawl())
        assert crawler.engine
        assert crawler.engine.downloader.middleware._max_active_size == 2
        _assert_scraper_slot_deprecation(warning_messages)


class TestResponseRoughSize:
    @pytest.fixture(autouse=True)
    def use_caplog(self, caplog):
        self.caplog = caplog

    @pytest.mark.parametrize(
        ("settings_dict", "expected"),
        [
            # A quarter of RESPONSE_MAX_ACTIVE_SIZE split among
            # CONCURRENT_REQUESTS requests.
            ({}, 78125),
            ({"CONCURRENT_REQUESTS": 100}, 12500),
            ({"RESPONSE_MAX_ACTIVE_SIZE": 8_000_000}, 125_000),
            # Unlimited concurrency leaves no number of requests to split it
            # among.
            ({"CONCURRENT_REQUESTS": 0}, 0),
            ({"RESPONSE_MAX_ACTIVE_SIZE": 0}, 0),
            ({"RESPONSE_ROUGH_SIZE": 1}, 1),
            ({"RESPONSE_ROUGH_SIZE": 0}, 0),
        ],
    )
    @coroutine_test
    async def test_value(self, settings_dict, expected):
        crawler = get_crawler(OfflineSpider, settings_dict=settings_dict)
        with warnings.catch_warnings():
            warnings.simplefilter("error", ScrapyDeprecationWarning)
            await maybe_deferred_to_future(crawler.crawl())
        assert crawler.engine
        assert crawler.engine.downloader.middleware._response_rough_size == expected

    @coroutine_test
    async def test_response_replaces_rough_size(self):
        """The rough size of a request stops counting as soon as the size of its
        response is known."""
        sizes: list[tuple[int, int]] = []

        class DownloaderMiddleware:
            def __init__(self, crawler):
                self.crawler = crawler

            @classmethod
            def from_crawler(cls, crawler):
                return cls(crawler)

            def process_response(self, request, response):
                middleware = self.crawler.engine.downloader.middleware
                sizes.append(
                    (middleware._rough_active_size, middleware._response_active_size)
                )
                return response

        class TestSpider(Spider):
            name = "test"
            start_urls = ["data:,a"]
            custom_settings = {
                "DOWNLOADER_MIDDLEWARES": {DownloaderMiddleware: 0},
            }

            def parse(self, response):
                pass

        crawler = get_crawler(TestSpider)
        await maybe_deferred_to_future(crawler.crawl())

        assert sizes == [(0, 1)]
        assert crawler.engine
        assert crawler.engine.downloader.middleware._rough_sizes == {}

    @pytest.mark.only_asyncio
    @coroutine_test
    async def test_same_request_downloaded_twice(self):
        """The rough size of a request object being downloaded twice at the same
        time is counted once, so that it is gone once both downloads finish."""

        class TestSpider(Spider):
            name = "test"
            start_urls = ["data:,"]
            custom_settings = {"RESPONSE_ROUGH_SIZE": 1024}

            async def parse(self, response):
                assert self.crawler.engine
                request = Request("data:,a")
                # Only one of the two downloads succeeds, the other one fails
                # because the request object is already being downloaded.
                await asyncio.gather(
                    self.crawler.engine.download_async(request),
                    self.crawler.engine.download_async(request),
                    return_exceptions=True,
                )

        crawler = get_crawler(TestSpider)
        await maybe_deferred_to_future(crawler.crawl())

        assert crawler.engine
        middleware = crawler.engine.downloader.middleware
        assert middleware._rough_sizes == {}
        assert middleware._rough_active_size == 0

    @coroutine_test
    async def test_rough_size_triggers_backout(self):
        """Rough sizes of requests being downloaded count toward the limit, even
        if their responses turn out to be empty."""

        class SlowDown:
            """Keeps requests in flight long enough for the engine to check for
            backout while their rough size is being counted."""

            async def process_request(self, request):
                await sleep(0.01)

        class TestSpider(Spider):
            name = "test"
            start_urls = ["data:,", "data:,"]
            custom_settings = {
                "DOWNLOADER_MIDDLEWARES": {SlowDown: 0},
                "RESPONSE_MAX_ACTIVE_SIZE": 512,
                "RESPONSE_ROUGH_SIZE": 1024,
            }

            def parse(self, response):
                pass

        crawler = get_crawler(TestSpider)
        self.caplog.clear()
        with self.caplog.at_level("INFO"):
            await maybe_deferred_to_future(crawler.crawl())

        assert _count_backout_logs(self.caplog) == 1

        expected_stats = {
            "request_backout_seconds/response_max_active_size": gt(0),
            "request_backout_seconds/total": gt(0),
        }
        assert _backout_stats(crawler) == expected_stats

    @coroutine_test
    async def test_body_file(self, tmp_path):
        """Requests and responses whose body is written to a file do not count
        toward the limit."""

        class TestSpider(Spider):
            name = "test"
            custom_settings = {
                "DOWNLOAD_HANDLERS": {"https": _BodyFileHandler},
                "RESPONSE_MAX_ACTIVE_SIZE": 512,
                "RESPONSE_ROUGH_SIZE": 1024,
            }

            async def start(self):
                for n in range(2):
                    yield Request(
                        f"https://example.com/{n}",
                        meta={"body_file": tmp_path / str(n)},
                    )

            def parse(self, response):
                pass

        crawler = get_crawler(TestSpider)
        self.caplog.clear()
        with self.caplog.at_level("INFO"):
            await maybe_deferred_to_future(crawler.crawl())

        assert crawler.stats
        assert crawler.stats.get_value("response_received_count") == 2
        assert _count_backout_logs(self.caplog) == 0
        assert _backout_stats(crawler) == {}

    @pytest.mark.only_asyncio
    @coroutine_test
    async def test_body_file_download_async(self, tmp_path):
        """download_async() requests whose response body is written to a file
        are not held back by the limit."""
        active = 0
        max_active = 0

        class Handler(_BodyFileHandler):
            async def download_request(self, request: Request) -> BodyFileResponse:
                nonlocal active, max_active
                active += 1
                max_active = max(max_active, active)
                try:
                    return await super().download_request(request)
                finally:
                    active -= 1

        class TestSpider(Spider):
            name = "test"
            start_urls = ["data:,"]
            custom_settings = {
                "DOWNLOAD_HANDLERS": {"https": Handler},
                "RESPONSE_MAX_ACTIVE_SIZE": 512,
                "RESPONSE_ROUGH_SIZE": 1024,
            }

            async def parse(self, response):
                assert self.crawler.engine
                await asyncio.gather(
                    *(
                        self.crawler.engine.download_async(
                            Request(
                                f"https://example.com/{n}",
                                meta={"body_file": tmp_path / str(n)},
                            )
                        )
                        for n in range(2)
                    )
                )
                yield {}

        crawler = get_crawler(TestSpider)
        await maybe_deferred_to_future(crawler.crawl())

        assert crawler.stats
        assert crawler.stats.get_value("item_scraped_count") == 1
        assert max_active == 2


class TestRequestBackout:
    @pytest.fixture(autouse=True)
    def use_caplog(self, caplog):
        self.caplog = caplog

    @coroutine_test
    async def test_none(self):

        class TestSpider(Spider):
            name = "test"
            start_urls = ["data:,"]

            def parse(self, response):
                pass

        crawler = get_crawler(TestSpider)
        self.caplog.clear()
        with self.caplog.at_level("INFO"):
            await maybe_deferred_to_future(crawler.crawl())

        assert _count_backout_logs(self.caplog) == 0

        assert _backout_stats(crawler) == {}

    @coroutine_test
    async def test_concurrency(self):

        class SlowDown:
            """Downloader middleware that returns a non-instant deferred from
            process_request, to force need_backout calls to happen at that
            point.

            The delay is deliberately non-zero so that the concurrency backout
            state lasts a measurable amount of wall-clock time, which keeps the
            request_backout_seconds/concurrency stat reliably above 0."""

            def process_request(self, request):
                from twisted.internet import reactor

                d: Deferred[None] = Deferred()
                reactor.callLater(0.01, d.callback, None)
                return d

        class TestSpider(Spider):
            name = "test"
            # Several start URLs so that, with CONCURRENT_REQUESTS=1, the engine
            # reliably attempts to schedule a second request while the first one
            # is still active, which is what triggers the concurrency backout.
            start_urls = ["data:,"] * 5
            custom_settings = {
                "CONCURRENT_REQUESTS": 1,
                "DOWNLOADER_MIDDLEWARES": {SlowDown: 0},
            }

            def parse(self, response):
                pass

        crawler = get_crawler(TestSpider)
        self.caplog.clear()
        with self.caplog.at_level("INFO"):
            await maybe_deferred_to_future(crawler.crawl())

        assert _count_backout_logs(self.caplog) == 0

        expected_stats = {
            "request_backout_seconds/concurrency": gt(0),
            "request_backout_seconds/total": gt(0),
        }
        assert _backout_stats(crawler) == expected_stats

    @coroutine_test
    async def test_response_size(self):

        class TestSpider(Spider):
            name = "test"
            start_urls = ["data:,a"]
            custom_settings = {
                "RESPONSE_MAX_ACTIVE_SIZE": 1,
            }

            def parse(self, response):
                pass

        crawler = get_crawler(TestSpider)
        self.caplog.clear()
        with self.caplog.at_level("INFO"):
            await maybe_deferred_to_future(crawler.crawl())

        assert _count_backout_logs(self.caplog) == 1

        expected_stats = {
            "request_backout_seconds/response_max_active_size": gt(0),
            "request_backout_seconds/total": gt(0),
        }
        assert _backout_stats(crawler) == expected_stats

    @pytest.mark.parametrize(
        ("status", "callback", "errback", "settings"),
        [
            (200, lambda response: response.css("a"), _ignore, {}),
            (200, _raise, _ignore, {}),
            (404, None, _ignore, {}),
            (404, None, None, {}),
            (404, None, lambda failure: failure, {}),
            (
                200,
                None,
                None,
                {"SPIDER_MIDDLEWARES": {_RaiseOnSpiderInput: 0}},
            ),
            (
                200,
                None,
                None,
                {"DOWNLOADER_MIDDLEWARES": {_IgnoreResponse: 1}},
            ),
        ],
        ids=[
            "selector",
            "callback-exception",
            "errback",
            "no-errback",
            "errback-failure",
            "spider-middleware-exception",
            "downloader-middleware-ignore",
        ],
    )
    @coroutine_test
    async def test_response_max_active_size_no_cycles(
        self, monkeypatch, status, callback, errback, settings
    ):
        """Scrapy frees responses through reference counting alone, so a crawl
        does not stall on RESPONSE_MAX_ACTIVE_SIZE without garbage
        collection."""
        # Keep the bypass, which collects garbage first, from lifting a stall.
        monkeypatch.setattr(Downloader, "_SIZE_BYPASS_DELAY", 60)

        class ResponseMiddleware:
            def process_request(self, request):
                return HtmlResponse(request.url, status=status, body=b"<a></a>")

        class TestSpider(Spider):
            name = "test"
            custom_settings = {
                **settings,
                "DOWNLOADER_MIDDLEWARES": {
                    ResponseMiddleware: 0,
                    **settings.get("DOWNLOADER_MIDDLEWARES", {}),
                },
                "RESPONSE_MAX_ACTIVE_SIZE": 1,
            }

            async def start(self):
                for n in range(3):
                    yield Request(
                        f"https://example.com/{n}", callback=callback, errback=errback
                    )

            def parse(self, response):
                pass

        crawler = get_crawler(TestSpider)
        await _crawl_without_gc(crawler)

        assert crawler.stats
        assert crawler.stats.get_value("downloader/response_count") == 3

    @coroutine_test
    async def test_response_max_active_size_no_cycles_media(
        self, monkeypatch, tmp_path
    ):
        monkeypatch.setattr(Downloader, "_SIZE_BYPASS_DELAY", 60)

        class ResponseMiddleware:
            def process_request(self, request):
                status = 404 if request.url.endswith("/file") else 200
                return Response(request.url, status=status, body=b"a")

        class TestSpider(Spider):
            name = "test"
            custom_settings = {
                "DOWNLOADER_MIDDLEWARES": {ResponseMiddleware: 0},
                "FILES_STORE": str(tmp_path),
                "ITEM_PIPELINES": {FilesPipeline: 1},
                "RESPONSE_MAX_ACTIVE_SIZE": 1,
            }

            async def start(self):
                for n in range(3):
                    yield Request(f"https://example.com/{n}")

            def parse(self, response):
                yield {"file_urls": [f"{response.url}/file"]}

        crawler = get_crawler(TestSpider)
        await _crawl_without_gc(crawler)

        assert crawler.stats
        assert crawler.stats.get_value("item_scraped_count") == 3

    @coroutine_test
    async def test_response_size_process_request(self):

        class DownloaderMiddleware:
            def process_request(self, request):
                return Response("https://example.com", body=b"a")

        class TestSpider(Spider):
            name = "test"
            start_urls = ["data:,"]
            custom_settings = {
                "DOWNLOADER_MIDDLEWARES": {DownloaderMiddleware: 0},
                "RESPONSE_MAX_ACTIVE_SIZE": 1,
            }

            def parse(self, response):
                pass

        crawler = get_crawler(TestSpider)
        self.caplog.clear()
        with self.caplog.at_level("INFO"):
            await maybe_deferred_to_future(crawler.crawl())

        assert _count_backout_logs(self.caplog) == 1

        expected_stats = {
            "request_backout_seconds/response_max_active_size": gt(0),
            "request_backout_seconds/total": gt(0),
        }
        assert _backout_stats(crawler) == expected_stats

    @coroutine_test
    async def test_request_from_process_request(self):
        """A request returned from process_request does not count toward the
        limit, even though requests also have a body."""

        class DownloaderMiddleware:
            def __init__(self):
                self.replaced = False

            def process_request(self, request):
                if self.replaced:
                    return None
                self.replaced = True
                return Request("data:,b", body=b"a" * 2000)

        class TestSpider(Spider):
            name = "test"
            start_urls = ["data:,"]
            custom_settings = {
                "DOWNLOADER_MIDDLEWARES": {DownloaderMiddleware: 0},
                "RESPONSE_MAX_ACTIVE_SIZE": 1000,
                "RESPONSE_ROUGH_SIZE": 0,
            }

            def parse(self, response):
                pass

        crawler = get_crawler(TestSpider)
        self.caplog.clear()
        with self.caplog.at_level("INFO"):
            await maybe_deferred_to_future(crawler.crawl())

        assert _count_backout_logs(self.caplog) == 0

        assert _backout_stats(crawler) == {}

    @coroutine_test
    async def test_response_size_process_response(self):

        class DownloaderMiddleware:
            def process_response(self, request, response):
                return Response("https://example.com", body=b"a")

        class TestSpider(Spider):
            name = "test"
            start_urls = ["data:,"]
            custom_settings = {
                "DOWNLOADER_MIDDLEWARES": {DownloaderMiddleware: 0},
                "RESPONSE_MAX_ACTIVE_SIZE": 1,
            }

            def parse(self, response):
                pass

        crawler = get_crawler(TestSpider)
        self.caplog.clear()
        with self.caplog.at_level("INFO"):
            await maybe_deferred_to_future(crawler.crawl())

        assert _count_backout_logs(self.caplog) == 1

        expected_stats = {
            "request_backout_seconds/response_max_active_size": gt(0),
            "request_backout_seconds/total": gt(0),
        }
        assert _backout_stats(crawler) == expected_stats

    @coroutine_test
    async def test_response_size_process_exception(self):

        class DownloaderMiddleware1:
            def process_exception(self, request, exception):
                return Response("https://example.com", body=b"a")

        class DownloaderMiddleware2:
            def process_request(self, request):
                raise ValueError

        class TestSpider(Spider):
            name = "test"
            start_urls = ["data:,"]
            custom_settings = {
                "DOWNLOADER_MIDDLEWARES": {
                    DownloaderMiddleware1: 0,
                    DownloaderMiddleware2: 1,
                },
                "RESPONSE_MAX_ACTIVE_SIZE": 1,
            }

            def parse(self, response):
                pass

        crawler = get_crawler(TestSpider)
        self.caplog.clear()
        with self.caplog.at_level("INFO"):
            await maybe_deferred_to_future(crawler.crawl())

        assert _count_backout_logs(self.caplog) == 1

        expected_stats = {
            "request_backout_seconds/response_max_active_size": gt(0),
            "request_backout_seconds/total": gt(0),
        }
        assert _backout_stats(crawler) == expected_stats

    @coroutine_test
    async def test_response_size_download(self):
        """Ensure that responses from engine.download calls are also taken into
        account for the RESPONSE_MAX_ACTIVE_SIZE setting."""

        class SlowDown:
            """Item pipeline that returns a non-instant deferred, to force
            need_backout calls to happen at that point."""

            def process_item(self, item):
                from twisted.internet import reactor

                d: Deferred[dict[Any, Any]] = Deferred()
                reactor.callLater(0, d.callback, {})
                return d

        class TestSpider(Spider):
            name = "test"
            start_urls = ["data:,"]
            custom_settings = {
                "ITEM_PIPELINES": {SlowDown: 0},
                "RESPONSE_MAX_ACTIVE_SIZE": 1,
            }

            async def parse(self, response):
                assert self.crawler.engine
                response = await self.crawler.engine.download_async(Request("data:,a"))
                yield {"response": response}

        crawler = get_crawler(TestSpider)
        self.caplog.clear()
        with self.caplog.at_level("INFO"):
            await maybe_deferred_to_future(crawler.crawl())

        assert _count_backout_logs(self.caplog) == 1

        expected_stats = {
            "request_backout_seconds/response_max_active_size": gt(0),
            "request_backout_seconds/total": gt(0),
        }
        assert _backout_stats(crawler) == expected_stats

    @pytest.mark.parametrize("shared_slot", [True, False])
    @coroutine_test
    async def test_response_max_active_size_media_downloads(self, shared_slot):
        """Responses of media pipeline requests waiting for a slow upload hold
        back the next media downloads.
        """
        max_active_size = 3000
        uploads = 0
        peak_uploads = 0

        class SlowStore(_NoStatStore):
            async def persist_file(self, path, buf, info, meta=None, headers=None):
                nonlocal uploads, peak_uploads
                uploads += 1
                peak_uploads = max(peak_uploads, uploads)
                await sleep(0.05)
                uploads -= 1

        class TestSpider(_MediaSpider):
            file_count = 20
            file_size = 1000
            custom_settings = {
                "FILES_STORE": "test://",
                "ITEM_PIPELINES": {
                    _SharedSlotFilesPipeline
                    if shared_slot
                    else _SlotPerFileFilesPipeline: 1
                },
                "MEDIA_STORAGES": {"test": SlowStore},
                "RESPONSE_MAX_ACTIVE_SIZE": max_active_size,
                "RESPONSE_ROUGH_SIZE": file_size,
            }

        crawler = get_crawler(TestSpider)
        await maybe_deferred_to_future(crawler.crawl())

        assert crawler.stats
        assert crawler.stats.get_value("file_count") == 20
        assert peak_uploads == max_active_size // TestSpider.file_size
        assert crawler.stats.get_value("response_max_active_size/bypass_count") is None

    @coroutine_test
    async def test_response_max_active_size_scheduled_response_with_files(self):
        """A scheduled response above the limit does not hold back the media
        downloads that it waits for.
        """

        class TestSpider(_MediaSpider):
            start_urls = [f"data:,{'a' * 2000}"]
            custom_settings = {
                "FILES_STORE": "test://",
                "ITEM_PIPELINES": {_SharedSlotFilesPipeline: 1},
                "MEDIA_STORAGES": {"test": _NoStatStore},
                "RESPONSE_MAX_ACTIVE_SIZE": 1000,
            }
            file_count = 3
            file_size = 10

        crawler = get_crawler(TestSpider)
        await maybe_deferred_to_future(crawler.crawl())

        assert crawler.stats
        assert crawler.stats.get_value("file_count") == 3
        assert crawler.stats.get_value("response_max_active_size/bypass_count") is None

    @coroutine_test
    async def test_response_max_active_size_scheduled_request_behind_held_back(
        self, monkeypatch
    ):
        """Scheduled requests queued in a slot behind a held-back
        download_async() request are downloaded first, and the bypass lets it
        through even if it is due while the slot waits for its download
        delay. Once it is through, scheduled requests are not held back.
        """
        monkeypatch.setattr(Downloader, "_SIZE_BYPASS_DELAY", 0.01)
        downloads: list[int | str] = []
        scheduled_reached: Deferred[None] = Deferred()
        scheduled_downloaded: Deferred[None] = Deferred()

        class Handler(DataURIDownloadHandler):
            async def download_request(self, request: Request) -> Response:
                # Keeps the slot busy until the scheduled requests are queued
                # behind the held-back one.
                if request.meta.get("wait_for_scheduled"):
                    await maybe_deferred_to_future(scheduled_reached)
                return await super().download_request(request)

        class TestSpider(Spider):
            name = "test"
            start_urls = ["data:,"]
            custom_settings = {
                "CONCURRENT_REQUESTS_PER_DOMAIN": 1,
                "DOWNLOAD_DELAY": 0.2,
                "DOWNLOAD_DELAY_JITTER": 0,
                "DOWNLOAD_HANDLERS": {"data": Handler},
                "RESPONSE_MAX_ACTIVE_SIZE": 1000,
                "RESPONSE_ROUGH_SIZE": 1,
            }
            scheduled_count = 0

            def request_reached_downloader(self, request: Request) -> None:
                if request.url[-1].isdigit():
                    self.scheduled_count += 1
                    if self.scheduled_count == 4:
                        scheduled_reached.callback(None)

            def response_downloaded(self, response: Response) -> None:
                if response.url == "data:,a":
                    downloads.append("a")
                elif response.url[-1].isdigit():
                    downloads.append(int(response.text))
                    if len(downloads) == 5:
                        scheduled_downloaded.callback(None)

            async def parse(self, response):
                assert self.crawler.engine
                self.crawler.signals.connect(
                    self.request_reached_downloader,
                    signals.request_reached_downloader,
                )
                self.crawler.signals.connect(
                    self.response_downloaded, signals.response_downloaded
                )
                download_async = self.crawler.engine.download_async
                kept_dfd = deferred_from_coro(
                    download_async(
                        Request(
                            f"data:,{'a' * 2000}", meta={"wait_for_scheduled": True}
                        )
                    )
                )
                held_back_dfd = deferred_from_coro(download_async(Request("data:,a")))
                for n in range(4):
                    yield Request(f"data:,{n}", callback=self.parse_b)
                kept = await maybe_deferred_to_future(kept_dfd)
                await maybe_deferred_to_future(held_back_dfd)
                await maybe_deferred_to_future(scheduled_downloaded)
                assert kept
                yield {}

            def parse_b(self, response):
                pass

        crawler = get_crawler(TestSpider)
        crawl_deferred = crawler.crawl()
        # Scheduled requests held back after the bypass would otherwise hang
        # the test.
        timeout = call_later(10, crawl_deferred.cancel)
        try:
            await maybe_deferred_to_future(crawl_deferred)
        finally:
            timeout.cancel()

        assert crawler.stats
        assert downloads == [3, "a", 2, 1, 0]
        assert crawler.stats.get_value("response_max_active_size/bypass_count") == 1

    @pytest.mark.parametrize(
        ("kept_count", "kept_size", "examples", "more"),
        [(1, 2000, 1, ""), (4, 300, 3, " (+1 more)")],
    )
    @coroutine_test
    async def test_response_max_active_size_bypass(
        self, monkeypatch, kept_count, kept_size, examples, more
    ):
        """Code that keeps a response to a download_async() request above the
        limit while it awaits another one slows down instead of stalling.
        """
        monkeypatch.setattr(Downloader, "_SIZE_BYPASS_DELAY", 0.01)

        class TestSpider(Spider):
            name = "test"
            start_urls = ["data:,"]
            custom_settings = {
                "RESPONSE_MAX_ACTIVE_SIZE": 1000,
            }

            async def parse(self, response):
                assert self.crawler.engine
                kept = [
                    await self.crawler.engine.download_async(
                        Request(f"data:,{n:0{kept_size}}")
                    )
                    for n in range(kept_count)
                ]
                for n in range(2):
                    await self.crawler.engine.download_async(Request(f"data:,{n}"))
                assert kept
                yield {}

        crawler = get_crawler(TestSpider)
        self.caplog.clear()
        with self.caplog.at_level("INFO"):
            await maybe_deferred_to_future(crawler.crawl())

        assert crawler.stats
        assert crawler.stats.get_value("item_scraped_count") == 1
        assert crawler.stats.get_value("response_max_active_size/bypass_count") == 2
        messages = [
            record.getMessage()
            for record in self.caplog.records
            if record.getMessage().startswith("Letting")
        ]
        assert len(messages) == 1
        assert "<GET data:,0>" in messages[0]
        assert messages[0].count("<200 data:,") == examples
        assert f">{more}, have used" in messages[0]

    @coroutine_test
    async def test_response_max_active_size_scheduled_bypass(self, monkeypatch):
        """Code that keeps responses to scheduled requests above the limit
        slows down instead of stalling.
        """
        monkeypatch.setattr(Downloader, "_SIZE_BYPASS_DELAY", 0.01)
        monkeypatch.setattr(ExecutionEngine, "_SLOT_HEARTBEAT_INTERVAL", 0.01)

        class TestSpider(Spider):
            name = "test"
            start_urls = [f"data:,{n}" for n in range(3)]
            custom_settings = {
                "RESPONSE_MAX_ACTIVE_SIZE": 1,
            }
            kept: list[Response] = []

            def parse(self, response):
                self.kept.append(response)

        crawler = get_crawler(TestSpider)
        self.caplog.clear()
        with self.caplog.at_level("INFO"):
            crawl_deferred = crawler.crawl()
            # A stall would otherwise hang the test.
            timeout = call_later(10, crawl_deferred.cancel)
            try:
                await maybe_deferred_to_future(crawl_deferred)
            finally:
                timeout.cancel()

        assert crawler.stats
        assert crawler.stats.get_value("response_received_count") == 3
        assert crawler.stats.get_value("response_max_active_size/bypass_count") == 2
        records = [
            record
            for record in self.caplog.records
            if record.getMessage().startswith("Letting")
        ]
        assert len(records) == 1
        assert records[0].levelno == logging.WARNING
        assert "<200 data:," in records[0].getMessage()

    @pytest.mark.parametrize("awaited", [False, True])
    @coroutine_test
    async def test_response_max_active_size_collects_cycles(self, monkeypatch, awaited):
        """Responses in a reference cycle stop counting toward the limit once
        it holds back requests, even with automatic garbage collection
        disabled.
        """
        monkeypatch.setattr(Downloader, "_SIZE_BYPASS_DELAY", 0.01)
        monkeypatch.setattr(ExecutionEngine, "_SLOT_HEARTBEAT_INTERVAL", 0.01)

        def keep_in_cycle(response: Response) -> None:
            cycle: list[Any] = [response]
            cycle.append(cycle)

        class TestSpider(Spider):
            name = "test"
            start_urls = ["data:,"] if awaited else [f"data:,{n}" for n in range(3)]
            custom_settings = {
                "RESPONSE_MAX_ACTIVE_SIZE": 1,
            }

            async def parse(self, response):
                if not awaited:
                    keep_in_cycle(response)
                    yield {}
                    return
                assert self.crawler.engine
                for n in range(3):
                    keep_in_cycle(
                        await self.crawler.engine.download_async(Request(f"data:,{n}"))
                    )
                    yield {}

        crawler = get_crawler(TestSpider)
        await _crawl_without_gc(crawler)

        assert crawler.stats
        assert crawler.stats.get_value("item_scraped_count") == 3
        assert crawler.stats.get_value("response_max_active_size/bypass_count") is None


class _NoStatStore:
    checksum_algorithm = "md5"

    def __init__(self, uri: str):
        pass

    def stat_file(self, path, info):
        return {}

    def persist_file(self, path, buf, info, meta=None, headers=None):
        pass


class _SharedSlotFilesPipeline(FilesPipeline):
    pass


class _SlotPerFileFilesPipeline(FilesPipeline):
    def get_media_requests(self, item, info):
        return [
            Request(url, meta={"download_slot": url}, callback=NO_CALLBACK)
            for url in item["file_urls"]
        ]


class _MediaSpider(Spider):
    name = "test"
    start_urls = ["data:,"]
    file_count: int
    file_size: int

    def parse(self, response):
        yield {
            "file_urls": [
                f"data:,{n:0{self.file_size}}" for n in range(self.file_count)
            ]
        }
