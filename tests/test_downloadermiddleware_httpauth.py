import pytest
from w3lib.http import basic_auth_header

from scrapy.downloadermiddlewares.httpauth import HttpAuthMiddleware
from scrapy.http import Request
from scrapy.spiders import Spider


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


class TestHttpAuthMiddlewareLegacy:
    def setup_method(self):
        self.spider = LegacySpider("foo")

    def test_auth(self):
        mw = HttpAuthMiddleware()
        with pytest.raises(AttributeError):
            mw.spider_opened(self.spider)


class TestHttpAuthMiddleware:
    def setup_method(self):
        self.mw = HttpAuthMiddleware()
        self.spider = DomainSpider("foo")
        self.mw.spider_opened(self.spider)

    def teardown_method(self):
        del self.mw

    def test_no_auth(self):
        req = Request("http://example-noauth.com/")
        assert self.mw.process_request(req, self.spider) is None
        assert "Authorization" not in req.headers

    def test_auth_domain(self):
        req = Request("http://example.com/")
        assert self.mw.process_request(req, self.spider) is None
        assert req.headers["Authorization"] == basic_auth_header("foo", "bar")

    def test_auth_subdomain(self):
        req = Request("http://foo.example.com/")
        assert self.mw.process_request(req, self.spider) is None
        assert req.headers["Authorization"] == basic_auth_header("foo", "bar")

    def test_auth_already_set(self):
        req = Request("http://example.com/", headers={"Authorization": "Digest 123"})
        assert self.mw.process_request(req, self.spider) is None
        assert req.headers["Authorization"] == b"Digest 123"


class TestHttpAuthAnyMiddleware:
    def setup_method(self):
        self.mw = HttpAuthMiddleware()
        self.spider = AnyDomainSpider("foo")
        self.mw.spider_opened(self.spider)

    def teardown_method(self):
        del self.mw

    def test_auth(self):
        req = Request("http://example.com/")
        assert self.mw.process_request(req, self.spider) is None
        assert req.headers["Authorization"] == basic_auth_header("foo", "bar")

    def test_auth_already_set(self):
        req = Request("http://example.com/", headers={"Authorization": "Digest 123"})
        assert self.mw.process_request(req, self.spider) is None
        assert req.headers["Authorization"] == b"Digest 123"
