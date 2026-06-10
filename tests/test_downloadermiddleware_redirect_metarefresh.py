from __future__ import annotations

import logging
from itertools import chain
from unittest.mock import MagicMock

import pytest

from scrapy.downloadermiddlewares.redirect import MetaRefreshMiddleware
from scrapy.http import HtmlResponse, Request, Response
from scrapy.spiders import Spider
from scrapy.utils.misc import build_from_crawler
from scrapy.utils.test import get_crawler
from tests.test_downloadermiddleware_redirect_base import (
    HTTP_SCHEMES,
    NON_HTTP_SCHEMES,
    REDIRECT_SCHEME_CASES,
    SCHEME_PARAMS,
    Base,
)


def meta_refresh_body(url, interval=5):
    html = f"""<html><head><meta http-equiv="refresh" content="{interval};url={url}"/></head></html>"""
    return html.encode("utf-8")


class TestMetaRefreshMiddleware(Base.Test):
    mwcls = MetaRefreshMiddleware
    reason = "meta refresh"

    def setup_method(self):
        crawler = get_crawler(Spider)
        self.mw = self.mwcls.from_crawler(crawler)

    def _body(self, interval=5, url="http://example.org/newpage"):
        return meta_refresh_body(url, interval)

    def get_response(self, request, location):
        return HtmlResponse(request.url, body=self._body(url=location))

    def test_meta_refresh(self):
        req = Request(url="http://example.org")
        rsp = HtmlResponse(req.url, body=self._body())
        req2 = self.mw.process_response(req, rsp)
        assert isinstance(req2, Request)
        assert req2.url == "http://example.org/newpage"

    def test_meta_refresh_with_high_interval(self):
        # meta-refresh with high intervals don't trigger redirects
        req = Request(url="http://example.org")
        rsp = HtmlResponse(
            url="http://example.org", body=self._body(interval=1000), encoding="utf-8"
        )
        rsp2 = self.mw.process_response(req, rsp)
        assert rsp is rsp2

    def test_meta_refresh_trough_posted_request(self):
        req = Request(
            url="http://example.org",
            method="POST",
            body="test",
            headers={"Content-Type": "text/plain", "Content-length": "4"},
        )
        rsp = HtmlResponse(req.url, body=self._body())
        req2 = self.mw.process_response(req, rsp)

        assert isinstance(req2, Request)
        assert req2.url == "http://example.org/newpage"
        assert req2.method == "GET"
        assert "Content-Type" not in req2.headers, (
            "Content-Type header must not be present in redirected request"
        )
        assert "Content-Length" not in req2.headers, (
            "Content-Length header must not be present in redirected request"
        )
        assert not req2.body, f"Redirected body must be empty, not '{req2.body}'"

    def test_ignore_tags_default(self):
        req = Request(url="http://example.org")
        body = (
            """<noscript><meta http-equiv="refresh" """
            """content="0;URL='http://example.org/newpage'"></noscript>"""
        )
        rsp = HtmlResponse(req.url, body=body.encode())
        response = self.mw.process_response(req, rsp)
        assert isinstance(response, Response)

    def test_ignore_tags_1_x_list(self):
        """Test that Scrapy 1.x behavior remains possible"""
        settings = {"METAREFRESH_IGNORE_TAGS": ["script", "noscript"]}
        crawler = get_crawler(Spider, settings)
        mw = MetaRefreshMiddleware.from_crawler(crawler)
        req = Request(url="http://example.org")
        body = (
            """<noscript><meta http-equiv="refresh" """
            """content="0;URL='http://example.org/newpage'"></noscript>"""
        )
        rsp = HtmlResponse(req.url, body=body.encode())
        response = mw.process_response(req, rsp)
        assert isinstance(response, Response)


@pytest.mark.parametrize(
    SCHEME_PARAMS,
    [
        *REDIRECT_SCHEME_CASES,
        # data/file/ftp/s3/foo → * does not redirect
        *(
            (
                f"{input_scheme}://example.com/a",
                f"{output_scheme}://example.com/b",
                None,
            )
            for input_scheme in NON_HTTP_SCHEMES
            for output_scheme in chain(HTTP_SCHEMES, NON_HTTP_SCHEMES)
        ),
        # data/file/ftp/s3/foo → relative does not redirect
        *(
            (
                f"{scheme}://example.com/a",
                location,
                None,
            )
            for scheme in NON_HTTP_SCHEMES
            for location in ("//example.com/b", "/b")
        ),
    ],
)
def test_meta_refresh_schemes(url, location, target):
    crawler = get_crawler(Spider)
    mw = MetaRefreshMiddleware.from_crawler(crawler)
    request = Request(url)
    response = HtmlResponse(url, body=meta_refresh_body(location))
    redirect = mw.process_response(request, response)
    if target is None:
        assert redirect == response
    else:
        assert isinstance(redirect, Request)


def test_warning_meta_refresh_middleware(caplog):
    crawler = get_crawler()
    crawler.get_spider_middleware = MagicMock(return_value=None)
    mw = build_from_crawler(MetaRefreshMiddleware, crawler)
    with caplog.at_level(logging.WARNING):
        mw._engine_started()
    assert (
        "scrapy.downloadermiddlewares.redirect.MetaRefreshMiddleware found no "
        "scrapy.spidermiddlewares.referer.RefererMiddleware"
    ) in caplog.text
    assert (
        "enable scrapy.spidermiddlewares.referer.RefererMiddleware (or a subclass)"
        in caplog.text
    )
    assert (
        "replace scrapy.downloadermiddlewares.redirect.MetaRefreshMiddleware "
        "with a subclass that overrides the handle_referer() method"
    ) in caplog.text
