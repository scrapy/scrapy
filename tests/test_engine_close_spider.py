from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest
from twisted.internet import defer

from scrapy import signals
from scrapy.core.engine import ExecutionEngine
from scrapy.statscollectors import MemoryStatsCollector
from scrapy.utils.spider import DefaultSpider
from scrapy.utils.test import get_crawler
from tests.utils.decorators import coroutine_test

if TYPE_CHECKING:
    from scrapy.core.scheduler import Scheduler
    from scrapy.crawler import Crawler


class TestEngineCloseSpider:
    """Tests for exception handling coverage during close_spider_async()."""

    @pytest.fixture
    def crawler(self) -> Crawler:
        crawler = get_crawler(DefaultSpider)
        crawler.spider = crawler._create_spider()
        return crawler

    @coroutine_test
    async def test_no_slot(self, crawler: Crawler) -> None:
        engine = ExecutionEngine(crawler, lambda _: None)
        crawler.engine = engine
        await engine.open_spider_async()
        slot = engine._slot
        engine._slot = None
        with pytest.raises(RuntimeError, match="Engine slot not assigned"):
            await engine.close_spider_async()
        # close it correctly
        engine._slot = slot
        await engine.close_spider_async()

    @coroutine_test
    async def test_no_spider(self, crawler: Crawler) -> None:
        engine = ExecutionEngine(crawler, lambda _: None)
        with pytest.raises(RuntimeError, match="Spider not opened"):
            await engine.close_spider_async()
        engine.downloader.close()  # cleanup

    @coroutine_test
    async def test_exception_slot(
        self, crawler: Crawler, caplog: pytest.LogCaptureFixture
    ) -> None:
        engine = ExecutionEngine(crawler, lambda _: None)
        crawler.engine = engine
        await engine.open_spider_async()
        assert engine._slot
        del engine._slot.heartbeat
        await engine.close_spider_async()
        assert "Slot close failure" in caplog.text

    @coroutine_test
    async def test_exception_downloader(
        self, crawler: Crawler, caplog: pytest.LogCaptureFixture
    ) -> None:
        engine = ExecutionEngine(crawler, lambda _: None)
        crawler.engine = engine
        await engine.open_spider_async()
        del engine.downloader.slots
        await engine.close_spider_async()
        assert "Downloader close failure" in caplog.text

    @coroutine_test
    async def test_exception_scraper(
        self, crawler: Crawler, caplog: pytest.LogCaptureFixture
    ) -> None:
        engine = ExecutionEngine(crawler, lambda _: None)
        crawler.engine = engine
        await engine.open_spider_async()
        engine.scraper.slot = None
        await engine.close_spider_async()
        assert "Scraper close failure" in caplog.text

    @coroutine_test
    async def test_exception_scheduler(
        self, crawler: Crawler, caplog: pytest.LogCaptureFixture
    ) -> None:
        engine = ExecutionEngine(crawler, lambda _: None)
        crawler.engine = engine
        await engine.open_spider_async()
        assert engine._slot
        del cast("Scheduler", engine._slot.scheduler).dqs
        await engine.close_spider_async()
        assert "Scheduler close failure" in caplog.text

    @coroutine_test
    async def test_exception_signal(
        self, crawler: Crawler, caplog: pytest.LogCaptureFixture
    ) -> None:
        engine = ExecutionEngine(crawler, lambda _: None)
        crawler.engine = engine
        await engine.open_spider_async()
        signal_manager = engine.signals
        del engine.signals
        await engine.close_spider_async()
        assert "Error while sending spider_close signal" in caplog.text
        # send the spider_closed signal to close various components
        await signal_manager.send_catch_log_async(
            signal=signals.spider_closed,
            spider=engine.spider,
            reason="cancelled",
        )

    @coroutine_test
    async def test_exception_stats(
        self, crawler: Crawler, caplog: pytest.LogCaptureFixture
    ) -> None:
        engine = ExecutionEngine(crawler, lambda _: None)
        crawler.engine = engine
        await engine.open_spider_async()
        assert isinstance(crawler.stats, MemoryStatsCollector)
        del crawler.stats.spider_stats
        await engine.close_spider_async()
        assert "Stats close failure" in caplog.text

    @coroutine_test
    async def test_exception_callback(
        self, crawler: Crawler, caplog: pytest.LogCaptureFixture
    ) -> None:
        engine = ExecutionEngine(crawler, lambda _: defer.fail(ValueError()))
        crawler.engine = engine
        await engine.open_spider_async()
        await engine.close_spider_async()
        assert "Error running spider_closed_callback" in caplog.text

    @coroutine_test
    async def test_exception_async_callback(
        self, crawler: Crawler, caplog: pytest.LogCaptureFixture
    ) -> None:
        async def cb(_):
            raise ValueError

        engine = ExecutionEngine(crawler, cb)
        crawler.engine = engine
        await engine.open_spider_async()
        await engine.close_spider_async()
        assert "Error running spider_closed_callback" in caplog.text
