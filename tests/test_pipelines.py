import asyncio

import pytest
from twisted.internet.defer import Deferred, inlineCallbacks

from scrapy import Request, Spider, signals
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.pipelines import ItemPipelineManager
from scrapy.utils.asyncio import call_later
from scrapy.utils.defer import (
    deferred_f_from_coro_f,
    deferred_to_future,
    maybe_deferred_to_future,
)
from scrapy.utils.spider import DefaultSpider
from scrapy.utils.test import get_crawler, get_from_asyncio_queue
from tests.mockserver.http import MockServer


class SimplePipeline:
    def process_item(self, item, spider):
        item["pipeline_passed"] = True
        return item


class DeferredPipeline:
    def cb(self, item):
        item["pipeline_passed"] = True
        return item

    def process_item(self, item, spider):
        d = Deferred()
        d.addCallback(self.cb)
        d.callback(item)
        return d


class AsyncDefPipeline:
    async def process_item(self, item, spider):
        d = Deferred()
        call_later(0, d.callback, None)
        await maybe_deferred_to_future(d)
        item["pipeline_passed"] = True
        return item


class AsyncDefAsyncioPipeline:
    async def process_item(self, item, spider):
        d = Deferred()
        loop = asyncio.get_event_loop()
        loop.call_later(0, d.callback, None)
        await deferred_to_future(d)
        await asyncio.sleep(0.2)
        item["pipeline_passed"] = await get_from_asyncio_queue(True)
        return item


class AsyncDefNotAsyncioPipeline:
    async def process_item(self, item, spider):
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


class TestCustomPipelineManager:
    def test_deprecated_process_item_spider_arg(self) -> None:
        class CustomPipelineManager(ItemPipelineManager):
            def process_item(self, item, spider):  # pylint: disable=signature-differs
                return super().process_item(item, spider)

        crawler = get_crawler(DefaultSpider)
        crawler.spider = crawler._create_spider()
        itemproc = CustomPipelineManager.from_crawler(crawler)
        with pytest.warns(
            ScrapyDeprecationWarning,
            match=r"Passing a spider argument to CustomPipelineManager.process_item\(\) is deprecated",
        ):
            itemproc.process_item({}, crawler.spider)

    @deferred_f_from_coro_f
    async def test_deprecated_spider_arg_integration(
        self, mockserver: MockServer
    ) -> None:
        class CustomPipelineManager(ItemPipelineManager):
            def open_spider(self, spider):  # pylint: disable=signature-differs
                return super().open_spider(spider)

            def process_item(self, item, spider):  # pylint: disable=signature-differs
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
                match=r"The open_spider\(\) method of .+\.CustomPipelineManager requires a spider argument",
            ),
            pytest.warns(
                ScrapyDeprecationWarning,
                match=r"The process_item\(\) method of .+\.CustomPipelineManager requires a spider argument",
            ),
            pytest.warns(
                ScrapyDeprecationWarning,
                match=r"Passing a spider argument to CustomPipelineManager.open_spider\(\) is deprecated",
            ),
            pytest.warns(
                ScrapyDeprecationWarning,
                match=r"Passing a spider argument to CustomPipelineManager.process_item\(\) is deprecated",
            ),
        ):
            await maybe_deferred_to_future(crawler.crawl(mockserver=mockserver))

        assert len(items) == 1
