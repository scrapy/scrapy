from __future__ import annotations

from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode

import pytest

from scrapy import Field, Item, Request, Spider
from scrapy.linkextractors import LinkExtractor
from tests.benchmarks import crawl

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from pytest_codspeed import BenchmarkFixture  # type: ignore[import-not-found]

    from scrapy.http import Response
    from tests.mockserver.http import MockServer

pytest.importorskip("pytest_codspeed", reason="Benchmarks require pytest-codspeed")

PAGES = 100
LINKS_PER_PAGE = 5


class _Page(Item):
    url = Field()
    anchors = Field()


class _FollowSpider(Spider):
    name = "benchmark"
    url: str
    link_extractor = LinkExtractor()

    async def start(self) -> AsyncIterator[Any]:
        yield Request(self.url, dont_filter=True)

    def parse(self, response: Response) -> Any:
        yield _Page(
            url=response.url,
            anchors=response.css("a::text").getall(),
        )
        for link in self.link_extractor.extract_links(response):  # type: ignore[arg-type]
            yield Request(link.url)


class _Pipeline:
    def process_item(self, item: Any) -> Any:
        return item


def test_benchmark_crawl(benchmark: BenchmarkFixture, mockserver: MockServer) -> None:
    """Crawl of a set of interlinked pages served over HTTP."""
    query = urlencode({"total": PAGES, "show": LINKS_PER_PAGE, "order": "desc"})
    url = mockserver.url(f"/follow?{query}")
    settings = {"ITEM_PIPELINES": {_Pipeline: 100}, "LOG_ENABLED": False}

    def run() -> None:
        crawler = crawl(_FollowSpider, settings, url=url)
        assert crawler.stats
        assert crawler.stats.get_value("item_scraped_count") == PAGES + 1

    benchmark(run)
