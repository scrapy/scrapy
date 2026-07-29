from __future__ import annotations

from typing import Any

from scrapy.downloadermiddlewares.downloadtimeout import DownloadTimeoutMiddleware
from scrapy.http import Request
from scrapy.spiders import Spider
from scrapy.utils.test import get_crawler


def get_request_spider_mw(settings: dict[str, Any] | None = None):
    crawler = get_crawler(Spider, settings)
    spider = crawler._create_spider("foo")
    request = Request("http://scrapytest.org/")
    return request, spider, DownloadTimeoutMiddleware.from_crawler(crawler)


def test_default_download_timeout():
    req, spider, mw = get_request_spider_mw()
    mw.spider_opened(spider)
    assert mw.process_request(req) is None
    assert req.meta.get("download_timeout") == 180


def test_string_download_timeout():
    req, spider, mw = get_request_spider_mw({"DOWNLOAD_TIMEOUT": "20.1"})
    mw.spider_opened(spider)
    assert mw.process_request(req) is None
    assert req.meta.get("download_timeout") == 20.1


def test_setting_has_download_timeout():
    req, spider, mw = get_request_spider_mw({"DOWNLOAD_TIMEOUT": 2})
    mw.spider_opened(spider)
    assert mw.process_request(req) is None
    assert req.meta.get("download_timeout") == 2


def test_request_has_download_timeout():
    req, spider, mw = get_request_spider_mw({"DOWNLOAD_TIMEOUT": 2})
    mw.spider_opened(spider)
    req.meta["download_timeout"] = 1
    assert mw.process_request(req) is None
    assert req.meta.get("download_timeout") == 1


def test_zero_download_timeout():
    req, spider, mw = get_request_spider_mw({"DOWNLOAD_TIMEOUT": 0})
    mw.spider_opened(spider)
    assert mw.process_request(req) is None
    assert req.meta.get("download_timeout") is None
