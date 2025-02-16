import warnings

import pytest

from scrapy import Request, Spider
from scrapy.downloadermiddlewares.offsite import OffsiteMiddleware
from scrapy.exceptions import IgnoreRequest
from scrapy.utils.test import get_crawler

UNSET = object()


@pytest.mark.parametrize(
    ("allowed_domain", "url", "allowed"),
    [
        ("example.com", "http://example.com/1", True),
        ("example.com", "http://example.org/1", False),
        ("example.com", "http://sub.example.com/1", True),
        ("sub.example.com", "http://sub.example.com/1", True),
        ("sub.example.com", "http://example.com/1", False),
        ("example.com", "http://example.com:8000/1", True),
        ("example.com", "http://example.org/example.com", False),
        ("example.com", "http://example.org/foo.example.com", False),
        ("example.com", "http://example.com.example", False),
        ("a.example", "http://nota.example", False),
        ("b.a.example", "http://notb.a.example", False),
    ],
)
def test_process_request_domain_filtering(allowed_domain, url, allowed):
    crawler = get_crawler(Spider)
    spider = crawler._create_spider(name="a", allowed_domains=[allowed_domain])
    mw = OffsiteMiddleware.from_crawler(crawler)
    mw.spider_opened(spider)
    request = Request(url)
    if allowed:
        assert mw.process_request(request, spider) is None
    else:
        with pytest.raises(IgnoreRequest):
            mw.process_request(request, spider)


@pytest.mark.parametrize(
    ("value", "filtered"),
    [
        (UNSET, True),
        (None, True),
        (False, True),
        (True, False),
    ],
)
def test_process_request_dont_filter(value, filtered):
    crawler = get_crawler(Spider)
    spider = crawler._create_spider(name="a", allowed_domains=["a.example"])
    mw = OffsiteMiddleware.from_crawler(crawler)
    mw.spider_opened(spider)
    kwargs = {}
    if value is not UNSET:
        kwargs["dont_filter"] = value
    request = Request("https://b.example", **kwargs)
    if filtered:
        with pytest.raises(IgnoreRequest):
            mw.process_request(request, spider)
    else:
        assert mw.process_request(request, spider) is None


@pytest.mark.parametrize(
    ("allow_offsite", "dont_filter", "filtered"),
    [
        (True, UNSET, False),
        (True, None, False),
        (True, False, False),
        (True, True, False),
        (False, UNSET, True),
        (False, None, True),
        (False, False, True),
        (False, True, False),
    ],
)
def test_process_request_allow_offsite(allow_offsite, dont_filter, filtered):
    crawler = get_crawler(Spider)
    spider = crawler._create_spider(name="a", allowed_domains=["a.example"])
    mw = OffsiteMiddleware.from_crawler(crawler)
    mw.spider_opened(spider)
    kwargs = {"meta": {}}
    if allow_offsite is not UNSET:
        kwargs["meta"]["allow_offsite"] = allow_offsite
    if dont_filter is not UNSET:
        kwargs["dont_filter"] = dont_filter
    request = Request("https://b.example", **kwargs)
    if filtered:
        with pytest.raises(IgnoreRequest):
            mw.process_request(request, spider)
    else:
        assert mw.process_request(request, spider) is None


@pytest.mark.parametrize(
    "value",
    [
        UNSET,
        None,
        [],
    ],
)
def test_process_request_no_allowed_domains(value):
    crawler = get_crawler(Spider)
    kwargs = {}
    if value is not UNSET:
        kwargs["allowed_domains"] = value
    spider = crawler._create_spider(name="a", **kwargs)
    mw = OffsiteMiddleware.from_crawler(crawler)
    mw.spider_opened(spider)
    request = Request("https://example.com")
    assert mw.process_request(request, spider) is None


def test_process_request_invalid_domains():
    crawler = get_crawler(Spider)
    allowed_domains = ["a.example", None, "http:////b.example", "//c.example"]
    spider = crawler._create_spider(name="a", allowed_domains=allowed_domains)
    mw = OffsiteMiddleware.from_crawler(crawler)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        mw.spider_opened(spider)
    request = Request("https://a.example")
    assert mw.process_request(request, spider) is None
    for letter in ("b", "c"):
        request = Request(f"https://{letter}.example")
        with pytest.raises(IgnoreRequest):
            mw.process_request(request, spider)


@pytest.mark.parametrize(
    ("allowed_domain", "url", "allowed"),
    [
        ("example.com", "http://example.com/1", True),
        ("example.com", "http://example.org/1", False),
        ("example.com", "http://sub.example.com/1", True),
        ("sub.example.com", "http://sub.example.com/1", True),
        ("sub.example.com", "http://example.com/1", False),
        ("example.com", "http://example.com:8000/1", True),
        ("example.com", "http://example.org/example.com", False),
        ("example.com", "http://example.org/foo.example.com", False),
        ("example.com", "http://example.com.example", False),
        ("a.example", "http://nota.example", False),
        ("b.a.example", "http://notb.a.example", False),
    ],
)
def test_request_scheduled_domain_filtering(allowed_domain, url, allowed):
    crawler = get_crawler(Spider)
    spider = crawler._create_spider(name="a", allowed_domains=[allowed_domain])
    mw = OffsiteMiddleware.from_crawler(crawler)
    mw.spider_opened(spider)
    request = Request(url)
    if allowed:
        assert mw.request_scheduled(request, spider) is None
    else:
        with pytest.raises(IgnoreRequest):
            mw.request_scheduled(request, spider)


@pytest.mark.parametrize(
    ("value", "filtered"),
    [
        (UNSET, True),
        (None, True),
        (False, True),
        (True, False),
    ],
)
def test_request_scheduled_dont_filter(value, filtered):
    crawler = get_crawler(Spider)
    spider = crawler._create_spider(name="a", allowed_domains=["a.example"])
    mw = OffsiteMiddleware.from_crawler(crawler)
    mw.spider_opened(spider)
    kwargs = {}
    if value is not UNSET:
        kwargs["dont_filter"] = value
    request = Request("https://b.example", **kwargs)
    if filtered:
        with pytest.raises(IgnoreRequest):
            mw.request_scheduled(request, spider)
    else:
        assert mw.request_scheduled(request, spider) is None


@pytest.mark.parametrize(
    "value",
    [
        UNSET,
        None,
        [],
    ],
)
def test_request_scheduled_no_allowed_domains(value):
    crawler = get_crawler(Spider)
    kwargs = {}
    if value is not UNSET:
        kwargs["allowed_domains"] = value
    spider = crawler._create_spider(name="a", **kwargs)
    mw = OffsiteMiddleware.from_crawler(crawler)
    mw.spider_opened(spider)
    request = Request("https://example.com")
    assert mw.request_scheduled(request, spider) is None


def test_request_scheduled_invalid_domains():
    crawler = get_crawler(Spider)
    allowed_domains = ["a.example", None, "http:////b.example", "//c.example"]
    spider = crawler._create_spider(name="a", allowed_domains=allowed_domains)
    mw = OffsiteMiddleware.from_crawler(crawler)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        mw.spider_opened(spider)
    request = Request("https://a.example")
    assert mw.request_scheduled(request, spider) is None
    for letter in ("b", "c"):
        request = Request(f"https://{letter}.example")
        with pytest.raises(IgnoreRequest):
            mw.request_scheduled(request, spider)
