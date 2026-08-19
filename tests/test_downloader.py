import asyncio
import warnings
from typing import Any

import pytest
from twisted.internet.defer import Deferred

from scrapy import Request, Spider
from scrapy.crawler import Crawler
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.http import Response
from scrapy.utils.asyncio import sleep
from scrapy.utils.defer import maybe_deferred_to_future
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
