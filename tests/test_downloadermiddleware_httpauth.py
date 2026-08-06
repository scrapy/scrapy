from __future__ import annotations

from typing import Any

import pytest

from scrapy.downloadermiddlewares.httpauth import HttpAuthMiddleware
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.http import Request
from scrapy.spiders import Spider
from scrapy.utils.misc import build_from_crawler
from scrapy.utils.test import get_crawler


def _build_mw(settings: dict[str, Any], spider: Spider) -> HttpAuthMiddleware:
    mw = build_from_crawler(HttpAuthMiddleware, get_crawler(settings_dict=settings))
    if getattr(spider, "http_user", "") or getattr(spider, "http_pass", ""):
        with pytest.warns(ScrapyDeprecationWarning, match="spider attributes"):
            mw.spider_opened(spider)
    else:
        mw.spider_opened(spider)
    return mw


@pytest.mark.parametrize(
    ("config", "expected"),
    [
        # Baseline
        ({}, None),
        # Settings.
        # HTTPAUTH_DOMAIN=None allows any domain.
        (
            {"settings": {"HTTPAUTH_USER": "cu", "HTTPAUTH_DOMAIN": None}},
            b"Basic Y3U6",
        ),
        (
            {"settings": {"HTTPAUTH_PASS": "cp", "HTTPAUTH_DOMAIN": None}},
            b"Basic OmNw",
        ),
        (
            {
                "settings": {
                    "HTTPAUTH_USER": "cu",
                    "HTTPAUTH_PASS": "cp",
                    "HTTPAUTH_DOMAIN": None,
                }
            },
            b"Basic Y3U6Y3A=",
        ),
        # HTTPAUTH_DOMAIN=domain allows only that domain and subdomains.
        (
            {"settings": {"HTTPAUTH_USER": "cu", "HTTPAUTH_DOMAIN": "a.example"}},
            b"Basic Y3U6",
        ),
        (
            {
                "url": "https://s.a.example/a",
                "settings": {"HTTPAUTH_USER": "cu", "HTTPAUTH_DOMAIN": "a.example"},
            },
            b"Basic Y3U6",
        ),
        (
            {"settings": {"HTTPAUTH_USER": "cu", "HTTPAUTH_DOMAIN": "b.example"}},
            None,
        ),
        # HTTPAUTH_DOMAIN must be set if HTTPAUTH_USER or HTTPAUTH_PASS are.
        ({"settings": {"HTTPAUTH_USER": "cu"}}, ValueError),
        ({"settings": {"HTTPAUTH_PASS": "cp"}}, ValueError),
        # Spider attributes.
        # http_auth_domain=None allows any domain.
        (
            {"spider_attributes": {"http_user": "su", "http_auth_domain": None}},
            b"Basic c3U6",
        ),
        (
            {"spider_attributes": {"http_pass": "sp", "http_auth_domain": None}},
            b"Basic OnNw",
        ),
        (
            {
                "spider_attributes": {
                    "http_user": "su",
                    "http_pass": "sp",
                    "http_auth_domain": None,
                }
            },
            b"Basic c3U6c3A=",
        ),
        # http_auth_domain=domain allows only that domain and subdomains.
        (
            {"spider_attributes": {"http_user": "su", "http_auth_domain": "a.example"}},
            b"Basic c3U6",
        ),
        (
            {
                "url": "https://s.a.example/a",
                "spider_attributes": {
                    "http_user": "su",
                    "http_auth_domain": "a.example",
                },
            },
            b"Basic c3U6",
        ),
        (
            {"spider_attributes": {"http_user": "su", "http_auth_domain": "b.example"}},
            None,
        ),
        # http_auth_domain must be defined if http_user or http_pass are.
        ({"spider_attributes": {"http_user": "su"}}, AttributeError),
        # Spider attributes take priority over settings.
        (
            {
                "settings": {
                    "HTTPAUTH_USER": "cu",
                    "HTTPAUTH_PASS": "cp",
                    "HTTPAUTH_DOMAIN": None,
                },
                "spider_attributes": {"http_user": "su", "http_auth_domain": None},
            },
            b"Basic c3U6",
        ),
        # Request.meta.
        ({"meta": {"http_user": "mu"}}, b"Basic bXU6"),
        ({"meta": {"http_pass": "mp"}}, b"Basic Om1w"),
        ({"meta": {"http_user": "mu", "http_pass": "mp"}}, b"Basic bXU6bXA="),
        # Request.meta["http_auth_domain"]=domain allows only that domain and
        # its subdomains.
        (
            {"meta": {"http_user": "mu", "http_auth_domain": "a.example"}},
            b"Basic bXU6",
        ),
        (
            {
                "url": "https://s.a.example/a",
                "meta": {"http_user": "mu", "http_auth_domain": "a.example"},
            },
            b"Basic bXU6",
        ),
        ({"meta": {"http_user": "mu", "http_auth_domain": "b.example"}}, None),
        # Without http_auth_domain, credentials from Request.meta are limited
        # to the origin of the request where they were first seen.
        #
        # Note: auth_origin is not meant to be set by users, it is set the
        # first time a request is processed by the middleware. See
        # test_origin_setdefault.
        (
            {"meta": {"auth_origin": "https://a.example", "http_user": "mu"}},
            b"Basic bXU6",
        ),
        (
            {
                "url": "https://a.example:443",
                "meta": {"auth_origin": "https://a.example", "http_user": "mu"},
            },
            b"Basic bXU6",
        ),
        (
            {
                "url": "https://s.a.example",
                "meta": {"auth_origin": "https://a.example", "http_user": "mu"},
            },
            None,
        ),
        ({"meta": {"auth_origin": "http://a.example", "http_user": "mu"}}, None),
        ({"meta": {"auth_origin": "https://a.example:1", "http_user": "mu"}}, None),
        ({"meta": {"auth_origin": "https://b.example", "http_user": "mu"}}, None),
        # http_auth_domain takes priority over auth_origin.
        (
            {
                "meta": {
                    "auth_origin": "https://b.example",
                    "http_user": "mu",
                    "http_auth_domain": "a.example",
                }
            },
            b"Basic bXU6",
        ),
        # Takes priority over settings and spider attributes.
        (
            {
                "meta": {"http_user": "mu"},
                "settings": {
                    "HTTPAUTH_USER": "cu",
                    "HTTPAUTH_PASS": "cp",
                    "HTTPAUTH_DOMAIN": None,
                },
            },
            b"Basic bXU6",
        ),
        (
            {
                "meta": {"http_user": "mu"},
                "spider_attributes": {
                    "http_user": "su",
                    "http_pass": "sp",
                    "http_auth_domain": None,
                },
            },
            b"Basic bXU6",
        ),
        # If the Authorization header is set, it is not modified.
        (
            {
                "headers": {"Authorization": "a"},
                "settings": {"HTTPAUTH_USER": "cu", "HTTPAUTH_DOMAIN": None},
            },
            b"a",
        ),
        (
            {
                "headers": {"Authorization": "a"},
                "spider_attributes": {"http_user": "su", "http_auth_domain": None},
            },
            b"a",
        ),
        ({"headers": {"Authorization": "a"}, "meta": {"http_user": "mu"}}, b"a"),
        # If a non-HTTP request is received, nothing is done.
        (
            {
                "url": "ftp://example.com",
                "spider_attributes": {"http_user": "su", "http_auth_domain": None},
            },
            None,
        ),
        ({"url": "s3://example.com", "meta": {"http_user": "mu"}}, None),
    ],
)
def test_main(config: dict[str, Any], expected: bytes | type[Exception] | None) -> None:
    url = config.get("url", "https://a.example")
    headers = config.get("headers", {})
    meta = config.get("meta", {})
    settings = config.get("settings", {})
    spider_attributes = config.get("spider_attributes", {})

    class TestSpider(Spider):
        pass

    for k, v in spider_attributes.items():
        setattr(TestSpider, k, v)

    spider = TestSpider("foo")

    if isinstance(expected, type) and issubclass(expected, Exception):
        with pytest.raises(expected):
            _build_mw(settings, spider)
        return

    mw = _build_mw(settings, spider)
    request = Request(url, headers=headers, meta=meta)
    assert mw.process_request(request) is None
    if expected is None:
        assert "Authorization" not in request.headers
    else:
        assert request.headers["Authorization"] == expected, repr(
            request.headers["Authorization"]
        )


@pytest.mark.parametrize(
    ("meta", "url", "output_value"),
    [
        ({}, "https://example.com/a", None),
        ({"http_user": "a", "auth_origin": "foo"}, "https://example.com/a", "foo"),
        ({"http_user": "a"}, "https://example.com/a", "https://example.com"),
        ({"http_user": "a"}, "http://example.com/a", "http://example.com"),
        ({"http_user": "a"}, "https://example.com:443/a", "https://example.com"),
        ({"http_user": "a"}, "http://example.com:80/a", "http://example.com"),
        ({"http_user": "a"}, "https://example.com:80/a", "https://example.com:80"),
        ({"http_user": "a"}, "http://example.com:443/a", "http://example.com:443"),
        ({"http_user": "a"}, "https://example.com:1234/a", "https://example.com:1234"),
        ({"http_user": "a"}, "http://example.com:1234/a", "http://example.com:1234"),
        # No origin is tracked when the allowed domain is explicit.
        (
            {"http_user": "a", "http_auth_domain": "example.com"},
            "https://example.com/a",
            None,
        ),
    ],
)
def test_origin_setdefault(
    meta: dict[str, Any], url: str, output_value: str | None
) -> None:
    """When request.meta is used for authorization, an auth_origin meta key is
    defined on the request if not defined already."""
    mw = build_from_crawler(HttpAuthMiddleware, get_crawler())
    request = Request(url, meta=meta)
    assert mw.process_request(request) is None
    if output_value is None:
        assert "auth_origin" not in request.meta
    else:
        assert request.meta["auth_origin"] == output_value
