from __future__ import annotations

from typing import TYPE_CHECKING, Any

from scrapy import Request, Spider, signals
from scrapy.utils.defer import maybe_deferred_to_future
from scrapy.utils.test import get_crawler
from tests.utils.decorators import coroutine_test

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterable

    from twisted.python.failure import Failure

    from scrapy.http import Response
    from tests.mockserver.http import MockServer


class LineageSpider(Spider):
    name = "lineage"
    custom_settings = {"RETRY_TIMES": 1}

    def __init__(self, mockserver: MockServer, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.mockserver = mockserver

    async def start(self) -> AsyncIterator[Any]:
        yield Request(self.mockserver.url("/redirect"))

    def parse(self, response: Response) -> Iterable[Request]:
        yield Request(self.mockserver.url("/status?n=503"), errback=self.on_error)
        assert response.request
        yield Request(
            self.mockserver.url("/text"), parent_id=response.request.parent_id
        )

    async def on_error(self, failure: Failure) -> AsyncIterator[Request]:
        yield Request(self.mockserver.url("/status?n=200"), callback=self.done)

    def done(self, response: Response) -> None:
        pass


@coroutine_test
async def test_lineage(mockserver: MockServer) -> None:
    requests: dict[str, Request] = {}

    def track(request: Request) -> None:
        requests.setdefault(request.url.removeprefix(mockserver.url("")), request)
        if "503" in request.url and request.meta.get("retry_times"):
            requests["retry"] = request

    crawler = get_crawler(LineageSpider)
    crawler.signals.connect(track, signals.request_reached_downloader)
    await maybe_deferred_to_future(crawler.crawl(mockserver=mockserver))

    parents = {path: r.parent_id for path, r in requests.items()}
    ids = {path: r.id for path, r in requests.items()}
    assert parents == {
        "/redirect": None,
        "/redirected": ids["/redirect"],
        "/status?n=503": ids["/redirected"],
        "retry": ids["/status?n=503"],
        "/status?n=200": ids["retry"],
        "/text": ids["/redirect"],
    }
