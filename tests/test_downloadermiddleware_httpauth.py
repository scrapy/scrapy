from typing import Any

import pytest
from w3lib.http import basic_auth_header

from scrapy.downloadermiddlewares.httpauth import HttpAuthMiddleware
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.http import Request
from scrapy.spiders import Spider
from scrapy.utils.misc import build_from_crawler
from scrapy.utils.test import get_crawler

_DOMAIN_NOT_SET = object()


def make_mw(
    user: str = "", passwd: str = "", domain: str | object = _DOMAIN_NOT_SET
) -> HttpAuthMiddleware:
    settings: dict[str, Any] = {
        "HTTPAUTH_USER": user,
        "HTTPAUTH_PASS": passwd,
    }
    if domain is not _DOMAIN_NOT_SET:
        settings["HTTPAUTH_DOMAIN"] = domain
    return build_from_crawler(HttpAuthMiddleware, get_crawler(settings_dict=settings))


# --- Spider attribute tests (deprecated) ---


class LegacySpider(Spider):
    http_user = "foo"
    http_pass = "bar"


class DomainSpider(Spider):
    http_user = "foo"
    http_pass = "bar"
    http_auth_domain = "example.com"


class AnyDomainSpider(Spider):
    http_user = "foo"
    http_pass = "bar"
    http_auth_domain = None


class TestHttpAuthMiddlewareLegacySpiderAttr:
    def test_missing_domain_raises(self):
        mw = HttpAuthMiddleware()
        with pytest.warns(ScrapyDeprecationWarning), pytest.raises(AttributeError):
            mw.spider_opened(LegacySpider("foo"))

    def test_domain_spider(self):
        mw = HttpAuthMiddleware()
        with pytest.warns(ScrapyDeprecationWarning):
            mw.spider_opened(DomainSpider("foo"))
        req = Request("http://example.com/")
        mw.process_request(req)
        assert req.headers["Authorization"] == basic_auth_header("foo", "bar")

    def test_no_auth_wrong_domain(self):
        mw = HttpAuthMiddleware()
        with pytest.warns(ScrapyDeprecationWarning):
            mw.spider_opened(DomainSpider("foo"))
        req = Request("http://other.com/")
        mw.process_request(req)
        assert "Authorization" not in req.headers

    def test_any_domain_spider(self):
        mw = HttpAuthMiddleware()
        with pytest.warns(ScrapyDeprecationWarning):
            mw.spider_opened(AnyDomainSpider("foo"))
        req = Request("http://anywhere.com/")
        mw.process_request(req)
        assert req.headers["Authorization"] == basic_auth_header("foo", "bar")


# --- Settings-based tests ---


class TestHttpAuthMiddlewareSettings:
    def test_no_auth(self):
        mw = make_mw()
        req = Request("http://example.com/")
        mw.process_request(req)
        assert "Authorization" not in req.headers

    def test_auth_without_domain_raises(self):
        with pytest.raises(ValueError, match="HTTPAUTH_DOMAIN"):
            make_mw(user="foo", passwd="bar")

    def test_auth_all_domains(self):
        mw = make_mw(user="foo", passwd="bar", domain=None)
        req = Request("http://example.com/")
        mw.process_request(req)
        assert req.headers["Authorization"] == basic_auth_header("foo", "bar")

    def test_auth_domain_match(self):
        mw = make_mw(user="foo", passwd="bar", domain="example.com")
        req = Request("http://example.com/")
        mw.process_request(req)
        assert req.headers["Authorization"] == basic_auth_header("foo", "bar")

    def test_auth_subdomain(self):
        mw = make_mw(user="foo", passwd="bar", domain="example.com")
        req = Request("http://sub.example.com/")
        mw.process_request(req)
        assert req.headers["Authorization"] == basic_auth_header("foo", "bar")

    def test_no_auth_wrong_domain(self):
        mw = make_mw(user="foo", passwd="bar", domain="example.com")
        req = Request("http://other.com/")
        mw.process_request(req)
        assert "Authorization" not in req.headers

    def test_auth_already_set(self):
        mw = make_mw(user="foo", passwd="bar", domain="example.com")
        req = Request("http://example.com/", headers={"Authorization": "Digest 123"})
        mw.process_request(req)
        assert req.headers["Authorization"] == b"Digest 123"


# --- Per-request meta tests ---


class TestHttpAuthMiddlewareMeta:
    def test_meta_auth_no_domain(self):
        mw = make_mw()
        req = Request("http://example.com/", meta={"http_user": "u", "http_pass": "p"})
        mw.process_request(req)
        assert req.headers["Authorization"] == basic_auth_header("u", "p")

    def test_meta_auth_domain_match(self):
        mw = make_mw()
        req = Request(
            "http://example.com/",
            meta={
                "http_user": "u",
                "http_pass": "p",
                "http_auth_domain": "example.com",
            },
        )
        mw.process_request(req)
        assert req.headers["Authorization"] == basic_auth_header("u", "p")

    def test_meta_auth_domain_no_match(self):
        mw = make_mw()
        req = Request(
            "http://other.com/",
            meta={
                "http_user": "u",
                "http_pass": "p",
                "http_auth_domain": "example.com",
            },
        )
        mw.process_request(req)
        assert "Authorization" not in req.headers

    def test_meta_overrides_middleware(self):
        mw = make_mw(user="mw_user", passwd="mw_pass", domain="example.com")
        req = Request(
            "http://example.com/",
            meta={"http_user": "meta_user", "http_pass": "meta_pass"},
        )
        mw.process_request(req)
        assert req.headers["Authorization"] == basic_auth_header(
            "meta_user", "meta_pass"
        )

    def test_meta_already_set(self):
        mw = make_mw()
        req = Request(
            "http://example.com/",
            headers={"Authorization": "Digest 123"},
            meta={"http_user": "u", "http_pass": "p"},
        )
        mw.process_request(req)
        assert req.headers["Authorization"] == b"Digest 123"

    @pytest.mark.parametrize(
        ("url", "expected"),
        [
            ("https://example.com/b", True),
            ("https://example.com:443/b", True),
            ("http://example.com/a", False),
            ("https://example.com:8443/a", False),
            ("https://sub.example.com/a", False),
            ("https://other.example/a", False),
        ],
    )
    def test_meta_auth_origin(self, url: str, expected: bool):
        mw = make_mw()
        req = Request(
            "https://example.com/a", meta={"http_user": "u", "http_pass": "p"}
        )
        mw.process_request(req)
        assert req.headers["Authorization"] == basic_auth_header("u", "p")
        redirected = req.replace(url=url, headers={})
        mw.process_request(redirected)
        assert ("Authorization" in redirected.headers) is expected

    def test_meta_auth_domain_ignores_origin(self):
        mw = make_mw()
        meta = {"http_user": "u", "http_pass": "p", "http_auth_domain": "example.com"}
        req = Request("https://example.com/a", meta=meta)
        mw.process_request(req)
        redirected = req.replace(url="http://sub.example.com/a", headers={})
        mw.process_request(redirected)
        assert redirected.headers["Authorization"] == basic_auth_header("u", "p")


@pytest.mark.parametrize(
    ("mw_kwargs", "meta"),
    [
        ({"user": "foo", "passwd": "bar", "domain": None}, {}),
        ({}, {"http_user": "u", "http_pass": "p"}),
    ],
)
@pytest.mark.parametrize("url", ["ws://example.com/a", "wss://example.com/a"])
def test_websocket(mw_kwargs: dict[str, Any], meta: dict[str, Any], url: str):
    mw = make_mw(**mw_kwargs)
    req = Request(url, meta=meta)
    mw.process_request(req)
    assert "Authorization" in req.headers


@pytest.mark.parametrize(
    ("mw_kwargs", "meta"),
    [
        ({"user": "foo", "passwd": "bar", "domain": None}, {}),
        ({}, {"http_user": "u", "http_pass": "p"}),
    ],
)
@pytest.mark.parametrize("url", ["ftp://example.com/a", "s3://example.com/a"])
def test_non_http(mw_kwargs: dict[str, Any], meta: dict[str, Any], url: str):
    mw = make_mw(**mw_kwargs)
    req = Request(url, meta=meta)
    mw.process_request(req)
    assert "Authorization" not in req.headers
