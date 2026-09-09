from __future__ import annotations

from typing import TYPE_CHECKING

from itemadapter import ItemAdapter

from scrapy import signals
from tests import get_testdata

if TYPE_CHECKING:
    from tests.utils.engine import CrawlerRun


class TestEngineBase:
    @staticmethod
    def _assert_visited_urls(run: CrawlerRun) -> None:
        must_be_visited = [
            "/static/",
            "/redirect",
            "/redirected",
            "/static/item1.html",
            "/static/item2.html",
            "/static/item999.html",
        ]
        urls_visited = {rp[0].url for rp in run.respplug}
        urls_expected = {run.geturl(p) for p in must_be_visited}
        assert urls_expected <= urls_visited, (
            f"URLs not visited: {list(urls_expected - urls_visited)}"
        )

    @staticmethod
    def _assert_scheduled_requests(run: CrawlerRun, count: int) -> None:
        assert len(run.reqplug) == count

        paths_expected = [
            "/static/item999.html",
            "/static/item2.html",
            "/static/item1.html",
        ]

        urls_requested = {rq[0].url for rq in run.reqplug}
        urls_expected = {run.geturl(p) for p in paths_expected}
        assert urls_expected <= urls_requested
        scheduled_requests_count = len(run.reqplug)
        dropped_requests_count = len(run.reqdropped)
        responses_count = len(run.respplug)
        assert scheduled_requests_count == dropped_requests_count + responses_count
        assert len(run.reqreached) == responses_count

    @staticmethod
    def _assert_dropped_requests(run: CrawlerRun) -> None:
        assert len(run.reqdropped) == 1

    @staticmethod
    def _assert_downloaded_responses(run: CrawlerRun, count: int) -> None:
        # response tests
        assert len(run.respplug) == count
        assert len(run.reqreached) == count

        for response, _ in run.respplug:
            if run.getpath(response.url) == "/static/item999.html":
                assert response.status == 404
            if run.getpath(response.url) == "/redirect":
                assert response.status == 302

    @staticmethod
    def _assert_items_error(run: CrawlerRun) -> None:
        assert len(run.itemerror) == 2
        for item, response, spider, failure in run.itemerror:
            assert failure.value.__class__ is ZeroDivisionError
            assert spider == run.crawler.spider

            assert item["url"] == response.url
            if "item1.html" in item["url"]:
                assert item["name"] == "Item 1 name"
                assert item["price"] == "100"
            if "item2.html" in item["url"]:
                assert item["name"] == "Item 2 name"
                assert item["price"] == "200"

    @staticmethod
    def _assert_scraped_items(run: CrawlerRun) -> None:
        assert len(run.itemresp) == 2
        for item_, response in run.itemresp:
            item = ItemAdapter(item_)
            assert item["url"] == response.url
            if "item1.html" in item["url"]:
                assert item["name"] == "Item 1 name"
                assert item["price"] == "100"
            if "item2.html" in item["url"]:
                assert item["name"] == "Item 2 name"
                assert item["price"] == "200"

    @staticmethod
    def _assert_headers_received(run: CrawlerRun) -> None:
        for headers in run.headers.values():
            assert b"Server" in headers
            assert headers[b"Server"]
            assert b"TwistedWeb" in headers[b"Server"]
            assert b"Date" in headers
            assert b"Content-Type" in headers

    @staticmethod
    def _assert_bytes_received(run: CrawlerRun) -> None:
        assert len(run.bytes) == 9
        for request, data in run.bytes.items():
            joined_data = b"".join(data)
            if run.getpath(request.url) == "/static/":
                assert joined_data == get_testdata("test_site", "index.html")
            elif run.getpath(request.url) == "/static/item1.html":
                assert joined_data == get_testdata("test_site", "item1.html")
            elif run.getpath(request.url) == "/static/item2.html":
                assert joined_data == get_testdata("test_site", "item2.html")
            elif run.getpath(request.url) == "/redirected":
                assert joined_data == b"Redirected here"
            elif run.getpath(request.url) == "/redirect":
                assert (
                    joined_data == b"\n<html>\n"
                    b"    <head>\n"
                    b'        <meta http-equiv="refresh" content="0;URL=/redirected">\n'
                    b"    </head>\n"
                    b'    <body bgcolor="#FFFFFF" text="#000000">\n'
                    b'    <a href="/redirected">click here</a>\n'
                    b"    </body>\n"
                    b"</html>\n"
                )
            elif run.getpath(request.url) == "/static/item999.html":
                assert (
                    joined_data == b"\n<html>\n"
                    b"  <head><title>404 - No Such Resource</title></head>\n"
                    b"  <body>\n"
                    b"    <h1>No Such Resource</h1>\n"
                    b"    <p>File not found.</p>\n"
                    b"  </body>\n"
                    b"</html>\n"
                )
            elif run.getpath(request.url) == "/numbers":
                # signal was fired multiple times
                assert len(data) > 1
                # bytes were received in order
                numbers = [str(x).encode("utf8") for x in range(2**18)]
                assert joined_data == b"".join(numbers)

    @staticmethod
    def _assert_signals_caught(run: CrawlerRun) -> None:
        assert signals.engine_started in run.signals_caught
        assert signals.engine_stopped in run.signals_caught
        assert signals.spider_opened in run.signals_caught
        assert signals.spider_idle in run.signals_caught
        assert signals.spider_closed in run.signals_caught
        assert signals.headers_received in run.signals_caught

        assert {"spider": run.crawler.spider} == run.signals_caught[
            signals.spider_opened
        ]
        assert {"spider": run.crawler.spider} == run.signals_caught[signals.spider_idle]
        assert {
            "spider": run.crawler.spider,
            "reason": "finished",
        } == run.signals_caught[signals.spider_closed]
