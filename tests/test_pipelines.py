import asyncio

import pytest
from twisted.internet.defer import Deferred, inlineCallbacks, succeed

from scrapy import Request, Spider, signals
from scrapy.crawler import Crawler
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.pipelines import ItemPipelineManager
from scrapy.utils.asyncio import call_later
from scrapy.utils.conf import build_component_list
from scrapy.utils.defer import (
    deferred_f_from_coro_f,
    deferred_to_future,
    maybe_deferred_to_future,
)
from scrapy.utils.spider import DefaultSpider
from scrapy.utils.test import get_crawler, get_from_asyncio_queue
from tests.mockserver.http import MockServer


class SimplePipeline:
    def process_item(self, item):
        item["pipeline_passed"] = True
        return item


class DeprecatedSpiderArgPipeline:
    def open_spider(self, spider):
        pass

    def close_spider(self, spider):
        pass

    def process_item(self, item, spider):
        item["pipeline_passed"] = True
        return item


class DeferredPipeline:
    def cb(self, item):
        item["pipeline_passed"] = True
        return item

    def process_item(self, item):
        d = Deferred()
        d.addCallback(self.cb)
        d.callback(item)
        return d


class AsyncDefPipeline:
    async def process_item(self, item):
        d = Deferred()
        call_later(0, d.callback, None)
        await maybe_deferred_to_future(d)
        item["pipeline_passed"] = True
        return item


class AsyncDefAsyncioPipeline:
    async def process_item(self, item):
        d = Deferred()
        loop = asyncio.get_event_loop()
        loop.call_later(0, d.callback, None)
        await deferred_to_future(d)
        await asyncio.sleep(0.2)
        item["pipeline_passed"] = await get_from_asyncio_queue(True)
        return item


class AsyncDefNotAsyncioPipeline:
    async def process_item(self, item):
        d1 = Deferred()
        from twisted.internet import reactor

        reactor.callLater(0, d1.callback, None)
        await d1
        d2 = Deferred()
        reactor.callLater(0, d2.callback, None)
        await maybe_deferred_to_future(d2)
        item["pipeline_passed"] = True
        return item


class ItemSpider(Spider):
    name = "itemspider"

    async def start(self):
        yield Request(self.mockserver.url("/status?n=200"))

    def parse(self, response):
        return {"field": 42}


class TestPipeline:
    @classmethod
    def setup_class(cls):
        cls.mockserver = MockServer()
        cls.mockserver.__enter__()

    @classmethod
    def teardown_class(cls):
        cls.mockserver.__exit__(None, None, None)

    def _on_item_scraped(self, item):
        assert isinstance(item, dict)
        assert item.get("pipeline_passed")
        self.items.append(item)

    def _create_crawler(self, pipeline_class):
        settings = {
            "ITEM_PIPELINES": {pipeline_class: 1},
        }
        crawler = get_crawler(ItemSpider, settings)
        crawler.signals.connect(self._on_item_scraped, signals.item_scraped)
        self.items = []
        return crawler

    @inlineCallbacks
    def test_simple_pipeline(self):
        crawler = self._create_crawler(SimplePipeline)
        yield crawler.crawl(mockserver=self.mockserver)
        assert len(self.items) == 1

    @inlineCallbacks
    def test_deferred_pipeline(self):
        crawler = self._create_crawler(DeferredPipeline)
        yield crawler.crawl(mockserver=self.mockserver)
        assert len(self.items) == 1

    @inlineCallbacks
    def test_asyncdef_pipeline(self):
        crawler = self._create_crawler(AsyncDefPipeline)
        yield crawler.crawl(mockserver=self.mockserver)
        assert len(self.items) == 1

    @pytest.mark.only_asyncio
    @inlineCallbacks
    def test_asyncdef_asyncio_pipeline(self):
        crawler = self._create_crawler(AsyncDefAsyncioPipeline)
        yield crawler.crawl(mockserver=self.mockserver)
        assert len(self.items) == 1

    @pytest.mark.only_not_asyncio
    @inlineCallbacks
    def test_asyncdef_not_asyncio_pipeline(self):
        crawler = self._create_crawler(AsyncDefNotAsyncioPipeline)
        yield crawler.crawl(mockserver=self.mockserver)
        assert len(self.items) == 1

    @deferred_f_from_coro_f
    async def test_deprecated_spider_arg(self, mockserver: MockServer) -> None:
        crawler = self._create_crawler(DeprecatedSpiderArgPipeline)
        with (
            pytest.warns(
                ScrapyDeprecationWarning,
                match=r"DeprecatedSpiderArgPipeline.open_spider\(\) requires a spider argument",
            ),
            pytest.warns(
                ScrapyDeprecationWarning,
                match=r"DeprecatedSpiderArgPipeline.close_spider\(\) requires a spider argument",
            ),
            pytest.warns(
                ScrapyDeprecationWarning,
                match=r"DeprecatedSpiderArgPipeline.process_item\(\) requires a spider argument",
            ),
        ):
            await maybe_deferred_to_future(crawler.crawl(mockserver=mockserver))

        assert len(self.items) == 1


class TestCustomPipelineManager:
    def test_deprecated_process_item_spider_arg(self) -> None:
        class CustomPipelineManager(ItemPipelineManager):
            def process_item(self, item, spider):  # pylint: disable=useless-parent-delegation
                return super().process_item(item, spider)

        crawler = get_crawler(DefaultSpider)
        crawler.spider = crawler._create_spider()
        itemproc = CustomPipelineManager.from_crawler(crawler)
        with pytest.warns(
            ScrapyDeprecationWarning,
            match=r"CustomPipelineManager.process_item\(\) is deprecated, use process_item_async\(\)",
        ):
            itemproc.process_item({}, crawler.spider)

    @deferred_f_from_coro_f
    async def test_integration_recommended(self, mockserver: MockServer) -> None:
        class CustomPipelineManager(ItemPipelineManager):
            async def process_item_async(self, item):
                return await super().process_item_async(item)

        items = []

        def _on_item_scraped(item):
            assert isinstance(item, dict)
            assert item.get("pipeline_passed")
            items.append(item)

        crawler = get_crawler(
            ItemSpider,
            {
                "ITEM_PROCESSOR": CustomPipelineManager,
                "ITEM_PIPELINES": {SimplePipeline: 1},
            },
        )
        crawler.spider = crawler._create_spider()
        crawler.signals.connect(_on_item_scraped, signals.item_scraped)
        await maybe_deferred_to_future(crawler.crawl(mockserver=mockserver))

        assert len(items) == 1

    @deferred_f_from_coro_f
    async def test_integration_no_async_subclass(self, mockserver: MockServer) -> None:
        class CustomPipelineManager(ItemPipelineManager):
            def open_spider(self, spider):
                with pytest.warns(
                    ScrapyDeprecationWarning,
                    match=r"CustomPipelineManager.open_spider\(\) is deprecated, use open_spider_async\(\)",
                ):
                    return super().open_spider(spider)

            def close_spider(self, spider):
                with pytest.warns(
                    ScrapyDeprecationWarning,
                    match=r"CustomPipelineManager.close_spider\(\) is deprecated, use close_spider_async\(\)",
                ):
                    return super().close_spider(spider)

            def process_item(self, item, spider):
                with pytest.warns(
                    ScrapyDeprecationWarning,
                    match=r"CustomPipelineManager.process_item\(\) is deprecated, use process_item_async\(\)",
                ):
                    return super().process_item(item, spider)

        items = []

        def _on_item_scraped(item):
            assert isinstance(item, dict)
            assert item.get("pipeline_passed")
            items.append(item)

        crawler = get_crawler(
            ItemSpider,
            {
                "ITEM_PROCESSOR": CustomPipelineManager,
                "ITEM_PIPELINES": {SimplePipeline: 1},
            },
        )
        crawler.spider = crawler._create_spider()
        crawler.signals.connect(_on_item_scraped, signals.item_scraped)
        with (
            pytest.warns(
                ScrapyDeprecationWarning,
                match=r"CustomPipelineManager overrides open_spider\(\) but doesn't override open_spider_async\(\)",
            ),
            pytest.warns(
                ScrapyDeprecationWarning,
                match=r"CustomPipelineManager overrides close_spider\(\) but doesn't override close_spider_async\(\)",
            ),
            pytest.warns(
                ScrapyDeprecationWarning,
                match=r"CustomPipelineManager overrides process_item\(\) but doesn't override process_item_async\(\)",
            ),
        ):
            await maybe_deferred_to_future(crawler.crawl(mockserver=mockserver))

        assert len(items) == 1

    @deferred_f_from_coro_f
    async def test_integration_no_async_not_subclass(
        self, mockserver: MockServer
    ) -> None:
        class CustomPipelineManager:
            def __init__(self, crawler):
                self.pipelines = [
                    p()
                    for p in build_component_list(
                        crawler.settings.getwithbase("ITEM_PIPELINES")
                    )
                ]

            @classmethod
            def from_crawler(cls, crawler):
                return cls(crawler)

            def open_spider(self, spider):
                return succeed(None)

            def close_spider(self, spider):
                return succeed(None)

            def process_item(self, item, spider):
                for pipeline in self.pipelines:
                    item = pipeline.process_item(item)
                return succeed(item)

        items = []

        def _on_item_scraped(item):
            assert isinstance(item, dict)
            assert item.get("pipeline_passed")
            items.append(item)

        crawler = get_crawler(
            ItemSpider,
            {
                "ITEM_PROCESSOR": CustomPipelineManager,
                "ITEM_PIPELINES": {SimplePipeline: 1},
            },
        )
        crawler.spider = crawler._create_spider()
        crawler.signals.connect(_on_item_scraped, signals.item_scraped)
        with (
            pytest.warns(
                ScrapyDeprecationWarning,
                match=r"CustomPipelineManager doesn't define a open_spider_async\(\) method",
            ),
            pytest.warns(
                ScrapyDeprecationWarning,
                match=r"CustomPipelineManager doesn't define a close_spider_async\(\) method",
            ),
            pytest.warns(
                ScrapyDeprecationWarning,
                match=r"CustomPipelineManager doesn't define a process_item_async\(\) method",
            ),
        ):
            await maybe_deferred_to_future(crawler.crawl(mockserver=mockserver))

        assert len(items) == 1


class TestMiddlewareManagerSpider:
    """Tests for the deprecated spider arg handling in MiddlewareManager.

    Here because MiddlewareManager doesn't have methods that could take a spider arg."""

    @pytest.fixture
    def crawler(self) -> Crawler:
        return get_crawler(Spider)

    @deferred_f_from_coro_f
    async def test_deprecated_spider_arg_no_crawler_spider(
        self, crawler: Crawler
    ) -> None:
        """Crawler is provided, but doesn't have a spider, the methods raise an exception.
        The instance passed to a deprecated method is ignored."""
        mwman = ItemPipelineManager(crawler=crawler)
        with (
            pytest.warns(
                ScrapyDeprecationWarning,
                match=r"DeprecatedSpiderArgPipeline.open_spider\(\) requires a spider argument",
            ),
            pytest.warns(
                ScrapyDeprecationWarning,
                match=r"DeprecatedSpiderArgPipeline.close_spider\(\) requires a spider argument",
            ),
            pytest.warns(
                ScrapyDeprecationWarning,
                match=r"DeprecatedSpiderArgPipeline.process_item\(\) requires a spider argument",
            ),
        ):
            mwman._add_middleware(DeprecatedSpiderArgPipeline())
        with (
            pytest.warns(
                ScrapyDeprecationWarning,
                match=r"ItemPipelineManager.open_spider\(\) is deprecated, use open_spider_async\(\) instead",
            ),
            pytest.raises(
                ValueError,
                match="ItemPipelineManager needs to access self.crawler.spider but it is None",
            ),
        ):
            mwman.open_spider(DefaultSpider())
        with pytest.raises(
            ValueError,
            match="ItemPipelineManager needs to access self.crawler.spider but it is None",
        ):
            await mwman.open_spider_async()
        with (
            pytest.warns(
                ScrapyDeprecationWarning,
                match=r"ItemPipelineManager.close_spider\(\) is deprecated, use close_spider_async\(\) instead",
            ),
            pytest.raises(
                ValueError,
                match="ItemPipelineManager needs to access self.crawler.spider but it is None",
            ),
        ):
            mwman.close_spider(DefaultSpider())
        with pytest.raises(
            ValueError,
            match="ItemPipelineManager needs to access self.crawler.spider but it is None",
        ):
            await mwman.close_spider_async()

    def test_deprecated_spider_arg_with_crawler(self, crawler: Crawler) -> None:
        """Crawler is provided and has a spider, works. The instance passed to a deprecated method
        is ignored, even if mismatched."""
        mwman = ItemPipelineManager(crawler=crawler)
        crawler.spider = crawler._create_spider("foo")
        with pytest.warns(
            ScrapyDeprecationWarning,
            match=r"ItemPipelineManager.open_spider\(\) is deprecated, use open_spider_async\(\) instead",
        ):
            mwman.open_spider(DefaultSpider())
        with pytest.warns(
            ScrapyDeprecationWarning,
            match=r"ItemPipelineManager.close_spider\(\) is deprecated, use close_spider_async\(\) instead",
        ):
            mwman.close_spider(DefaultSpider())

    def test_deprecated_spider_arg_without_crawler(self) -> None:
        """The first instance passed to a deprecated method is used. Mismatched ones raise an error."""
        with pytest.warns(
            ScrapyDeprecationWarning,
            match="was called without the crawler argument",
        ):
            mwman = ItemPipelineManager()
        spider = DefaultSpider()
        with pytest.warns(
            ScrapyDeprecationWarning,
            match=r"ItemPipelineManager.open_spider\(\) is deprecated, use open_spider_async\(\) instead",
        ):
            mwman.open_spider(spider)
        with (
            pytest.warns(
                ScrapyDeprecationWarning,
                match=r"ItemPipelineManager.close_spider\(\) is deprecated, use close_spider_async\(\) instead",
            ),
            pytest.raises(
                RuntimeError, match="Different instances of Spider were passed"
            ),
        ):
            mwman.close_spider(DefaultSpider())
        with pytest.warns(
            ScrapyDeprecationWarning,
            match=r"ItemPipelineManager.close_spider\(\) is deprecated, use close_spider_async\(\) instead",
        ):
            mwman.close_spider(spider)

    @deferred_f_from_coro_f
    async def test_no_spider_arg_without_crawler(self) -> None:
        """If no crawler and no spider arg, raise an error."""
        with pytest.warns(
            ScrapyDeprecationWarning,
            match="was called without the crawler argument",
        ):
            mwman = ItemPipelineManager()
        with (
            pytest.warns(
                ScrapyDeprecationWarning,
                match=r"DeprecatedSpiderArgPipeline.open_spider\(\) requires a spider argument",
            ),
            pytest.warns(
                ScrapyDeprecationWarning,
                match=r"DeprecatedSpiderArgPipeline.close_spider\(\) requires a spider argument",
            ),
            pytest.warns(
                ScrapyDeprecationWarning,
                match=r"DeprecatedSpiderArgPipeline.process_item\(\) requires a spider argument",
            ),
        ):
            mwman._add_middleware(DeprecatedSpiderArgPipeline())
        with (
            pytest.raises(
                ValueError,
                match="has no known Spider instance",
            ),
        ):
            await mwman.open_spider_async()
