from __future__ import annotations

from scrapy.downloadermiddlewares.defaultheaders import DefaultHeadersMiddleware
from scrapy.http import Request
from scrapy.spiders import Spider
from scrapy.utils.python import to_bytes
from scrapy.utils.test import get_crawler


def get_defaults_mw() -> tuple[dict[bytes, list[bytes]], DefaultHeadersMiddleware]:
    crawler = get_crawler(Spider)
    defaults = {
        to_bytes(k): [to_bytes(v)]
        for k, v in crawler.settings.get("DEFAULT_REQUEST_HEADERS").items()
    }
    return defaults, DefaultHeadersMiddleware.from_crawler(crawler)


def test_process_request():
    defaults, mw = get_defaults_mw()
    req = Request("http://www.scrapytest.org")
    mw.process_request(req)
    assert req.headers == defaults


def test_update_headers():
    defaults, mw = get_defaults_mw()
    headers = {"Accept-Language": ["es"], "Test-Header": ["test"]}
    bytes_headers = {b"Accept-Language": [b"es"], b"Test-Header": [b"test"]}
    req = Request("http://www.scrapytest.org", headers=headers)
    assert req.headers == bytes_headers

    mw.process_request(req)
    defaults.update(bytes_headers)
    assert req.headers == defaults
