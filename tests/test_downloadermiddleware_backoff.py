from __future__ import annotations

from typing import Any

import pytest

from scrapy.downloadermiddlewares.backoff import BackoffMiddleware
from scrapy.exceptions import (
    DownloadTimeoutError,
    NotConfigured,
    ScrapyDeprecationWarning,
)
from scrapy.http import Request, Response
from scrapy.throttler import RequestScopes, ThrottlerProtocol, iter_scopes
from scrapy.utils.misc import build_from_crawler
from scrapy.utils.spider import DefaultSpider
from scrapy.utils.test import get_crawler


def _middleware(settings: dict[str, Any] | None = None) -> BackoffMiddleware:
    crawler = get_crawler(DefaultSpider, settings_dict=settings)
    return build_from_crawler(BackoffMiddleware, crawler)


def _request(
    url: str = "http://example.com", meta: dict[str, Any] | None = None
) -> Request:
    return Request(url, meta=meta or {})


def _response(
    request: Request,
    *,
    status: int = 200,
    headers: dict[str, str] | None = None,
    flags: list[str] | None = None,
) -> Response:
    return Response(
        request.url, status=status, headers=headers or {}, request=request, flags=flags
    )


def _spy_back_off(
    middleware: BackoffMiddleware,
) -> list[tuple[list[str], float | None]]:
    """Record the (scope ids, delay) of every ``back_off`` call, still applying
    the real backoff."""
    calls: list[tuple[list[str], float | None]] = []
    throttler: ThrottlerProtocol = middleware._throttler
    original = throttler.back_off

    def spy(
        scopes: RequestScopes, *, delay: float | None = None, cap: bool = True
    ) -> None:
        calls.append((list(iter_scopes(scopes)), delay))
        original(scopes, delay=delay, cap=cap)

    throttler.back_off = spy  # type: ignore[method-assign]
    return calls


class TestInit:
    def test_disabled(self):
        crawler = get_crawler(DefaultSpider, settings_dict={"BACKOFF_ENABLED": False})
        with pytest.raises(NotConfigured):
            build_from_crawler(BackoffMiddleware, crawler)

    def test_default_codes_and_exceptions(self):
        mw = _middleware()
        assert 429 in mw._http_codes
        assert DownloadTimeoutError in mw._exceptions


class TestProcessResponse:
    def test_non_backoff_code(self):
        mw = _middleware()
        calls = _spy_back_off(mw)
        request = _request()
        response = _response(request, status=200)
        assert mw.process_response(request, response) is response
        assert calls == []

    def test_backoff_code_without_header(self):
        mw = _middleware()
        calls = _spy_back_off(mw)
        request = _request()
        mw.process_response(request, _response(request, status=429))
        assert calls == [(["example.com"], None)]

    @pytest.mark.parametrize(
        ("headers", "expected_delay"),
        [
            ({"Retry-After": "7"}, 7.0),
            ({"RateLimit-Reset": "12"}, 12.0),
            # The larger of the two headers wins.
            ({"Retry-After": "5", "RateLimit-Reset": "9"}, 9.0),
        ],
        ids=["retry-after", "ratelimit-reset", "max-of-both"],
    )
    def test_backoff_code_with_delay_header(self, headers, expected_delay):
        mw = _middleware()
        calls = _spy_back_off(mw)
        request = _request()
        mw.process_response(request, _response(request, status=503, headers=headers))
        assert calls == [(["example.com"], expected_delay)]

    def test_retry_after_http_date_in_the_past(self):
        mw = _middleware()
        calls = _spy_back_off(mw)
        request = _request()
        response = _response(
            request,
            status=503,
            headers={"Retry-After": "Wed, 21 Oct 2015 07:28:00 GMT"},
        )
        mw.process_response(request, response)
        # A past date yields no positive delay, so the exponential step applies.
        assert calls == [(["example.com"], None)]

    def test_cached_response_skipped(self):
        mw = _middleware()
        calls = _spy_back_off(mw)
        request = _request()
        mw.process_response(request, _response(request, status=429, flags=["cached"]))
        assert calls == []

    def test_dont_throttle_skipped(self):
        mw = _middleware()
        calls = _spy_back_off(mw)
        request = _request(meta={"dont_throttle": True})
        mw.process_response(request, _response(request, status=429))
        assert calls == []

    def test_per_scope_http_codes_override(self):
        mw = _middleware(
            {"THROTTLING_SCOPES": {"example.com": {"backoff": {"http_codes": [418]}}}}
        )
        calls = _spy_back_off(mw)
        # 418 is only a backoff code for this scope's override.
        request = _request()
        mw.process_response(request, _response(request, status=418))
        # A globally-configured code (429) is not one the scope backs off on.
        mw.process_response(request, _response(request, status=429))
        assert calls == [(["example.com"], None)]

    def test_deprecated_spider_arg(self):
        mw = _middleware()
        request = _request()
        response = _response(request, status=200)
        with pytest.warns(ScrapyDeprecationWarning, match="spider"):
            mw.process_response(request, response, spider=DefaultSpider())


class TestProcessException:
    def test_tracked_exception(self):
        mw = _middleware()
        calls = _spy_back_off(mw)
        mw.process_exception(_request("http://example.com/a"), DownloadTimeoutError())
        assert calls == [(["example.com"], None)]

    def test_untracked_exception(self):
        mw = _middleware()
        calls = _spy_back_off(mw)
        assert (
            mw.process_exception(_request("http://example.com/a"), ValueError()) is None
        )
        assert calls == []

    def test_dont_throttle_skipped(self):
        mw = _middleware()
        calls = _spy_back_off(mw)
        request = _request("http://example.com/a", meta={"dont_throttle": True})
        mw.process_exception(request, DownloadTimeoutError())
        assert calls == []

    def test_per_scope_exceptions_override(self):
        mw = _middleware(
            {
                "THROTTLING_SCOPES": {
                    "example.com": {"backoff": {"exceptions": ["builtins.ValueError"]}}
                }
            }
        )
        calls = _spy_back_off(mw)
        # ValueError is only a backoff trigger for this scope's override.
        mw.process_exception(_request("http://example.com/a"), ValueError())
        # A globally-configured exception is not one the scope backs off on.
        mw.process_exception(_request("http://example.com/a"), DownloadTimeoutError())
        assert calls == [(["example.com"], None)]

    def test_deprecated_spider_arg(self):
        mw = _middleware()
        with pytest.warns(ScrapyDeprecationWarning, match="spider"):
            mw.process_exception(
                _request("http://example.com/a"), ValueError(), spider=DefaultSpider()
            )


class TestResponseDelay:
    @pytest.mark.parametrize(
        ("headers", "expected"),
        [
            ({}, None),
            ({"Retry-After": "3"}, 3.0),
            ({"RateLimit-Reset": "4"}, 4.0),
            ({"Retry-After": "3", "RateLimit-Reset": "4"}, 4.0),
        ],
    )
    def test_response_delay(self, headers, expected):
        response = _response(_request(), headers=headers)
        assert BackoffMiddleware._response_delay(response) == expected
