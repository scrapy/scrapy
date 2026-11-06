from __future__ import annotations

import logging
from itertools import chain
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from scrapy.downloadermiddlewares.redirect import MetaRefreshMiddleware
from scrapy.exceptions import NotConfigured, ScrapyDeprecationWarning
from scrapy.http import HtmlResponse, Request, Response
from scrapy.spiders import Spider
from scrapy.utils.misc import build_from_crawler
from scrapy.utils.test import get_crawler
from tests.utils.bases.redirect import TestRedirectBase
from tests.utils.redirect import (
    HTTP_SCHEMES,
    NON_HTTP_SCHEMES,
    REDIRECT_SCHEME_CASES,
    SCHEME_PARAMS,
)

if TYPE_CHECKING:
    from scrapy.settings import BaseSettings


def meta_refresh_body(url: str, interval: int = 5) -> bytes:
    html = f"""<html><head><meta http-equiv="refresh" content="{interval};url={url}"/></head></html>"""
    return html.encode()


class TestMetaRefreshMiddleware(TestRedirectBase):
    mwcls = MetaRefreshMiddleware
    reason = "meta refresh"

    def setup_method(self):
        crawler = get_crawler(Spider)
        self.mw = build_from_crawler(self.mwcls, crawler)

    def _body(
        self, interval: int = 5, url: str = "http://example.org/newpage"
    ) -> bytes:
        return meta_refresh_body(url, interval)

    def get_response(
        self, request: Request, location: str, status: int = 302
    ) -> Response:
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
        assert not req2.body, f"Redirected body must be empty, not {req2.body!r}"

    def test_ignore_tags_default(self):
        req = Request(url="http://example.org")
        body = (
            """<noscript><meta http-equiv="refresh" """
            """content="0;URL='http://example.org/newpage'"></noscript>"""
        )
        rsp = HtmlResponse(req.url, body=body.encode())
        response = self.mw.process_response(req, rsp)
        assert isinstance(response, Response)

    def test_scripting_false(self):
        crawler = get_crawler(Spider, {"METAREFRESH_SCRIPTING": False})
        mw = build_from_crawler(MetaRefreshMiddleware, crawler)
        req = Request(url="http://example.org")
        body = b"<noscript>" + self._body(interval=0) + b"</noscript>"
        req2 = mw.process_response(req, HtmlResponse(req.url, body=body))
        assert isinstance(req2, Request)
        assert req2.url == "http://example.org/newpage"

    @pytest.mark.parametrize("content", ["0", "0;url=#x", "0;url=http://EXAMPLE.org/"])
    def test_refresh_self(self, content: str) -> None:
        req = Request(url="http://example.org")
        body = f'<meta http-equiv="refresh" content="{content}">'.encode()
        rsp = HtmlResponse(req.url, body=body)
        assert self.mw.process_response(req, rsp) is rsp

    def test_maxdelay_shortest(self):
        req = Request(url="http://example.org")
        body = self._body(interval=1000, url="/slow") + self._body(
            interval=1, url="/fast"
        )
        req2 = self.mw.process_response(req, HtmlResponse(req.url, body=body))
        assert isinstance(req2, Request)
        assert req2.url == "http://example.org/fast"


NOSCRIPT_REFRESH = (
    b"<noscript>" + meta_refresh_body("http://example.org/newpage", 0) + b"</noscript>"
)


def _process_noscript_refresh(mw: MetaRefreshMiddleware) -> Request | Response:
    req = Request(url="http://example.org")
    return mw.process_response(req, HtmlResponse(req.url, body=NOSCRIPT_REFRESH))


@pytest.mark.parametrize(
    ("ignore_tags", "scripting"),
    [
        (["script", "noscript"], True),
        (["noscript", "template"], True),
        (["script"], False),
        ([], False),
    ],
)
def test_ignore_tags(ignore_tags: list[str], scripting: bool) -> None:
    crawler = get_crawler(Spider, {"METAREFRESH_IGNORE_TAGS": ignore_tags})
    with pytest.warns(
        ScrapyDeprecationWarning, match=f"METAREFRESH_SCRIPTING = {scripting}"
    ):
        mw = build_from_crawler(MetaRefreshMiddleware, crawler)
    assert isinstance(_process_noscript_refresh(mw), Request) is not scripting


class _RemoveNoscriptAddon:
    def update_settings(self, settings: BaseSettings) -> None:
        settings.remove_from_list("METAREFRESH_IGNORE_TAGS", "noscript")


def test_ignore_tags_removed_from_list() -> None:
    crawler = get_crawler(Spider, {"ADDONS": {_RemoveNoscriptAddon: 0}})
    with pytest.warns(ScrapyDeprecationWarning, match="METAREFRESH_SCRIPTING = False"):
        mw = build_from_crawler(MetaRefreshMiddleware, crawler)
    assert isinstance(_process_noscript_refresh(mw), Request)


def test_ignore_tags_unsupported() -> None:
    crawler = get_crawler(Spider, {"METAREFRESH_IGNORE_TAGS": ["noscript", "div"]})
    with pytest.raises(ValueError, match="METAREFRESH_SCRIPTING"):
        build_from_crawler(MetaRefreshMiddleware, crawler)


class _IgnoreNoTagsAddon:
    def update_settings(self, settings: BaseSettings) -> None:
        settings.set("METAREFRESH_IGNORE_TAGS", [], priority="addon")


def test_ignore_tags_overridden() -> None:
    crawler = get_crawler(
        Spider,
        {"ADDONS": {_IgnoreNoTagsAddon: 0}, "METAREFRESH_SCRIPTING": True},
    )
    mw = build_from_crawler(MetaRefreshMiddleware, crawler)
    assert isinstance(_process_noscript_refresh(mw), Response)


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
    mw = build_from_crawler(MetaRefreshMiddleware, crawler)
    request = Request(url)
    response = HtmlResponse(url, body=meta_refresh_body(location))
    redirect = mw.process_response(request, response)
    if target is None:
        assert redirect == response
    else:
        assert isinstance(redirect, Request)


def test_warning_meta_refresh_middleware(caplog):
    crawler = get_crawler()
    crawler.get_spider_middleware = MagicMock(  # type: ignore[method-assign]
        return_value=None
    )
    mw = build_from_crawler(MetaRefreshMiddleware, crawler)
    with caplog.at_level(logging.WARNING):
        mw._spider_opened()
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


def test_not_configured():
    crawler = get_crawler(Spider, {"METAREFRESH_ENABLED": False})
    with pytest.raises(NotConfigured):
        build_from_crawler(MetaRefreshMiddleware, crawler)
