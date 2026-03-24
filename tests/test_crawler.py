import asyncio
import logging
import re
import warnings
from collections.abc import Generator
from pathlib import Path
from typing import Any, cast

import pytest
from twisted.internet.defer import Deferred
from zope.interface.exceptions import MultipleInvalid

import scrapy
from scrapy import Spider
from scrapy.crawler import (
    AsyncCrawlerProcess,
    AsyncCrawlerRunner,
    Crawler,
    CrawlerProcess,
    CrawlerRunner,
    CrawlerRunnerBase,
)
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.extensions.throttle import AutoThrottle
from scrapy.settings import Settings, default_settings
from scrapy.utils.defer import deferred_from_coro, maybe_deferred_to_future
from scrapy.utils.log import (
    _uninstall_scrapy_root_handler,
    configure_logging,
    get_scrapy_root_handler,
)
from scrapy.utils.spider import DefaultSpider
from scrapy.utils.test import get_crawler, get_reactor_settings
from tests.utils.decorators import coroutine_test, inline_callbacks_test

BASE_SETTINGS: dict[str, Any] = {}


def get_raw_crawler(spidercls=None, settings_dict=None):
    """get_crawler alternative that only calls the __init__ method of the
    crawler."""
    settings = Settings()
    settings.setdict(get_reactor_settings())
    settings.setdict(settings_dict or {})
    return Crawler(spidercls or DefaultSpider, settings)


class TestBaseCrawler:
    def assertOptionIsDefault(self, settings: Settings, key: str) -> None:
        assert isinstance(settings, Settings)
        assert settings[key] == getattr(default_settings, key)


class TestCrawler(TestBaseCrawler):
    def test_populate_spidercls_settings(self):
        spider_settings = {"TEST1": "spider", "TEST2": "spider"}
        project_settings = {
            **BASE_SETTINGS,
            "TEST1": "project",
            "TEST3": "project",
            **get_reactor_settings(),
        }

        class CustomSettingsSpider(DefaultSpider):
            custom_settings = spider_settings

        settings = Settings()
        settings.setdict(project_settings, priority="project")
        crawler = Crawler(CustomSettingsSpider, settings)
        crawler._apply_settings()

        assert crawler.settings.get("TEST1") == "spider"
        assert crawler.settings.get("TEST2") == "spider"
        assert crawler.settings.get("TEST3") == "project"

        assert not settings.frozen
        assert crawler.settings.frozen

    def test_crawler_accepts_dict(self):
        crawler = get_crawler(DefaultSpider, {"foo": "bar"})
        assert crawler.settings["foo"] == "bar"
        self.assertOptionIsDefault(crawler.settings, "RETRY_ENABLED")

    def test_crawler_accepts_None(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ScrapyDeprecationWarning)
            crawler = Crawler(DefaultSpider)
        self.assertOptionIsDefault(crawler.settings, "RETRY_ENABLED")

    def test_crawler_rejects_spider_objects(self):
        with pytest.raises(ValueError, match="spidercls argument must be a class"):
            Crawler(DefaultSpider())

    @inline_callbacks_test
    def test_crawler_crawl_twice_seq_unsupported(self):
        crawler = get_raw_crawler(NoRequestsSpider, BASE_SETTINGS)
        yield crawler.crawl()
        with pytest.raises(RuntimeError, match="more than once on the same instance"):
            yield crawler.crawl()

    @coroutine_test
    async def test_crawler_crawl_async_twice_seq_unsupported(self):
        crawler = get_raw_crawler(NoRequestsSpider, BASE_SETTINGS)
        await crawler.crawl_async()
        with pytest.raises(RuntimeError, match="more than once on the same instance"):
            await crawler.crawl_async()

    @inline_callbacks_test
    def test_crawler_crawl_twice_parallel_unsupported(self):
        crawler = get_raw_crawler(NoRequestsSpider, BASE_SETTINGS)
        d1 = crawler.crawl()
        d2 = crawler.crawl()
        yield d1
        with pytest.raises(RuntimeError, match="Crawling already taking place"):
            yield d2

    @pytest.mark.only_asyncio
    @coroutine_test
    async def test_crawler_crawl_async_twice_parallel_unsupported(self):
        crawler = get_raw_crawler(NoRequestsSpider, BASE_SETTINGS)
        t1 = asyncio.create_task(crawler.crawl_async())
        t2 = asyncio.create_task(crawler.crawl_async())
        await t1
        with pytest.raises(RuntimeError, match="Crawling already taking place"):
            await t2

    def test_get_addon(self):
        class ParentAddon:
            pass

        class TrackingAddon(ParentAddon):
            instances = []

            def __init__(self):
                TrackingAddon.instances.append(self)

            def update_settings(self, settings):
                pass

        settings = {
            **BASE_SETTINGS,
            "ADDONS": {
                TrackingAddon: 0,
            },
        }
        crawler = get_crawler(settings_dict=settings)
        assert len(TrackingAddon.instances) == 1
        expected = TrackingAddon.instances[-1]

        addon = crawler.get_addon(TrackingAddon)
        assert addon == expected

        addon = crawler.get_addon(DefaultSpider)
        assert addon is None

        addon = crawler.get_addon(ParentAddon)
        assert addon == expected

        class ChildAddon(TrackingAddon):
            pass

        addon = crawler.get_addon(ChildAddon)
        assert addon is None

    @inline_callbacks_test
    def test_get_downloader_middleware(self):
        class ParentDownloaderMiddleware:
            pass

        class TrackingDownloaderMiddleware(ParentDownloaderMiddleware):
            instances = []

            def __init__(self):
                TrackingDownloaderMiddleware.instances.append(self)

        class MySpider(Spider):
            name = "myspider"

            @classmethod
            def from_crawler(cls, crawler):
                return cls(crawler=crawler)

            def __init__(self, crawler, **kwargs: Any):
                super().__init__(**kwargs)
                self.crawler = crawler

            async def start(self):
                MySpider.result = crawler.get_downloader_middleware(MySpider.cls)
                return
                yield

        settings = {
            **BASE_SETTINGS,
            "DOWNLOADER_MIDDLEWARES": {
                TrackingDownloaderMiddleware: 0,
            },
        }

        crawler = get_raw_crawler(MySpider, settings)
        MySpider.cls = TrackingDownloaderMiddleware
        yield crawler.crawl()
        assert len(TrackingDownloaderMiddleware.instances) == 1
        assert MySpider.result == TrackingDownloaderMiddleware.instances[-1]

        crawler = get_raw_crawler(MySpider, settings)
        MySpider.cls = DefaultSpider
        yield crawler.crawl()
        assert MySpider.result is None

        crawler = get_raw_crawler(MySpider, settings)
        MySpider.cls = ParentDownloaderMiddleware
        yield crawler.crawl()
        assert MySpider.result == TrackingDownloaderMiddleware.instances[-1]

        class ChildDownloaderMiddleware(TrackingDownloaderMiddleware):
            pass

        crawler = get_raw_crawler(MySpider, settings)
        MySpider.cls = ChildDownloaderMiddleware
        yield crawler.crawl()
        assert MySpider.result is None

    def test_get_downloader_middleware_not_crawling(self):
        crawler = get_raw_crawler(settings_dict=BASE_SETTINGS)
        with pytest.raises(RuntimeError):
            crawler.get_downloader_middleware(DefaultSpider)

    @inline_callbacks_test
    def test_get_downloader_middleware_no_engine(self):
        class MySpider(Spider):
            name = "myspider"

            @classmethod
            def from_crawler(cls, crawler):
                try:
                    crawler.get_downloader_middleware(DefaultSpider)
                except Exception as e:
                    MySpider.result = e
                    raise

        crawler = get_raw_crawler(MySpider, BASE_SETTINGS)
        with pytest.raises(RuntimeError):
            yield crawler.crawl()

    @inline_callbacks_test
    def test_get_extension(self):
        class ParentExtension:
            pass

        class TrackingExtension(ParentExtension):
            instances = []

            def __init__(self):
                TrackingExtension.instances.append(self)

        class MySpider(Spider):
            name = "myspider"

            @classmethod
            def from_crawler(cls, crawler):
                return cls(crawler=crawler)

            def __init__(self, crawler, **kwargs: Any):
                super().__init__(**kwargs)
                self.crawler = crawler

            async def start(self):
                MySpider.result = crawler.get_extension(MySpider.cls)
                return
                yield

        settings = {
            **BASE_SETTINGS,
            "EXTENSIONS": {
                TrackingExtension: 0,
            },
        }

        crawler = get_raw_crawler(MySpider, settings)
        MySpider.cls = TrackingExtension
        yield crawler.crawl()
        assert len(TrackingExtension.instances) == 1
        assert MySpider.result == TrackingExtension.instances[-1]

        crawler = get_raw_crawler(MySpider, settings)
        MySpider.cls = DefaultSpider
        yield crawler.crawl()
        assert MySpider.result is None

        crawler = get_raw_crawler(MySpider, settings)
        MySpider.cls = ParentExtension
        yield crawler.crawl()
        assert MySpider.result == TrackingExtension.instances[-1]

        class ChildExtension(TrackingExtension):
            pass

        crawler = get_raw_crawler(MySpider, settings)
        MySpider.cls = ChildExtension
        yield crawler.crawl()
        assert MySpider.result is None

    def test_get_extension_not_crawling(self):
        crawler = get_raw_crawler(settings_dict=BASE_SETTINGS)
        with pytest.raises(RuntimeError):
            crawler.get_extension(DefaultSpider)

    @inline_callbacks_test
    def test_get_extension_no_engine(self):
        class MySpider(Spider):
            name = "myspider"

            @classmethod
            def from_crawler(cls, crawler):
                try:
                    crawler.get_extension(DefaultSpider)
                except Exception as e:
                    MySpider.result = e
                    raise

        crawler = get_raw_crawler(MySpider, BASE_SETTINGS)
        with pytest.raises(RuntimeError):
            yield crawler.crawl()

    @inline_callbacks_test
    def test_get_item_pipeline(self):
        class ParentItemPipeline:
            pass

        class TrackingItemPipeline(ParentItemPipeline):
            instances = []

            def __init__(self):
                TrackingItemPipeline.instances.append(self)

        class MySpider(Spider):
            name = "myspider"

            @classmethod
            def from_crawler(cls, crawler):
                return cls(crawler=crawler)

            def __init__(self, crawler, **kwargs: Any):
                super().__init__(**kwargs)
                self.crawler = crawler

            async def start(self):
                MySpider.result = crawler.get_item_pipeline(MySpider.cls)
                return
                yield

        settings = {
            **BASE_SETTINGS,
            "ITEM_PIPELINES": {
                TrackingItemPipeline: 0,
            },
        }

        crawler = get_raw_crawler(MySpider, settings)
        MySpider.cls = TrackingItemPipeline
        yield crawler.crawl()
        assert len(TrackingItemPipeline.instances) == 1
        assert MySpider.result == TrackingItemPipeline.instances[-1]

        crawler = get_raw_crawler(MySpider, settings)
        MySpider.cls = DefaultSpider
        yield crawler.crawl()
        assert MySpider.result is None

        crawler = get_raw_crawler(MySpider, settings)
        MySpider.cls = ParentItemPipeline
        yield crawler.crawl()
        assert MySpider.result == TrackingItemPipeline.instances[-1]

        class ChildItemPipeline(TrackingItemPipeline):
            pass

        crawler = get_raw_crawler(MySpider, settings)
        MySpider.cls = ChildItemPipeline
        yield crawler.crawl()
        assert MySpider.result is None

    def test_get_item_pipeline_not_crawling(self):
        crawler = get_raw_crawler(settings_dict=BASE_SETTINGS)
        with pytest.raises(RuntimeError):
            crawler.get_item_pipeline(DefaultSpider)

    @inline_callbacks_test
    def test_get_item_pipeline_no_engine(self):
        class MySpider(Spider):
            name = "myspider"

            @classmethod
            def from_crawler(cls, crawler):
                try:
                    crawler.get_item_pipeline(DefaultSpider)
                except Exception as e:
                    MySpider.result = e
                    raise

        crawler = get_raw_crawler(MySpider, BASE_SETTINGS)
        with pytest.raises(RuntimeError):
            yield crawler.crawl()

    @inline_callbacks_test
    def test_get_spider_middleware(self):
        class ParentSpiderMiddleware:
            pass

        class TrackingSpiderMiddleware(ParentSpiderMiddleware):
            instances = []

            def __init__(self):
                TrackingSpiderMiddleware.instances.append(self)

        class MySpider(Spider):
            name = "myspider"

            @classmethod
            def from_crawler(cls, crawler):
                return cls(crawler=crawler)

            def __init__(self, crawler, **kwargs: Any):
                super().__init__(**kwargs)
                self.crawler = crawler

            async def start(self):
                MySpider.result = crawler.get_spider_middleware(MySpider.cls)
                return
                yield

        settings = {
            **BASE_SETTINGS,
            "SPIDER_MIDDLEWARES": {
                TrackingSpiderMiddleware: 0,
            },
        }

        crawler = get_raw_crawler(MySpider, settings)
        MySpider.cls = TrackingSpiderMiddleware
        yield crawler.crawl()
        assert len(TrackingSpiderMiddleware.instances) == 1
        assert MySpider.result == TrackingSpiderMiddleware.instances[-1]

        crawler = get_raw_crawler(MySpider, settings)
        MySpider.cls = DefaultSpider
        yield crawler.crawl()
        assert MySpider.result is None

        crawler = get_raw_crawler(MySpider, settings)
        MySpider.cls = ParentSpiderMiddleware
        yield crawler.crawl()
        assert MySpider.result == TrackingSpiderMiddleware.instances[-1]

        class ChildSpiderMiddleware(TrackingSpiderMiddleware):
            pass

        crawler = get_raw_crawler(MySpider, settings)
        MySpider.cls = ChildSpiderMiddleware
        yield crawler.crawl()
        assert MySpider.result is None

    def test_get_spider_middleware_not_crawling(self):
        crawler = get_raw_crawler(settings_dict=BASE_SETTINGS)
        with pytest.raises(RuntimeError):
            crawler.get_spider_middleware(DefaultSpider)

    @inline_callbacks_test
    def test_get_spider_middleware_no_engine(self):
        class MySpider(Spider):
            name = "myspider"

            @classmethod
            def from_crawler(cls, crawler):
                try:
                    crawler.get_spider_middleware(DefaultSpider)
                except Exception as e:
                    MySpider.result = e
                    raise

        crawler = get_raw_crawler(MySpider, BASE_SETTINGS)
        with pytest.raises(RuntimeError):
            yield crawler.crawl()


class TestSpiderSettings:
    def test_spider_custom_settings(self):
        class MySpider(scrapy.Spider):
            name = "spider"
            custom_settings = {"AUTOTHROTTLE_ENABLED": True}

        crawler = get_crawler(MySpider)
        enabled_exts = [e.__class__ for e in crawler.extensions.middlewares]
        assert AutoThrottle in enabled_exts


class TestCrawlerLogging:
    def test_no_root_handler_installed(self):
        handler = get_scrapy_root_handler()
        if handler is not None:
            logging.root.removeHandler(handler)

        class MySpider(scrapy.Spider):
            name = "spider"

        get_crawler(MySpider)
        assert get_scrapy_root_handler() is None

    @coroutine_test
    async def test_spider_custom_settings_log_level(self, tmp_path):
        log_file = Path(tmp_path, "log.txt")
        log_file.write_text("previous message\n", encoding="utf-8")

        info_count = None

        class MySpider(scrapy.Spider):
            name = "spider"
            custom_settings = {
                "LOG_LEVEL": "INFO",
                "LOG_FILE": str(log_file),
            }

            async def start(self):
                info_count_start = crawler.stats.get_value("log_count/INFO")
                logging.debug("debug message")  # noqa: LOG015
                logging.info("info message")  # noqa: LOG015
                logging.warning("warning message")  # noqa: LOG015
                logging.error("error message")  # noqa: LOG015
                nonlocal info_count
                info_count = (
                    crawler.stats.get_value("log_count/INFO") - info_count_start
                )
                return
                yield

        try:
            configure_logging()
            assert get_scrapy_root_handler().level == logging.DEBUG
            crawler = get_crawler(MySpider)
            assert get_scrapy_root_handler().level == logging.INFO
            await crawler.crawl_async()
        finally:
            _uninstall_scrapy_root_handler()

        logged = log_file.read_text(encoding="utf-8")

        assert "previous message" in logged
        assert "debug message" not in logged
        assert "info message" in logged
        assert "warning message" in logged
        assert "error message" in logged
        assert crawler.stats.get_value("log_count/ERROR") == 1
        assert crawler.stats.get_value("log_count/WARNING") == 1
        assert info_count == 1
        assert crawler.stats.get_value("log_count/DEBUG", 0) == 0

    def test_spider_custom_settings_log_append(self, tmp_path):
        log_file = Path(tmp_path, "log.txt")
        log_file.write_text("previous message\n", encoding="utf-8")

        class MySpider(scrapy.Spider):
            name = "spider"
            custom_settings = {
                "LOG_FILE": str(log_file),
                "LOG_FILE_APPEND": False,
            }

        try:
            configure_logging()
            get_crawler(MySpider)
            logging.debug("debug message")  # noqa: LOG015
        finally:
            _uninstall_scrapy_root_handler()

        logged = log_file.read_text(encoding="utf-8")

        assert "previous message" not in logged
        assert "debug message" in logged


class SpiderLoaderWithWrongInterface:
    def unneeded_method(self):
        pass


class TestCrawlerRunner(TestBaseCrawler):
    def test_spider_manager_verify_interface(self):
        settings = Settings(
            {
                "SPIDER_LOADER_CLASS": SpiderLoaderWithWrongInterface,
            }
        )
        with pytest.raises(MultipleInvalid):
            CrawlerRunner(settings)

    def test_crawler_runner_accepts_dict(self):
        runner = CrawlerRunner({"foo": "bar"})
        assert runner.settings["foo"] == "bar"
        self.assertOptionIsDefault(runner.settings, "RETRY_ENABLED")

    def test_crawler_runner_accepts_None(self):
        runner = CrawlerRunner()
        self.assertOptionIsDefault(runner.settings, "RETRY_ENABLED")


class TestAsyncCrawlerRunner(TestBaseCrawler):
    def test_spider_manager_verify_interface(self):
        settings = Settings(
            {
                "SPIDER_LOADER_CLASS": SpiderLoaderWithWrongInterface,
            }
        )
        with pytest.raises(MultipleInvalid):
            AsyncCrawlerRunner(settings)

    def test_crawler_runner_accepts_dict(self):
        runner = AsyncCrawlerRunner({"foo": "bar"})
        assert runner.settings["foo"] == "bar"
        self.assertOptionIsDefault(runner.settings, "RETRY_ENABLED")

    def test_crawler_runner_accepts_None(self):
        runner = AsyncCrawlerRunner()
        self.assertOptionIsDefault(runner.settings, "RETRY_ENABLED")


class TestCrawlerProcess(TestBaseCrawler):
    def test_crawler_process_accepts_dict(self):
        runner = CrawlerProcess({"foo": "bar"}, install_root_handler=False)
        assert runner.settings["foo"] == "bar"
        self.assertOptionIsDefault(runner.settings, "RETRY_ENABLED")

    def test_crawler_process_accepts_None(self):
        runner = CrawlerProcess(install_root_handler=False)
        self.assertOptionIsDefault(runner.settings, "RETRY_ENABLED")


@pytest.mark.only_asyncio
class TestAsyncCrawlerProcess(TestBaseCrawler):
    def test_crawler_process_accepts_dict(self, reactor_pytest: str) -> None:
        runner = AsyncCrawlerProcess(
            {"foo": "bar", "TWISTED_ENABLED": reactor_pytest != "none"},
            install_root_handler=False,
        )
        assert runner.settings["foo"] == "bar"
        self.assertOptionIsDefault(runner.settings, "RETRY_ENABLED")

    @pytest.mark.requires_reactor  # can't pass TWISTED_ENABLED=False
    def test_crawler_process_accepts_None(self) -> None:
        runner = AsyncCrawlerProcess(install_root_handler=False)
        self.assertOptionIsDefault(runner.settings, "RETRY_ENABLED")


class ExceptionSpider(scrapy.Spider):
    name = "exception"

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        raise ValueError("Exception in from_crawler method")


class NoRequestsSpider(scrapy.Spider):
    name = "no_request"

    async def start(self):
        return
        yield


@pytest.mark.requires_reactor  # CrawlerRunner requires a reactor
class TestCrawlerRunnerHasSpider:
    @staticmethod
    def _runner() -> CrawlerRunnerBase:
        return CrawlerRunner(get_reactor_settings())

    @staticmethod
    def _crawl(runner: CrawlerRunnerBase, spider: type[Spider]) -> Deferred[None]:
        return cast("Deferred[None]", runner.crawl(spider))

    @inline_callbacks_test
    def test_crawler_runner_bootstrap_successful(self):
        runner = self._runner()
        yield self._crawl(runner, NoRequestsSpider)
        assert not runner.bootstrap_failed

    @inline_callbacks_test
    def test_crawler_runner_bootstrap_successful_for_several(self):
        runner = self._runner()
        yield self._crawl(runner, NoRequestsSpider)
        yield self._crawl(runner, NoRequestsSpider)
        assert not runner.bootstrap_failed

    @inline_callbacks_test
    def test_crawler_runner_bootstrap_failed(self):
        runner = self._runner()

        try:
            yield self._crawl(runner, ExceptionSpider)
        except ValueError:
            pass
        else:
            pytest.fail("Exception should be raised from spider")

        assert runner.bootstrap_failed

    @inline_callbacks_test
    def test_crawler_runner_bootstrap_failed_for_several(self):
        runner = self._runner()

        try:
            yield self._crawl(runner, ExceptionSpider)
        except ValueError:
            pass
        else:
            pytest.fail("Exception should be raised from spider")

        yield self._crawl(runner, NoRequestsSpider)

        assert runner.bootstrap_failed

    @inline_callbacks_test
    def test_crawler_runner_asyncio_enabled_true(
        self, reactor_pytest: str
    ) -> Generator[Deferred[Any], Any, None]:
        if reactor_pytest != "asyncio":
            runner = CrawlerRunner(
                settings={
                    "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
                }
            )
            with pytest.raises(
                Exception,
                match=r"The installed reactor \(.*?\) does not match the requested one \(.*?\)",
            ):
                yield self._crawl(runner, NoRequestsSpider)
        else:
            CrawlerRunner(
                settings={
                    "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
                }
            )


@pytest.mark.only_asyncio
class TestAsyncCrawlerRunnerHasSpider(TestCrawlerRunnerHasSpider):
    @staticmethod
    def _runner() -> CrawlerRunnerBase:
        return AsyncCrawlerRunner(get_reactor_settings())

    @staticmethod
    def _crawl(runner: CrawlerRunnerBase, spider: type[Spider]) -> Deferred[None]:
        return deferred_from_coro(runner.crawl(spider))

    def test_crawler_runner_asyncio_enabled_true(self):
        pytest.skip("This test is only for CrawlerRunner")


@pytest.mark.parametrize(
    ("settings", "items"),
    [
        ({}, default_settings.LOG_VERSIONS),
        ({"LOG_VERSIONS": ["itemadapter"]}, ["itemadapter"]),
        ({"LOG_VERSIONS": []}, None),
    ],
)
def test_log_scrapy_info(settings, items, caplog):
    with caplog.at_level("INFO"):
        CrawlerProcess(settings, install_root_handler=False)
    assert (
        caplog.records[0].getMessage()
        == f"Scrapy {scrapy.__version__} started (bot: scrapybot)"
    ), repr(caplog.records[0].msg)
    if not items:
        assert len(caplog.records) == 1
        return
    version_string = caplog.records[1].getMessage()
    expected_items_pattern = "',\n '".join(
        f"{item}': '[^']+('\n +'[^']+)*" for item in items
    )
    assert re.search(r"^Versions:\n{'" + expected_items_pattern + "'}$", version_string)


@coroutine_test
async def test_deprecated_crawler_stop() -> None:
    crawler = get_crawler(DefaultSpider)
    d = crawler.crawl()
    await maybe_deferred_to_future(d)
    with pytest.warns(
        ScrapyDeprecationWarning, match=r"Crawler.stop\(\) is deprecated"
    ):
        await maybe_deferred_to_future(crawler.stop())
