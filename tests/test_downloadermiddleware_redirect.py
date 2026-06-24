import logging
from unittest.mock import MagicMock

import pytest

from scrapy.downloadermiddlewares.redirect import RedirectMiddleware
from scrapy.http import Request, Response
from scrapy.spidermiddlewares.referer import (
    POLICY_NO_REFERRER,
    POLICY_ORIGIN,
    POLICY_UNSAFE_URL,
    RefererMiddleware,
)
from scrapy.spiders import Spider
from scrapy.utils.misc import build_from_crawler
from scrapy.utils.spider import DefaultSpider
from scrapy.utils.test import get_crawler
from tests.test_downloadermiddleware_redirect_base import (
    REDIRECT_SCHEME_CASES,
    SCHEME_PARAMS,
    Base,
)


class TestRedirectMiddleware(Base.Test):
    mwcls = RedirectMiddleware
    reason = 302

    def setup_method(self):
        crawler = get_crawler(DefaultSpider)
        crawler.spider = crawler._create_spider()
        self.mw = self.mwcls.from_crawler(crawler)

    def get_response(self, request, location, status=302):
        headers = {"Location": location}
        return Response(request.url, status=status, headers=headers)

    def test_redirect_3xx_permanent(self):
        def _test(method, status: int):
            url = f"http://www.example.com/{status}"
            url2 = "http://www.example.com/redirected"
            req = Request(url, method=method)
            rsp = Response(url, headers={"Location": url2}, status=status)

            req2 = self.mw.process_response(req, rsp)
            assert isinstance(req2, Request)
            assert req2.url == url2
            assert req2.method == method

            # response without Location header but with status code is 3XX should be ignored
            del rsp.headers["Location"]
            assert self.mw.process_response(req, rsp) is rsp

        _test("GET", status=307)
        _test("POST", status=307)
        _test("HEAD", status=307)

        _test("GET", status=308)
        _test("POST", status=308)
        _test("HEAD", status=308)

    @pytest.mark.parametrize("status", [301, 302, 303])
    def test_method_becomes_get(self, status):
        source_url = f"http://www.example.com/{status}"
        target_url = "http://www.example.com/redirected2"
        request = Request(
            source_url,
            method="POST",
            body="test",
            headers={"Content-Type": "text/plain", "Content-length": "4"},
        )
        response = Response(source_url, headers={"Location": target_url}, status=status)
        redirect_request = self.mw.process_response(request, response)
        assert isinstance(redirect_request, Request)
        assert redirect_request.url == target_url
        assert redirect_request.method == "GET"
        assert "Content-Type" not in redirect_request.headers
        assert "Content-Length" not in redirect_request.headers
        assert not redirect_request.body

    @pytest.mark.parametrize("status", [301, 302])
    @pytest.mark.parametrize("method", ["PUT", "DELETE"])
    def test_method_not_converted_on_301_302(self, status, method):
        url = f"http://www.example.com/{status}"
        url2 = "http://www.example.com/redirected"
        body = b"test-body"
        req = Request(
            url,
            method=method,
            body=body,
            headers={"Content-Type": "text/plain", "Content-Length": str(len(body))},
        )
        rsp = Response(url, headers={"Location": url2}, status=status)

        req2 = self.mw.process_response(req, rsp)
        assert isinstance(req2, Request)
        assert req2.url == url2
        assert req2.method == method
        assert req2.body == body
        assert req2.headers[b"Content-Type"] == b"text/plain"
        assert req2.headers[b"Content-Length"] == str(len(body)).encode()

    @pytest.mark.parametrize("method", ["PUT", "DELETE"])
    def test_method_converted_on_303(self, method):
        status = 303
        url = f"http://www.example.com/{status}"
        url2 = "http://www.example.com/redirected"
        req = Request(url, method=method)
        rsp = Response(url, headers={"Location": url2}, status=status)

        req2 = self.mw.process_response(req, rsp)
        assert isinstance(req2, Request)
        assert req2.url == url2
        assert req2.method == "GET"

    def test_get_method_body_preserved_on_303(self):
        status = 303
        url = f"http://www.example.com/{status}"
        url2 = "http://www.example.com/redirected"
        body = b"test-body"
        req = Request(
            url,
            method="GET",
            body=body,
            headers={"Content-Type": "text/plain", "Content-Length": str(len(body))},
        )
        rsp = Response(url, headers={"Location": url2}, status=status)

        req2 = self.mw.process_response(req, rsp)
        assert isinstance(req2, Request)
        assert req2.url == url2
        assert req2.method == "GET"
        assert req2.body == body
        assert req2.headers[b"Content-Type"] == b"text/plain"
        assert req2.headers[b"Content-Length"] == str(len(body)).encode()

    def test_redirect_strips_content_headers(self):
        url = "http://www.example.com/303"
        url2 = "http://www.example.com/redirected"
        headers = {
            "Content-Type": "application/json",
            "Content-Length": "100",
            "Content-Encoding": "gzip",
            "Content-Language": "en",
            "Content-Location": "http://www.example.com/original",
            "X-Custom": "foo",
        }
        req = Request(url, method="POST", headers=headers, body=b"foo")
        rsp = Response(url, headers={"Location": url2}, status=303)

        req2 = self.mw.process_response(req, rsp)
        assert isinstance(req2, Request)
        assert req2.url == url2
        assert req2.method == "GET"
        assert req2.body == b""
        assert "Content-Type" not in req2.headers
        assert "Content-Length" not in req2.headers
        assert "Content-Encoding" not in req2.headers
        assert "Content-Language" not in req2.headers
        assert "Content-Location" not in req2.headers
        assert req2.headers["X-Custom"] == b"foo"

    @pytest.mark.parametrize(
        (
            "referer",
            "source_url",
            "target_url",
            "policy_header",
            "expected_referer",
        ),
        [
            (
                None,
                "http://www.example.com/302",
                "http://www.example.com/redirected",
                None,
                b"http://www.example.com/302",
            ),
            (
                "http://example.com/old",
                "http://www.example.com/302",
                "http://www.example.com/redirected",
                None,
                b"http://www.example.com/302",
            ),
            (
                "https://example.com/old",
                "https://www.example.com/302",
                "http://www.example.com/redirected",
                None,
                None,
            ),
            (
                "http://example.com/old",
                "http://www.example.com/foo/bar",
                "http://www.example.com/redirected",
                "origin",
                b"http://www.example.com/",
            ),
        ],
    )
    def test_redirect_referer(
        self, referer, source_url, target_url, policy_header, expected_referer
    ):
        headers = {"Referer": referer} if referer else {}
        source_request = Request(source_url, headers=headers)
        resp_headers = {"Location": target_url}
        if policy_header:
            resp_headers["Referrer-Policy"] = policy_header
        response = Response(source_url, headers=resp_headers, status=302)
        crawler = get_crawler()
        referer_mw = build_from_crawler(RefererMiddleware, crawler)
        redirect_mw = self.mwcls.from_crawler(crawler)
        redirect_mw._referer_spider_middleware = referer_mw
        redirect_request = redirect_mw.process_response(source_request, response)
        if expected_referer:
            assert redirect_request.headers.get("Referer") == expected_referer
        else:
            assert "Referer" not in redirect_request.headers

    def test_redirect_strips_referer_no_middleware(self):
        source_url = "http://www.example.com/302"
        redirect_url = "http://www.example.com/redirected"
        source_request = Request(
            source_url, headers={"Referer": "http://example.com/old"}
        )
        response = Response(source_url, headers={"Location": redirect_url}, status=302)
        redirect_mw = self.mwcls.from_crawler(get_crawler())
        redirect_mw._referer_spider_middleware = None
        redirect_request = redirect_mw.process_response(source_request, response)
        assert "Referer" not in redirect_request.headers

    @pytest.mark.parametrize("status", [307, 308])
    def test_cross_origin_maintain_body(self, status):
        source_url = "https://example.com"
        target_url = "https://attacker.example"
        body = b"secret"
        request = Request(
            source_url,
            method="POST",
            body=body,
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(len(body)),
            },
        )
        response1 = Response(
            source_url, headers={"Location": target_url}, status=status
        )
        redirect_request = self.mw.process_response(request, response1)
        assert isinstance(redirect_request, Request)
        assert redirect_request.url == target_url
        assert redirect_request.method == "POST"
        assert redirect_request.body == body
        assert redirect_request.headers[b"Content-Type"] == b"application/json"
        assert redirect_request.headers[b"Content-Length"] == str(len(body)).encode()

    def test_redirect_keeps_fragment(self):
        url = "http://www.example.com/301#frag"
        url2 = "http://www.example.com/redirected"
        req = Request(url)
        rsp = Response(url, headers={"Location": url2}, status=302)

        req2 = self.mw.process_response(req, rsp)
        assert isinstance(req2, Request)
        assert req2.url == "http://www.example.com/redirected#frag"

    def test_redirect_302_head(self):
        url = "http://www.example.com/302"
        url2 = "http://www.example.com/redirected2"
        req = Request(url, method="HEAD")
        rsp = Response(url, headers={"Location": url2}, status=302)

        req2 = self.mw.process_response(req, rsp)
        assert isinstance(req2, Request)
        assert req2.url == url2
        assert req2.method == "HEAD"

    def test_redirect_302_relative(self):
        url = "http://www.example.com/302"
        url2 = "///i8n.example2.com/302"
        url3 = "http://i8n.example2.com/302"
        req = Request(url, method="HEAD")
        rsp = Response(url, headers={"Location": url2}, status=302)

        req2 = self.mw.process_response(req, rsp)
        assert isinstance(req2, Request)
        assert req2.url == url3
        assert req2.method == "HEAD"

    def test_spider_handling(self):
        self.mw.crawler.spider.handle_httpstatus_list = [404, 301, 302]
        url = "http://www.example.com/301"
        url2 = "http://www.example.com/redirected"
        req = Request(url)
        rsp = Response(url, headers={"Location": url2}, status=301)
        r = self.mw.process_response(req, rsp)
        assert r is rsp

    def test_request_meta_handling(self):
        url = "http://www.example.com/301"
        url2 = "http://www.example.com/redirected"

        def _test_passthrough(req):
            rsp = Response(url, headers={"Location": url2}, status=301, request=req)
            r = self.mw.process_response(req, rsp)
            assert r is rsp

        _test_passthrough(
            Request(url, meta={"handle_httpstatus_list": [404, 301, 302]})
        )
        _test_passthrough(Request(url, meta={"handle_httpstatus_all": True}))

    def test_latin1_location(self):
        req = Request("http://scrapytest.org/first")
        latin1_location = "/ação".encode("latin1")  # HTTP historically supports latin1
        resp = Response(
            "http://scrapytest.org/first",
            headers={"Location": latin1_location},
            status=302,
        )
        req_result = self.mw.process_response(req, resp)
        perc_encoded_utf8_url = "http://scrapytest.org/a%E7%E3o"
        assert perc_encoded_utf8_url == req_result.url

    def test_utf8_location(self):
        req = Request("http://scrapytest.org/first")
        utf8_location = "/ação".encode()  # header using UTF-8 encoding
        resp = Response(
            "http://scrapytest.org/first",
            headers={"Location": utf8_location},
            status=302,
        )
        req_result = self.mw.process_response(req, resp)
        perc_encoded_utf8_url = "http://scrapytest.org/a%C3%A7%C3%A3o"
        assert perc_encoded_utf8_url == req_result.url

    def test_no_location(self):
        request = Request("https://example.com")
        response = Response(request.url, status=302)
        assert self.mw.process_response(request, response) is response


@pytest.mark.parametrize(SCHEME_PARAMS, REDIRECT_SCHEME_CASES)
def test_redirect_schemes(url, location, target):
    crawler = get_crawler(Spider)
    mw = RedirectMiddleware.from_crawler(crawler)
    request = Request(url)
    response = Response(url, headers={"Location": location}, status=301)
    redirect = mw.process_response(request, response)
    if target is None:
        assert redirect == response
    else:
        assert isinstance(redirect, Request)
        assert redirect.url == target


@pytest.mark.parametrize(
    ("policy", "source_url", "target_url", "expected_referrer"),
    [
        # The policy header affects the outcome.
        # (without it, the https → http switch would drop the referer)
        (
            POLICY_UNSAFE_URL,
            "https://a.example/1",
            "http://a.example/2",
            b"https://a.example/1",
        ),
        # The policy header can get the Referer header removed.
        (
            POLICY_NO_REFERRER,
            "http://a.example/1",
            "http://a.example/2",
            None,
        ),
        # The policy header can get the Referer header edited (path stripped).
        (
            POLICY_ORIGIN,
            "http://a.example/1",
            "http://a.example/2",
            b"http://a.example/",
        ),
    ],
)
def test_response_referrer_policy(policy, source_url, target_url, expected_referrer):
    crawler = get_crawler()
    referrer_mw = build_from_crawler(RefererMiddleware, crawler)
    redirect_mw = build_from_crawler(RedirectMiddleware, crawler)
    redirect_mw._referer_spider_middleware = referrer_mw
    source_request = Request(source_url)
    extra_headers = {}
    if policy:
        extra_headers["Referrer-Policy"] = policy
    response_redirect = Response(
        source_request.url,
        status=301,
        headers={"Location": target_url, **extra_headers},
    )
    source_request = redirect_mw.process_response(source_request, response_redirect)
    assert isinstance(source_request, Request)

    assert source_request.headers.get("Referer") == expected_referrer


def test_no_warning_when_referer_middleware_present(caplog):
    crawler = get_crawler()
    crawler.get_spider_middleware = MagicMock(return_value=MagicMock())
    mw = build_from_crawler(RedirectMiddleware, crawler)
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        mw._engine_started()
    assert not [
        record
        for record in caplog.records
        if record.name == "scrapy.downloadermiddlewares.redirect"
    ]


def test_warning_redirect_middleware(caplog):
    crawler = get_crawler()
    crawler.get_spider_middleware = MagicMock(return_value=None)
    mw = build_from_crawler(RedirectMiddleware, crawler)
    with caplog.at_level(logging.WARNING):
        mw._engine_started()
    assert (
        "scrapy.downloadermiddlewares.redirect.RedirectMiddleware found no "
        "scrapy.spidermiddlewares.referer.RefererMiddleware"
    ) in caplog.text
    assert (
        "enable scrapy.spidermiddlewares.referer.RefererMiddleware (or a subclass)"
        in caplog.text
    )
    assert (
        "replace scrapy.downloadermiddlewares.redirect.RedirectMiddleware "
        "with a subclass that overrides the handle_referer() method"
    ) in caplog.text


def test_warning_subclass(caplog):
    class MyRedirectMiddleware(RedirectMiddleware):
        pass

    crawler = get_crawler()
    crawler.get_spider_middleware = MagicMock(return_value=None)
    mw = build_from_crawler(MyRedirectMiddleware, crawler)
    with caplog.at_level(logging.WARNING):
        mw._engine_started()
    assert (
        "test_warning_subclass.<locals>.MyRedirectMiddleware found no "
        "scrapy.spidermiddlewares.referer.RefererMiddleware"
    ) in caplog.text
    assert (
        "enable scrapy.spidermiddlewares.referer.RefererMiddleware (or a subclass)"
        in caplog.text
    )
    assert "edit " in caplog.text
    assert "test_warning_subclass.<locals>.MyRedirectMiddleware" in caplog.text
    assert (
        "(if defined in your code base) to override the handle_referer() method"
    ) in caplog.text
