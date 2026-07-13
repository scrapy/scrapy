from __future__ import annotations

import asyncio
import logging
import re
import signal
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar
from unittest.mock import MagicMock

import pytest
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
from scrapy.utils.defer import ensure_awaitable, maybe_deferred_to_future
from scrapy.utils.log import (
    _uninstall_scrapy_root_handler,
    configure_logging,
    get_scrapy_root_handler,
)
from scrapy.utils.spider import DefaultSpider
from scrapy.utils.test import get_crawler, get_reactor_settings
from tests.spiders import ExceptionSpider, NoRequestsSpider
from tests.utils.decorators import coroutine_test

if TYPE_CHECKING:
    from collections.abc import Callable

BASE_SETTINGS: dict[str, Any] = {}


def get_raw_crawler(
    spidercls: type[Spider] | None = None, settings_dict: dict[str, Any] | None = None
) -> Crawler:
    """get_crawler alternative that only calls the __init__ method of the
    crawler."""
    settings = Settings()
    settings.setdict(get_reactor_settings())
    settings.setdict(settings_dict or {})
    return Crawler(spidercls or DefaultSpider, settings)


class TestBaseCrawler:
    @staticmethod
    def assertOptionIsDefault(settings: Settings, key: str) -> None:
        assert isinstance(settings, Settings)
        assert settings[key] == getattr(default_settings, key)


class TestCrawler(TestBaseCrawler):
    def test_populate_spidercls_settings(self) -> None:
        spider_settings: dict[str, Any] = {
            "TEST1": "spider",
            "TEST2": "spider",
        }
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

    def test_crawler_accepts_dict(self) -> None:
        crawler = get_crawler(DefaultSpider, {"foo": "bar"})
        assert crawler.settings["foo"] == "bar"
        self.assertOptionIsDefault(crawler.settings, "RETRY_ENABLED")

    def test_crawler_accepts_None(self) -> None:
        crawler = Crawler(DefaultSpider)
        self.assertOptionIsDefault(crawler.settings, "RETRY_ENABLED")

    def test_crawler_rejects_spider_objects(self) -> None:
        with pytest.raises(ValueError, match="spidercls argument must be a class"):
            Crawler(DefaultSpider())  # type: ignore[arg-type]

    @coroutine_test
    async def test_crawler_crawl_twice_seq_unsupported(self) -> None:
        crawler = get_raw_crawler(NoRequestsSpider, BASE_SETTINGS)
        await maybe_deferred_to_future(crawler.crawl())
        with pytest.raises(RuntimeError, match="more than once on the same instance"):
            await maybe_deferred_to_future(crawler.crawl())

    @coroutine_test
    async def test_crawler_crawl_async_twice_seq_unsupported(self) -> None:
        crawler = get_raw_crawler(NoRequestsSpider, BASE_SETTINGS)
        await crawler.crawl_async()
        with pytest.raises(RuntimeError, match="more than once on the same instance"):
            await crawler.crawl_async()

    @coroutine_test
    async def test_crawler_crawl_twice_parallel_unsupported(self) -> None:
        crawler = get_raw_crawler(NoRequestsSpider, BASE_SETTINGS)
        d1 = crawler.crawl()
        d2 = crawler.crawl()
        await maybe_deferred_to_future(d1)
        with pytest.raises(RuntimeError, match="Crawling already taking place"):
            await maybe_deferred_to_future(d2)

    @pytest.mark.only_asyncio
    @coroutine_test
    async def test_crawler_crawl_async_twice_parallel_unsupported(self) -> None:
        crawler = get_raw_crawler(NoRequestsSpider, BASE_SETTINGS)
        t1 = asyncio.create_task(crawler.crawl_async())
        t2 = asyncio.create_task(crawler.crawl_async())
        await t1
        with pytest.raises(RuntimeError, match="Crawling already taking place"):
            await t2

    def test_get_addon(self) -> None:
        class ParentAddon:
            pass

        class TrackingAddon(ParentAddon):
            instances: ClassVar[list[TrackingAddon]] = []

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

        addon = crawler.get_addon(DefaultSpider)  # type: ignore[assignment]
        assert addon is None

        addon = crawler.get_addon(ParentAddon)
        assert addon == expected

        class ChildAddon(TrackingAddon):
            pass

        addon = crawler.get_addon(ChildAddon)
        assert addon is None

    @coroutine_test
    async def test_get_downloader_middleware(self) -> None:
        class ParentDownloaderMiddleware:
            pass

        class TrackingDownloaderMiddleware(ParentDownloaderMiddleware):
            instances: ClassVar[list[TrackingDownloaderMiddleware]] = []

            def __init__(self):
                TrackingDownloaderMiddleware.instances.append(self)

        class MySpider(Spider):
            name = "myspider"
            cls: ClassVar[type[Any]]
            result: ClassVar[Any]

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
        await crawler.crawl_async()
        assert len(TrackingDownloaderMiddleware.instances) == 1
        assert MySpider.result == TrackingDownloaderMiddleware.instances[-1]

        crawler = get_raw_crawler(MySpider, settings)
        MySpider.cls = DefaultSpider
        await crawler.crawl_async()
        assert MySpider.result is None

        crawler = get_raw_crawler(MySpider, settings)
        MySpider.cls = ParentDownloaderMiddleware
        await crawler.crawl_async()
        assert MySpider.result == TrackingDownloaderMiddleware.instances[-1]

        class ChildDownloaderMiddleware(TrackingDownloaderMiddleware):
            pass

        crawler = get_raw_crawler(MySpider, settings)
        MySpider.cls = ChildDownloaderMiddleware
        await crawler.crawl_async()
        assert MySpider.result is None

    def test_get_downloader_middleware_not_crawling(self) -> None:
        crawler = get_raw_crawler(settings_dict=BASE_SETTINGS)
        with pytest.raises(RuntimeError):
            crawler.get_downloader_middleware(DefaultSpider)

    @coroutine_test
    async def test_get_downloader_middleware_no_engine(self) -> None:
        class MySpider(Spider):
            name = "myspider"

            @classmethod
            def from_crawler(cls, crawler):
                crawler.get_downloader_middleware(DefaultSpider)

        crawler = get_raw_crawler(MySpider, BASE_SETTINGS)
        with pytest.raises(RuntimeError):
            await crawler.crawl_async()

    @coroutine_test
    async def test_get_extension(self) -> None:
        class ParentExtension:
            pass

        class TrackingExtension(ParentExtension):
            instances: ClassVar[list[TrackingExtension]] = []

            def __init__(self):
                TrackingExtension.instances.append(self)

        class MySpider(Spider):
            name = "myspider"
            cls: ClassVar[type[Any]]
            result: ClassVar[Any]

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
        await crawler.crawl_async()
        assert len(TrackingExtension.instances) == 1
        assert MySpider.result == TrackingExtension.instances[-1]

        crawler = get_raw_crawler(MySpider, settings)
        MySpider.cls = DefaultSpider
        await crawler.crawl_async()
        assert MySpider.result is None

        crawler = get_raw_crawler(MySpider, settings)
        MySpider.cls = ParentExtension
        await crawler.crawl_async()
        assert MySpider.result == TrackingExtension.instances[-1]

        class ChildExtension(TrackingExtension):
            pass

        crawler = get_raw_crawler(MySpider, settings)
        MySpider.cls = ChildExtension
        await crawler.crawl_async()
        assert MySpider.result is None

    def test_get_extension_not_crawling(self) -> None:
        crawler = get_raw_crawler(settings_dict=BASE_SETTINGS)
        with pytest.raises(RuntimeError):
            crawler.get_extension(DefaultSpider)

    @coroutine_test
    async def test_get_extension_no_engine(self) -> None:
        class MySpider(Spider):
            name = "myspider"

            @classmethod
            def from_crawler(cls, crawler):
                crawler.get_extension(DefaultSpider)

        crawler = get_raw_crawler(MySpider, BASE_SETTINGS)
        with pytest.raises(RuntimeError):
            await crawler.crawl_async()

    @coroutine_test
    async def test_get_item_pipeline(self) -> None:
        class ParentItemPipeline:
            pass

        class TrackingItemPipeline(ParentItemPipeline):
            instances: ClassVar[list[TrackingItemPipeline]] = []

            def __init__(self):
                TrackingItemPipeline.instances.append(self)

        class MySpider(Spider):
            name = "myspider"
            cls: ClassVar[type[Any]]
            result: ClassVar[Any]

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
        await crawler.crawl_async()
        assert len(TrackingItemPipeline.instances) == 1
        assert MySpider.result == TrackingItemPipeline.instances[-1]

        crawler = get_raw_crawler(MySpider, settings)
        MySpider.cls = DefaultSpider
        await crawler.crawl_async()
        assert MySpider.result is None

        crawler = get_raw_crawler(MySpider, settings)
        MySpider.cls = ParentItemPipeline
        await crawler.crawl_async()
        assert MySpider.result == TrackingItemPipeline.instances[-1]

        class ChildItemPipeline(TrackingItemPipeline):
            pass

        crawler = get_raw_crawler(MySpider, settings)
        MySpider.cls = ChildItemPipeline
        await crawler.crawl_async()
        assert MySpider.result is None

    def test_get_item_pipeline_not_crawling(self) -> None:
        crawler = get_raw_crawler(settings_dict=BASE_SETTINGS)
        with pytest.raises(RuntimeError):
            crawler.get_item_pipeline(DefaultSpider)

    @coroutine_test
    async def test_get_item_pipeline_no_engine(self) -> None:
        class MySpider(Spider):
            name = "myspider"

            @classmethod
            def from_crawler(cls, crawler):
                crawler.get_item_pipeline(DefaultSpider)

        crawler = get_raw_crawler(MySpider, BASE_SETTINGS)
        with pytest.raises(RuntimeError):
            await crawler.crawl_async()

    @coroutine_test
    async def test_get_spider_middleware(self) -> None:
        class ParentSpiderMiddleware:
            pass

        class TrackingSpiderMiddleware(ParentSpiderMiddleware):
            instances: ClassVar[list[TrackingSpiderMiddleware]] = []

            def __init__(self):
                TrackingSpiderMiddleware.instances.append(self)

        class MySpider(Spider):
            name = "myspider"
            cls: ClassVar[type[Any]]
            result: ClassVar[Any]

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
        await crawler.crawl_async()
        assert len(TrackingSpiderMiddleware.instances) == 1
        assert MySpider.result == TrackingSpiderMiddleware.instances[-1]

        crawler = get_raw_crawler(MySpider, settings)
        MySpider.cls = DefaultSpider
        await crawler.crawl_async()
        assert MySpider.result is None

        crawler = get_raw_crawler(MySpider, settings)
        MySpider.cls = ParentSpiderMiddleware
        await crawler.crawl_async()
        assert MySpider.result == TrackingSpiderMiddleware.instances[-1]

        class ChildSpiderMiddleware(TrackingSpiderMiddleware):
            pass

        crawler = get_raw_crawler(MySpider, settings)
        MySpider.cls = ChildSpiderMiddleware
        await crawler.crawl_async()
        assert MySpider.result is None

    def test_get_spider_middleware_not_crawling(self) -> None:
        crawler = get_raw_crawler(settings_dict=BASE_SETTINGS)
        with pytest.raises(RuntimeError):
            crawler.get_spider_middleware(DefaultSpider)

    @coroutine_test
    async def test_get_spider_middleware_no_engine(self) -> None:
        class MySpider(Spider):
            name = "myspider"

            @classmethod
            def from_crawler(cls, crawler):
                crawler.get_spider_middleware(DefaultSpider)

        crawler = get_raw_crawler(MySpider, BASE_SETTINGS)
        with pytest.raises(RuntimeError):
            await crawler.crawl_async()


class TestSpiderSettings:
    def test_spider_custom_settings(self) -> None:
        class MySpider(scrapy.Spider):
            name = "spider"
            custom_settings = {"AUTOTHROTTLE_ENABLED": True}

        crawler = get_crawler(MySpider)
        assert crawler.extensions
        enabled_exts = [e.__class__ for e in crawler.extensions.middlewares]
        assert AutoThrottle in enabled_exts


class TestCrawlerLogging:
    def test_no_root_handler_installed(self) -> None:
        handler = get_scrapy_root_handler()
        if handler is not None:
            logging.root.removeHandler(handler)

        class MySpider(scrapy.Spider):
            name = "spider"

        get_crawler(MySpider)
        assert get_scrapy_root_handler() is None

    @coroutine_test
    async def test_spider_custom_settings_log_level(self, tmp_path: Path) -> None:
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
                assert crawler.stats
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
            handler = get_scrapy_root_handler()
            assert handler is not None
            assert handler.level == logging.DEBUG
            crawler = get_crawler(MySpider)
            handler = get_scrapy_root_handler()
            assert handler is not None
            assert handler.level == logging.INFO
            await crawler.crawl_async()
        finally:
            _uninstall_scrapy_root_handler()

        logged = log_file.read_text(encoding="utf-8")

        assert "previous message" in logged
        assert "debug message" not in logged
        assert "info message" in logged
        assert "warning message" in logged
        assert "error message" in logged
        assert crawler.stats
        assert crawler.stats.get_value("log_count/ERROR") == 1
        assert crawler.stats.get_value("log_count/WARNING") == 1
        assert info_count == 1
        assert crawler.stats.get_value("log_count/DEBUG", 0) == 0

    def test_spider_custom_settings_log_append(self, tmp_path: Path) -> None:
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
    def unneeded_method(self) -> None:
        pass


class TestCrawlerRunner(TestBaseCrawler):
    def test_spider_manager_verify_interface(self) -> None:
        settings = Settings(
            {
                "SPIDER_LOADER_CLASS": SpiderLoaderWithWrongInterface,
            }
        )
        with pytest.raises(MultipleInvalid):
            CrawlerRunner(settings)

    def test_crawler_runner_accepts_dict(self) -> None:
        runner = CrawlerRunner({"foo": "bar"})
        assert runner.settings["foo"] == "bar"
        self.assertOptionIsDefault(runner.settings, "RETRY_ENABLED")

    def test_crawler_runner_accepts_None(self) -> None:
        runner = CrawlerRunner()
        self.assertOptionIsDefault(runner.settings, "RETRY_ENABLED")


class TestAsyncCrawlerRunner(TestBaseCrawler):
    def test_spider_manager_verify_interface(self) -> None:
        settings = Settings(
            {
                "SPIDER_LOADER_CLASS": SpiderLoaderWithWrongInterface,
            }
        )
        with pytest.raises(MultipleInvalid):
            AsyncCrawlerRunner(settings)

    def test_crawler_runner_accepts_dict(self) -> None:
        runner = AsyncCrawlerRunner({"foo": "bar"})
        assert runner.settings["foo"] == "bar"
        self.assertOptionIsDefault(runner.settings, "RETRY_ENABLED")

    def test_crawler_runner_accepts_None(self) -> None:
        runner = AsyncCrawlerRunner()
        self.assertOptionIsDefault(runner.settings, "RETRY_ENABLED")


class TestCrawlerProcess(TestBaseCrawler):
    def test_crawler_process_accepts_dict(self) -> None:
        runner = CrawlerProcess({"foo": "bar"}, install_root_handler=False)
        assert runner.settings["foo"] == "bar"
        self.assertOptionIsDefault(runner.settings, "RETRY_ENABLED")

    def test_crawler_process_accepts_None(self) -> None:
        runner = CrawlerProcess(install_root_handler=False)
        self.assertOptionIsDefault(runner.settings, "RETRY_ENABLED")


@pytest.mark.only_asyncio
class TestAsyncCrawlerProcess(TestBaseCrawler):
    def test_crawler_process_accepts_dict(self, reactor_pytest: str) -> None:
        runner = AsyncCrawlerProcess(
            {"foo": "bar", "TWISTED_REACTOR_ENABLED": reactor_pytest != "none"},
            install_root_handler=False,
        )
        assert runner.settings["foo"] == "bar"
        self.assertOptionIsDefault(runner.settings, "RETRY_ENABLED")

    @pytest.mark.requires_reactor  # can't pass TWISTED_REACTOR_ENABLED=False
    def test_crawler_process_accepts_None(self) -> None:
        runner = AsyncCrawlerProcess(install_root_handler=False)
        self.assertOptionIsDefault(runner.settings, "RETRY_ENABLED")


class TestAsyncCrawlerProcessReactorlessHelpers:
    """Unit tests for the reactorless shutdown helpers of AsyncCrawlerProcess.

    These cover defensive branches that guard against shutdown races and that
    are not reachable through a full process run.
    """

    @staticmethod
    def _bare_process(
        monkeypatch: pytest.MonkeyPatch,
    ) -> tuple[AsyncCrawlerProcess, list[Any]]:
        # AsyncCrawlerProcess.__init__ has global side effects (it installs a
        # reactor import hook and an asyncio event loop), so build a bare
        # instance and set only the attributes these helpers read. The shutdown
        # handlers installed by these helpers are recorded for assertions
        # instead of touching the real process-wide signal handlers.
        installed_handlers: list[Any] = []
        monkeypatch.setattr(
            "scrapy.crawler.install_shutdown_handlers",
            lambda handler, *args, **kwargs: installed_handlers.append(handler),
        )
        return AsyncCrawlerProcess.__new__(AsyncCrawlerProcess), installed_handlers

    @staticmethod
    def _run_in_thread(target: Callable[[], None]) -> None:
        # Run target in a dedicated thread so its event loop is not nested
        # inside the event loop that may already be running the test session.
        thread = threading.Thread(target=target)
        thread.start()
        thread.join()

    def test_signal_shutdown_reactorless_without_loop(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        process, installed_handlers = self._bare_process(monkeypatch)
        process._reactorless_loop = None
        # No loop to schedule the shutdown task on, so it returns early, but it
        # must still escalate the handler so a second signal forces a kill.
        process._signal_shutdown_reactorless(signal.SIGINT, None)
        assert installed_handlers == [process._signal_kill_reactorless]

    def test_signal_kill_reactorless_without_loop(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        process, installed_handlers = self._bare_process(monkeypatch)
        process._reactorless_loop = None
        process._reactorless_main_task = None
        # No loop to cancel the main task on, so it returns early, but it must
        # still ignore any further signals.
        process._signal_kill_reactorless(signal.SIGINT, None)
        assert installed_handlers == [signal.SIG_IGN]

    def test_signal_kill_reactorless_without_main_task(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        process, installed_handlers = self._bare_process(monkeypatch)
        loop = MagicMock()
        process._reactorless_loop = loop
        process._reactorless_main_task = None
        # No main task to cancel, so nothing is scheduled on the loop.
        process._signal_kill_reactorless(signal.SIGINT, None)
        assert installed_handlers == [signal.SIG_IGN]
        loop.call_soon_threadsafe.assert_not_called()

    def test_shutdown_graceful_reactorless_main_task_already_done(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        process, _ = self._bare_process(monkeypatch)
        process._stop_after_crawl = False

        async def noop() -> None:
            return None

        monkeypatch.setattr(process, "stop", noop)
        monkeypatch.setattr(process, "join", noop)

        def run() -> None:
            loop = asyncio.new_event_loop()
            try:
                main_task: asyncio.Future[None] = loop.create_future()
                main_task.set_result(None)
                process._reactorless_main_task = main_task
                # The main task is already done, so it is not cancelled.
                loop.run_until_complete(process._shutdown_graceful_reactorless())
                assert not main_task.cancelled()
            finally:
                loop.close()

        self._run_in_thread(run)

    def test_create_shutdown_task_closed_loop(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        process, _ = self._bare_process(monkeypatch)
        loop = asyncio.new_event_loop()
        loop.close()
        process._reactorless_loop = loop
        process._stop_after_crawl = True
        # create_task() raises RuntimeError on a closed loop; the coroutine
        # must be closed instead of leaking.
        process._create_shutdown_task()

    def test_cancel_all_tasks_logs_task_exception(self) -> None:
        contexts: list[dict[str, Any]] = []
        task_was_cancelled: list[bool] = []

        def run() -> None:
            loop = asyncio.new_event_loop()
            loop.set_exception_handler(lambda _loop, context: contexts.append(context))

            async def fail_on_cancel() -> None:
                try:
                    await asyncio.sleep(10)
                except asyncio.CancelledError:
                    raise RuntimeError("boom")

            try:
                task = loop.create_task(fail_on_cancel())
                # Let the task start and suspend on the sleep so the
                # cancellation is raised inside its body and turned into a
                # RuntimeError rather than cancelling the task cleanly.
                loop.run_until_complete(asyncio.sleep(0))
                AsyncCrawlerProcess._cancel_all_tasks(loop)
                task_was_cancelled.append(task.cancelled())
            finally:
                loop.close()

        self._run_in_thread(run)

        # The task raised instead of being cancelled, so its exception is
        # reported to the loop exception handler.
        assert task_was_cancelled == [False]
        assert any(
            context.get("message")
            == "unhandled exception during AsyncCrawlerProcess shutdown"
            for context in contexts
        )


@pytest.mark.parametrize("runner_cls", [AsyncCrawlerRunner, CrawlerRunner])
def test_runner_settings_applied_to_crawler_instance(
    runner_cls: type[CrawlerRunnerBase],
) -> None:
    runner = runner_cls({"FOO": "runner"})
    crawler = Crawler(DefaultSpider)
    result = runner.create_crawler(crawler)
    assert result is crawler
    assert result.settings["FOO"] == "runner"


@pytest.mark.parametrize("runner_cls", [AsyncCrawlerRunner, CrawlerRunner])
def test_spider_custom_settings_override_runner(
    runner_cls: type[CrawlerRunnerBase],
) -> None:
    class MySpider(DefaultSpider):
        custom_settings = {"FOO": "spider"}

    runner = runner_cls({"FOO": "runner"})
    crawler = Crawler(MySpider)
    runner.create_crawler(crawler)
    assert crawler.settings["FOO"] == "spider"


def test_create_crawler_instance_consistent_with_spider_class() -> None:
    runner = AsyncCrawlerRunner({"FOO": "runner"})

    crawler_from_class = runner.create_crawler(DefaultSpider)

    pre_built = Crawler(DefaultSpider)
    runner.create_crawler(pre_built)

    assert crawler_from_class.settings["FOO"] == "runner"
    assert pre_built.settings["FOO"] == "runner"


@pytest.mark.parametrize("runner_cls", [AsyncCrawlerRunner, CrawlerRunner])
def test_create_crawler_rejects_spider_object(
    runner_cls: type[CrawlerRunnerBase],
) -> None:
    runner = runner_cls()
    with pytest.raises(ValueError, match="cannot be a spider object"):
        runner.create_crawler(DefaultSpider())  # type: ignore[arg-type]


@pytest.mark.parametrize("runner_cls", [AsyncCrawlerRunner, CrawlerRunner])
def test_crawl_rejects_spider_object(runner_cls: type[CrawlerRunnerBase]) -> None:
    runner = runner_cls()
    with pytest.raises(ValueError, match="cannot be a spider object"):
        runner.crawl(DefaultSpider())  # type: ignore[arg-type]


@pytest.mark.requires_reactor  # CrawlerRunner requires a reactor
class TestCrawlerRunnerHasSpider:
    @pytest.fixture
    def runner(self) -> CrawlerRunnerBase:
        return CrawlerRunner(get_reactor_settings())

    @staticmethod
    async def _crawl(runner: CrawlerRunnerBase, spider: type[Spider]) -> None:
        await ensure_awaitable(runner.crawl(spider))

    @coroutine_test
    async def test_crawler_runner_bootstrap_successful(
        self, runner: CrawlerRunnerBase
    ) -> None:
        await self._crawl(runner, NoRequestsSpider)
        assert not runner.bootstrap_failed

    @coroutine_test
    async def test_crawler_runner_bootstrap_successful_for_several(
        self, runner: CrawlerRunnerBase
    ) -> None:
        await self._crawl(runner, NoRequestsSpider)
        await self._crawl(runner, NoRequestsSpider)
        assert not runner.bootstrap_failed

    @coroutine_test
    async def test_crawler_runner_bootstrap_failed(
        self, runner: CrawlerRunnerBase
    ) -> None:
        try:
            await self._crawl(runner, ExceptionSpider)
        except ValueError:
            pass
        else:
            pytest.fail("Exception should be raised from spider")

        assert runner.bootstrap_failed

    @coroutine_test
    async def test_crawler_runner_bootstrap_failed_for_several(
        self, runner: CrawlerRunnerBase
    ) -> None:
        try:
            await self._crawl(runner, ExceptionSpider)
        except ValueError:
            pass
        else:
            pytest.fail("Exception should be raised from spider")

        await self._crawl(runner, NoRequestsSpider)

        assert runner.bootstrap_failed

    @coroutine_test
    async def test_crawler_runner_asyncio_enabled_true(
        self, reactor_pytest: str
    ) -> None:
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
                await self._crawl(runner, NoRequestsSpider)
        else:
            runner = CrawlerRunner(
                settings={
                    "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
                }
            )
            await self._crawl(runner, NoRequestsSpider)


@pytest.mark.only_asyncio
class TestAsyncCrawlerRunnerHasSpider(TestCrawlerRunnerHasSpider):
    @pytest.fixture
    def runner(self) -> CrawlerRunnerBase:
        return AsyncCrawlerRunner(get_reactor_settings())

    def test_crawler_runner_asyncio_enabled_true(self) -> None:  # type: ignore[override]
        pytest.skip("This test is only for CrawlerRunner")


@pytest.mark.parametrize(
    ("settings", "items"),
    [
        ({}, default_settings.LOG_VERSIONS),
        ({"LOG_VERSIONS": ["itemadapter"]}, ["itemadapter"]),
        ({"LOG_VERSIONS": []}, None),
    ],
)
def test_log_scrapy_info(
    settings: dict[str, Any], items: list[str] | None, caplog: pytest.LogCaptureFixture
) -> None:
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
