from __future__ import annotations

from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode

import pytest

from scrapy import Field, Item, Request, Spider
from scrapy.linkextractors import LinkExtractor
from tests.benchmarks import NullDownloadHandler, crawl

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from pytest_codspeed import BenchmarkFixture  # type: ignore[import-not-found]

    from scrapy.crawler import Crawler
    from scrapy.http import Response
    from tests.mockserver.http import MockServer

pytest.importorskip("pytest_codspeed", reason="Benchmarks require pytest-codspeed")

PAGES = 100
LINKS_PER_PAGE = 5

# Requests per crawl of the benchmarks that use NullDownloadHandler. The broad
# crawl scenarios split them differently between hostnames and pages per
# hostname.
REQUESTS = 200
BROAD_DEEP_PAGES = 10

# Requests per crawl and delay of the benchmark that measures delayed requests,
# where wall time, unlike in the other benchmarks, is a function of the delay.
DELAYED_REQUESTS = 50
DELAY = 0.005

NULL_SETTINGS: dict[str, Any] = {
    "DOWNLOAD_HANDLERS": {"http": NullDownloadHandler},
    "LOG_ENABLED": False,
}


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


class _TreeSpider(Spider):
    """Crawl *pages* pages on each of *domains* hostnames.

    Pages are numbered from 1, and page *n* links to pages *2n* and *2n+1*, so
    that requests also reach the scheduler from callbacks, and not only from
    :meth:`~scrapy.Spider.start`.
    """

    name = "benchmark-tree"
    domains: int = 1
    pages: int = 1

    async def start(self) -> AsyncIterator[Any]:
        for domain in range(self.domains):
            yield Request(f"http://d{domain}.example.com/1")

    def parse(self, response: Response) -> Any:
        page = int(response.url.rpartition("/")[2])
        for child in (page * 2, page * 2 + 1):
            if child <= self.pages:
                yield Request(response.urljoin(f"/{child}"))


class _Pipeline:
    def process_item(self, item: Any) -> Any:
        return item


def _crawl_tree(settings: dict[str, Any], *, domains: int, pages: int) -> Crawler:
    crawler = crawl(
        _TreeSpider, {**NULL_SETTINGS, **settings}, domains=domains, pages=pages
    )
    assert crawler.stats
    assert crawler.stats.get_value("downloader/response_count") == domains * pages
    return crawler


def test_overhead_http(benchmark: BenchmarkFixture, mockserver: MockServer) -> None:
    """Per-request overhead of a crawl over HTTP.

    The pages are small on purpose, so that the cost of parsing them stays
    negligible next to the cost of moving requests and responses through the
    engine, the middlewares and the download handler.
    """
    query = urlencode({"total": PAGES, "show": LINKS_PER_PAGE, "order": "desc"})
    url = mockserver.url(f"/follow?{query}")
    settings = {"ITEM_PIPELINES": {_Pipeline: 100}, "LOG_ENABLED": False}

    def run() -> None:
        crawler = crawl(_FollowSpider, settings, url=url)
        assert crawler.stats
        assert crawler.stats.get_value("item_scraped_count") == PAGES + 1

    benchmark(run)


def test_overhead_engine(benchmark: BenchmarkFixture) -> None:
    """Per-request overhead of a crawl of a single hostname without any I/O."""

    def run() -> None:
        crawler = _crawl_tree({}, domains=1, pages=REQUESTS)
        assert crawler.stats
        assert crawler.stats.get_value("benchmark/peak_concurrency") > 1

    benchmark(run)


@pytest.mark.parametrize(
    ("domains", "pages"),
    [
        pytest.param(REQUESTS, 1, id="shallow"),
        pytest.param(REQUESTS // BROAD_DEEP_PAGES, BROAD_DEEP_PAGES, id="deep"),
    ],
)
def test_overhead_broad(benchmark: BenchmarkFixture, domains: int, pages: int) -> None:
    """Per-request overhead of a broad crawl.

    The shallow scenario, which reaches a single page of every hostname, pays
    the cost of tracking a hostname for the first time on every request, and
    gets its requests from :meth:`~scrapy.Spider.start`. The deep scenario,
    which reaches the same number of pages spread over fewer hostnames,
    amortizes that cost, and instead keeps several requests per hostname
    waiting in the scheduler.
    """
    benchmark(lambda: _crawl_tree({}, domains=domains, pages=pages))


def test_overhead_concurrency(benchmark: BenchmarkFixture) -> None:
    """Overhead of a crawl limited to 1 request at a time on a single hostname."""
    settings = {"CONCURRENT_REQUESTS_PER_DOMAIN": 1}
    benchmark(lambda: _crawl_tree(settings, domains=1, pages=REQUESTS))


def test_overhead_delay(benchmark: BenchmarkFixture) -> None:
    """Overhead of a crawl where every request waits for a download delay.

    The delay is not randomized, so that wall time, and hence the number of
    reactor iterations that the crawl needs, does not change between runs.
    """
    settings = {"DOWNLOAD_DELAY": DELAY, "RANDOMIZE_DOWNLOAD_DELAY": False}
    benchmark(lambda: _crawl_tree(settings, domains=1, pages=DELAYED_REQUESTS))
