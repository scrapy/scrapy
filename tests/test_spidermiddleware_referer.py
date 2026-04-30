from __future__ import annotations

import warnings
from typing import Any
from urllib.parse import urlparse

import pytest

from scrapy.http import Request, Response
from scrapy.settings import Settings
from scrapy.spidermiddlewares.referer import (
    POLICY_NO_REFERRER,
    POLICY_NO_REFERRER_WHEN_DOWNGRADE,
    POLICY_ORIGIN,
    POLICY_ORIGIN_WHEN_CROSS_ORIGIN,
    POLICY_SAME_ORIGIN,
    POLICY_SCRAPY_DEFAULT,
    POLICY_STRICT_ORIGIN,
    POLICY_STRICT_ORIGIN_WHEN_CROSS_ORIGIN,
    POLICY_UNSAFE_URL,
    DefaultReferrerPolicy,
    NoReferrerPolicy,
    NoReferrerWhenDowngradePolicy,
    OriginPolicy,
    OriginWhenCrossOriginPolicy,
    RefererMiddleware,
    ReferrerPolicy,
    SameOriginPolicy,
    StrictOriginPolicy,
    StrictOriginWhenCrossOriginPolicy,
    UnsafeUrlPolicy,
)
from scrapy.utils.misc import build_from_crawler
from scrapy.utils.test import get_crawler
from tests.utils.decorators import coroutine_test


class TestRefererMiddleware:
    req_meta: dict[str, Any] = {}
    resp_headers: dict[str, str] = {}
    settings: dict[str, Any] = {}
    scenarii: list[tuple[str, str, bytes | None]] = [
        ("http://scrapytest.org", "http://scrapytest.org/", b"http://scrapytest.org"),
    ]

    @pytest.fixture
    def mw(self) -> RefererMiddleware:
        settings = Settings(self.settings)
        return RefererMiddleware(settings)

    def get_request(self, target: str) -> Request:
        return Request(target, meta=self.req_meta)

    def get_response(self, origin: str) -> Response:
        return Response(origin, headers=self.resp_headers)

    def test(self, mw: RefererMiddleware) -> None:
        for origin, target, referrer in self.scenarii:
            response = self.get_response(origin)
            request = self.get_request(target)
            out = list(mw.process_spider_output(response, [request]))
            assert out[0].headers.get("Referer") == referrer


class MixinDefault:
    """
    Based on https://www.w3.org/TR/referrer-policy/#referrer-policy-no-referrer-when-downgrade

    with some additional filtering of s3://
    """

    scenarii: list[tuple[str, str, bytes | None]] = [
        ("https://example.com/", "https://scrapy.org/", b"https://example.com/"),
        ("http://example.com/", "http://scrapy.org/", b"http://example.com/"),
        ("http://example.com/", "https://scrapy.org/", b"http://example.com/"),
        ("https://example.com/", "http://scrapy.org/", None),
        # no credentials leak
        (
            "http://user:password@example.com/",
            "https://scrapy.org/",
            b"http://example.com/",
        ),
        # no referrer leak for local schemes
        ("file:///home/path/to/somefile.html", "https://scrapy.org/", None),
        ("file:///home/path/to/somefile.html", "http://scrapy.org/", None),
        # no referrer leak for s3 origins
        ("s3://mybucket/path/to/data.csv", "https://scrapy.org/", None),
        ("s3://mybucket/path/to/data.csv", "http://scrapy.org/", None),
    ]


class MixinNoReferrer:
    scenarii: list[tuple[str, str, bytes | None]] = [
        ("https://example.com/page.html", "https://example.com/", None),
        ("http://www.example.com/", "https://scrapy.org/", None),
        ("http://www.example.com/", "http://scrapy.org/", None),
        ("https://www.example.com/", "http://scrapy.org/", None),
        ("file:///home/path/to/somefile.html", "http://scrapy.org/", None),
    ]


class MixinNoReferrerWhenDowngrade:
    scenarii: list[tuple[str, str, bytes | None]] = [
        # TLS to TLS: send non-empty referrer
        (
            "https://example.com/page.html",
            "https://not.example.com/",
            b"https://example.com/page.html",
        ),
        (
            "https://example.com/page.html",
            "https://scrapy.org/",
            b"https://example.com/page.html",
        ),
        (
            "https://example.com:443/page.html",
            "https://scrapy.org/",
            b"https://example.com/page.html",
        ),
        (
            "https://example.com:444/page.html",
            "https://scrapy.org/",
            b"https://example.com:444/page.html",
        ),
        (
            "ftps://example.com/urls.zip",
            "https://scrapy.org/",
            b"ftps://example.com/urls.zip",
        ),
        # TLS to non-TLS: do not send referrer
        ("https://example.com/page.html", "http://not.example.com/", None),
        ("https://example.com/page.html", "http://scrapy.org/", None),
        ("ftps://example.com/urls.zip", "http://scrapy.org/", None),
        # non-TLS to TLS or non-TLS: send referrer
        (
            "http://example.com/page.html",
            "https://not.example.com/",
            b"http://example.com/page.html",
        ),
        (
            "http://example.com/page.html",
            "https://scrapy.org/",
            b"http://example.com/page.html",
        ),
        (
            "http://example.com:8080/page.html",
            "https://scrapy.org/",
            b"http://example.com:8080/page.html",
        ),
        (
            "http://example.com:80/page.html",
            "http://not.example.com/",
            b"http://example.com/page.html",
        ),
        (
            "http://example.com/page.html",
            "http://scrapy.org/",
            b"http://example.com/page.html",
        ),
        (
            "http://example.com:443/page.html",
            "http://scrapy.org/",
            b"http://example.com:443/page.html",
        ),
        (
            "ftp://example.com/urls.zip",
            "http://scrapy.org/",
            b"ftp://example.com/urls.zip",
        ),
        (
            "ftp://example.com/urls.zip",
            "https://scrapy.org/",
            b"ftp://example.com/urls.zip",
        ),
        # test for user/password stripping
        (
            "http://user:password@example.com/page.html",
            "https://not.example.com/",
            b"http://example.com/page.html",
        ),
    ]


class MixinSameOrigin:
    scenarii: list[tuple[str, str, bytes | None]] = [
        # Same origin (protocol, host, port): send referrer
        (
            "https://example.com/page.html",
            "https://example.com/not-page.html",
            b"https://example.com/page.html",
        ),
        (
            "http://example.com/page.html",
            "http://example.com/not-page.html",
            b"http://example.com/page.html",
        ),
        (
            "https://example.com:443/page.html",
            "https://example.com/not-page.html",
            b"https://example.com/page.html",
        ),
        (
            "http://example.com:80/page.html",
            "http://example.com/not-page.html",
            b"http://example.com/page.html",
        ),
        (
            "http://example.com/page.html",
            "http://example.com:80/not-page.html",
            b"http://example.com/page.html",
        ),
        (
            "http://example.com:8888/page.html",
            "http://example.com:8888/not-page.html",
            b"http://example.com:8888/page.html",
        ),
        # Different host: do NOT send referrer
        (
            "https://example.com/page.html",
            "https://not.example.com/otherpage.html",
            None,
        ),
        ("http://example.com/page.html", "http://not.example.com/otherpage.html", None),
        ("http://example.com/page.html", "http://www.example.com/otherpage.html", None),
        # Different port: do NOT send referrer
        (
            "https://example.com:444/page.html",
            "https://example.com/not-page.html",
            None,
        ),
        ("http://example.com:81/page.html", "http://example.com/not-page.html", None),
        ("http://example.com/page.html", "http://example.com:81/not-page.html", None),
        # Different protocols: do NOT send referrer
        ("https://example.com/page.html", "http://example.com/not-page.html", None),
        ("https://example.com/page.html", "http://not.example.com/", None),
        ("ftps://example.com/urls.zip", "https://example.com/not-page.html", None),
        ("ftp://example.com/urls.zip", "http://example.com/not-page.html", None),
        ("ftps://example.com/urls.zip", "https://example.com/not-page.html", None),
        # test for user/password stripping
        (
            "https://user:password@example.com/page.html",
            "http://example.com/not-page.html",
            None,
        ),
        (
            "https://user:password@example.com/page.html",
            "https://example.com/not-page.html",
            b"https://example.com/page.html",
        ),
    ]


class MixinOrigin:
    scenarii: list[tuple[str, str, bytes | None]] = [
        # TLS or non-TLS to TLS or non-TLS: referrer origin is sent (yes, even for downgrades)
        (
            "https://example.com/page.html",
            "https://example.com/not-page.html",
            b"https://example.com/",
        ),
        (
            "https://example.com/page.html",
            "https://scrapy.org",
            b"https://example.com/",
        ),
        ("https://example.com/page.html", "http://scrapy.org", b"https://example.com/"),
        ("http://example.com/page.html", "http://scrapy.org", b"http://example.com/"),
        # test for user/password stripping
        (
            "https://user:password@example.com/page.html",
            "http://scrapy.org",
            b"https://example.com/",
        ),
    ]


class MixinStrictOrigin:
    scenarii: list[tuple[str, str, bytes | None]] = [
        # TLS or non-TLS to TLS or non-TLS: referrer origin is sent but not for downgrades
        (
            "https://example.com/page.html",
            "https://example.com/not-page.html",
            b"https://example.com/",
        ),
        (
            "https://example.com/page.html",
            "https://scrapy.org",
            b"https://example.com/",
        ),
        ("http://example.com/page.html", "http://scrapy.org", b"http://example.com/"),
        # downgrade: send nothing
        ("https://example.com/page.html", "http://scrapy.org", None),
        # upgrade: send origin
        ("http://example.com/page.html", "https://scrapy.org", b"http://example.com/"),
        # test for user/password stripping
        (
            "https://user:password@example.com/page.html",
            "https://scrapy.org",
            b"https://example.com/",
        ),
        ("https://user:password@example.com/page.html", "http://scrapy.org", None),
    ]


class MixinOriginWhenCrossOrigin:
    scenarii: list[tuple[str, str, bytes | None]] = [
        # Same origin (protocol, host, port): send referrer
        (
            "https://example.com/page.html",
            "https://example.com/not-page.html",
            b"https://example.com/page.html",
        ),
        (
            "http://example.com/page.html",
            "http://example.com/not-page.html",
            b"http://example.com/page.html",
        ),
        (
            "https://example.com:443/page.html",
            "https://example.com/not-page.html",
            b"https://example.com/page.html",
        ),
        (
            "http://example.com:80/page.html",
            "http://example.com/not-page.html",
            b"http://example.com/page.html",
        ),
        (
            "http://example.com/page.html",
            "http://example.com:80/not-page.html",
            b"http://example.com/page.html",
        ),
        (
            "http://example.com:8888/page.html",
            "http://example.com:8888/not-page.html",
            b"http://example.com:8888/page.html",
        ),
        # Different host: send origin as referrer
        (
            "https://example2.com/page.html",
            "https://scrapy.org/otherpage.html",
            b"https://example2.com/",
        ),
        (
            "https://example2.com/page.html",
            "https://not.example2.com/otherpage.html",
            b"https://example2.com/",
        ),
        (
            "http://example2.com/page.html",
            "http://not.example2.com/otherpage.html",
            b"http://example2.com/",
        ),
        # exact match required
        (
            "http://example2.com/page.html",
            "http://www.example2.com/otherpage.html",
            b"http://example2.com/",
        ),
        # Different port: send origin as referrer
        (
            "https://example3.com:444/page.html",
            "https://example3.com/not-page.html",
            b"https://example3.com:444/",
        ),
        (
            "http://example3.com:81/page.html",
            "http://example3.com/not-page.html",
            b"http://example3.com:81/",
        ),
        # Different protocols: send origin as referrer
        (
            "https://example4.com/page.html",
            "http://example4.com/not-page.html",
            b"https://example4.com/",
        ),
        (
            "https://example4.com/page.html",
            "http://not.example4.com/",
            b"https://example4.com/",
        ),
        (
            "ftps://example4.com/urls.zip",
            "https://example4.com/not-page.html",
            b"ftps://example4.com/",
        ),
        (
            "ftp://example4.com/urls.zip",
            "http://example4.com/not-page.html",
            b"ftp://example4.com/",
        ),
        (
            "ftps://example4.com/urls.zip",
            "https://example4.com/not-page.html",
            b"ftps://example4.com/",
        ),
        # test for user/password stripping
        (
            "https://user:password@example5.com/page.html",
            "https://example5.com/not-page.html",
            b"https://example5.com/page.html",
        ),
        # TLS to non-TLS downgrade: send origin
        (
            "https://user:password@example5.com/page.html",
            "http://example5.com/not-page.html",
            b"https://example5.com/",
        ),
    ]


class MixinStrictOriginWhenCrossOrigin:
    scenarii: list[tuple[str, str, bytes | None]] = [
        # Same origin (protocol, host, port): send referrer
        (
            "https://example.com/page.html",
            "https://example.com/not-page.html",
            b"https://example.com/page.html",
        ),
        (
            "http://example.com/page.html",
            "http://example.com/not-page.html",
            b"http://example.com/page.html",
        ),
        (
            "https://example.com:443/page.html",
            "https://example.com/not-page.html",
            b"https://example.com/page.html",
        ),
        (
            "http://example.com:80/page.html",
            "http://example.com/not-page.html",
            b"http://example.com/page.html",
        ),
        (
            "http://example.com/page.html",
            "http://example.com:80/not-page.html",
            b"http://example.com/page.html",
        ),
        (
            "http://example.com:8888/page.html",
            "http://example.com:8888/not-page.html",
            b"http://example.com:8888/page.html",
        ),
        # Different host: send origin as referrer
        (
            "https://example2.com/page.html",
            "https://scrapy.org/otherpage.html",
            b"https://example2.com/",
        ),
        (
            "https://example2.com/page.html",
            "https://not.example2.com/otherpage.html",
            b"https://example2.com/",
        ),
        (
            "http://example2.com/page.html",
            "http://not.example2.com/otherpage.html",
            b"http://example2.com/",
        ),
        # exact match required
        (
            "http://example2.com/page.html",
            "http://www.example2.com/otherpage.html",
            b"http://example2.com/",
        ),
        # Different port: send origin as referrer
        (
            "https://example3.com:444/page.html",
            "https://example3.com/not-page.html",
            b"https://example3.com:444/",
        ),
        (
            "http://example3.com:81/page.html",
            "http://example3.com/not-page.html",
            b"http://example3.com:81/",
        ),
        # downgrade
        ("https://example4.com/page.html", "http://example4.com/not-page.html", None),
        ("https://example4.com/page.html", "http://not.example4.com/", None),
        # non-TLS to non-TLS
        (
            "ftp://example4.com/urls.zip",
            "http://example4.com/not-page.html",
            b"ftp://example4.com/",
        ),
        # upgrade
        (
            "http://example4.com/page.html",
            "https://example4.com/not-page.html",
            b"http://example4.com/",
        ),
        (
            "http://example4.com/page.html",
            "https://not.example4.com/",
            b"http://example4.com/",
        ),
        # Different protocols: send origin as referrer
        (
            "ftps://example4.com/urls.zip",
            "https://example4.com/not-page.html",
            b"ftps://example4.com/",
        ),
        (
            "ftps://example4.com/urls.zip",
            "https://example4.com/not-page.html",
            b"ftps://example4.com/",
        ),
        # test for user/password stripping
        (
            "https://user:password@example5.com/page.html",
            "https://example5.com/not-page.html",
            b"https://example5.com/page.html",
        ),
        # TLS to non-TLS downgrade: send nothing
        (
            "https://user:password@example5.com/page.html",
            "http://example5.com/not-page.html",
            None,
        ),
    ]


class MixinUnsafeUrl:
    scenarii: list[tuple[str, str, bytes | None]] = [
        # TLS to TLS: send referrer
        (
            "https://example.com/sekrit.html",
            "http://not.example.com/",
            b"https://example.com/sekrit.html",
        ),
        (
            "https://example1.com/page.html",
            "https://not.example1.com/",
            b"https://example1.com/page.html",
        ),
        (
            "https://example1.com/page.html",
            "https://scrapy.org/",
            b"https://example1.com/page.html",
        ),
        (
            "https://example1.com:443/page.html",
            "https://scrapy.org/",
            b"https://example1.com/page.html",
        ),
        (
            "https://example1.com:444/page.html",
            "https://scrapy.org/",
            b"https://example1.com:444/page.html",
        ),
        (
            "ftps://example1.com/urls.zip",
            "https://scrapy.org/",
            b"ftps://example1.com/urls.zip",
        ),
        # TLS to non-TLS: send referrer (yes, it's unsafe)
        (
            "https://example2.com/page.html",
            "http://not.example2.com/",
            b"https://example2.com/page.html",
        ),
        (
            "https://example2.com/page.html",
            "http://scrapy.org/",
            b"https://example2.com/page.html",
        ),
        (
            "ftps://example2.com/urls.zip",
            "http://scrapy.org/",
            b"ftps://example2.com/urls.zip",
        ),
        # non-TLS to TLS or non-TLS: send referrer (yes, it's unsafe)
        (
            "http://example3.com/page.html",
            "https://not.example3.com/",
            b"http://example3.com/page.html",
        ),
        (
            "http://example3.com/page.html",
            "https://scrapy.org/",
            b"http://example3.com/page.html",
        ),
        (
            "http://example3.com:8080/page.html",
            "https://scrapy.org/",
            b"http://example3.com:8080/page.html",
        ),
        (
            "http://example3.com:80/page.html",
            "http://not.example3.com/",
            b"http://example3.com/page.html",
        ),
        (
            "http://example3.com/page.html",
            "http://scrapy.org/",
            b"http://example3.com/page.html",
        ),
        (
            "http://example3.com:443/page.html",
            "http://scrapy.org/",
            b"http://example3.com:443/page.html",
        ),
        (
            "ftp://example3.com/urls.zip",
            "http://scrapy.org/",
            b"ftp://example3.com/urls.zip",
        ),
        (
            "ftp://example3.com/urls.zip",
            "https://scrapy.org/",
            b"ftp://example3.com/urls.zip",
        ),
        # test for user/password stripping
        (
            "http://user:password@example4.com/page.html",
            "https://not.example4.com/",
            b"http://example4.com/page.html",
        ),
        (
            "https://user:password@example4.com/page.html",
            "http://scrapy.org/",
            b"https://example4.com/page.html",
        ),
    ]


class TestRefererMiddlewareDefault(MixinDefault, TestRefererMiddleware):
    pass


# --- Tests using settings to set policy using class path
class TestSettingsNoReferrer(MixinNoReferrer, TestRefererMiddleware):
    settings = {"REFERRER_POLICY": "scrapy.spidermiddlewares.referer.NoReferrerPolicy"}


class TestSettingsNoReferrerWhenDowngrade(
    MixinNoReferrerWhenDowngrade, TestRefererMiddleware
):
    settings = {
        "REFERRER_POLICY": "scrapy.spidermiddlewares.referer.NoReferrerWhenDowngradePolicy"
    }


class TestSettingsSameOrigin(MixinSameOrigin, TestRefererMiddleware):
    settings = {"REFERRER_POLICY": "scrapy.spidermiddlewares.referer.SameOriginPolicy"}


class TestSettingsOrigin(MixinOrigin, TestRefererMiddleware):
    settings = {"REFERRER_POLICY": "scrapy.spidermiddlewares.referer.OriginPolicy"}


class TestSettingsStrictOrigin(MixinStrictOrigin, TestRefererMiddleware):
    settings = {
        "REFERRER_POLICY": "scrapy.spidermiddlewares.referer.StrictOriginPolicy"
    }


class TestSettingsOriginWhenCrossOrigin(
    MixinOriginWhenCrossOrigin, TestRefererMiddleware
):
    settings = {
        "REFERRER_POLICY": "scrapy.spidermiddlewares.referer.OriginWhenCrossOriginPolicy"
    }


class TestSettingsStrictOriginWhenCrossOrigin(
    MixinStrictOriginWhenCrossOrigin, TestRefererMiddleware
):
    settings = {
        "REFERRER_POLICY": "scrapy.spidermiddlewares.referer.StrictOriginWhenCrossOriginPolicy"
    }


class TestSettingsUnsafeUrl(MixinUnsafeUrl, TestRefererMiddleware):
    settings = {"REFERRER_POLICY": "scrapy.spidermiddlewares.referer.UnsafeUrlPolicy"}


class CustomPythonOrgPolicy(ReferrerPolicy):
    """
    A dummy policy that returns referrer as http(s)://python.org
    depending on the scheme of the target URL.
    """

    def referrer(self, response, request):
        scheme = urlparse(request).scheme
        if scheme == "https":
            return b"https://python.org/"
        if scheme == "http":
            return b"http://python.org/"
        return None


class TestSettingsCustomPolicy(TestRefererMiddleware):
    settings = {"REFERRER_POLICY": CustomPythonOrgPolicy}
    scenarii = [
        ("https://example.com/", "https://scrapy.org/", b"https://python.org/"),
        ("http://example.com/", "http://scrapy.org/", b"http://python.org/"),
        ("http://example.com/", "https://scrapy.org/", b"https://python.org/"),
        ("https://example.com/", "http://scrapy.org/", b"http://python.org/"),
        (
            "file:///home/path/to/somefile.html",
            "https://scrapy.org/",
            b"https://python.org/",
        ),
        (
            "file:///home/path/to/somefile.html",
            "http://scrapy.org/",
            b"http://python.org/",
        ),
    ]


# --- Tests using Request meta dict to set policy
class TestRequestMetaDefault(MixinDefault, TestRefererMiddleware):
    req_meta = {"referrer_policy": POLICY_SCRAPY_DEFAULT}


class TestRequestMetaNoReferrer(MixinNoReferrer, TestRefererMiddleware):
    req_meta = {"referrer_policy": POLICY_NO_REFERRER}


class TestRequestMetaNoReferrerWhenDowngrade(
    MixinNoReferrerWhenDowngrade, TestRefererMiddleware
):
    req_meta = {"referrer_policy": POLICY_NO_REFERRER_WHEN_DOWNGRADE}


class TestRequestMetaSameOrigin(MixinSameOrigin, TestRefererMiddleware):
    req_meta = {"referrer_policy": POLICY_SAME_ORIGIN}


class TestRequestMetaOrigin(MixinOrigin, TestRefererMiddleware):
    req_meta = {"referrer_policy": POLICY_ORIGIN}


class TestRequestMetaSrictOrigin(MixinStrictOrigin, TestRefererMiddleware):
    req_meta = {"referrer_policy": POLICY_STRICT_ORIGIN}


class TestRequestMetaOriginWhenCrossOrigin(
    MixinOriginWhenCrossOrigin, TestRefererMiddleware
):
    req_meta = {"referrer_policy": POLICY_ORIGIN_WHEN_CROSS_ORIGIN}


class TestRequestMetaStrictOriginWhenCrossOrigin(
    MixinStrictOriginWhenCrossOrigin, TestRefererMiddleware
):
    req_meta = {"referrer_policy": POLICY_STRICT_ORIGIN_WHEN_CROSS_ORIGIN}


class TestRequestMetaUnsafeUrl(MixinUnsafeUrl, TestRefererMiddleware):
    req_meta = {"referrer_policy": POLICY_UNSAFE_URL}


class TestRequestMetaPrecedence001(MixinUnsafeUrl, TestRefererMiddleware):
    settings = {"REFERRER_POLICY": "scrapy.spidermiddlewares.referer.SameOriginPolicy"}
    req_meta = {"referrer_policy": POLICY_UNSAFE_URL}


class TestRequestMetaPrecedence002(MixinNoReferrer, TestRefererMiddleware):
    settings = {
        "REFERRER_POLICY": "scrapy.spidermiddlewares.referer.NoReferrerWhenDowngradePolicy"
    }
    req_meta = {"referrer_policy": POLICY_NO_REFERRER}


class TestRequestMetaPrecedence003(MixinUnsafeUrl, TestRefererMiddleware):
    settings = {
        "REFERRER_POLICY": "scrapy.spidermiddlewares.referer.OriginWhenCrossOriginPolicy"
    }
    req_meta = {"referrer_policy": POLICY_UNSAFE_URL}


class TestRequestMetaSettingFallback:
    params = [
        (
            # When an unknown policy is referenced in Request.meta
            # (here, a typo error),
            # the policy defined in settings takes precedence
            {
                "REFERRER_POLICY": "scrapy.spidermiddlewares.referer.OriginWhenCrossOriginPolicy"
            },
            {},
            {"referrer_policy": "ssscrapy-default"},
            OriginWhenCrossOriginPolicy,
            True,
        ),
        (
            # same as above but with string value for settings policy
            {"REFERRER_POLICY": "origin-when-cross-origin"},
            {},
            {"referrer_policy": "ssscrapy-default"},
            OriginWhenCrossOriginPolicy,
            True,
        ),
        (
            # request meta references a wrong policy but it is set,
            # so the Referrer-Policy header in response is not used,
            # and the settings' policy is applied
            {"REFERRER_POLICY": "origin-when-cross-origin"},
            {"Referrer-Policy": "unsafe-url"},
            {"referrer_policy": "ssscrapy-default"},
            OriginWhenCrossOriginPolicy,
            True,
        ),
        (
            # here, request meta does not set the policy
            # so response headers take precedence
            {"REFERRER_POLICY": "origin-when-cross-origin"},
            {"Referrer-Policy": "unsafe-url"},
            {},
            UnsafeUrlPolicy,
            False,
        ),
        (
            # here, request meta does not set the policy,
            # but response headers also use an unknown policy,
            # so the settings' policy is used
            {"REFERRER_POLICY": "origin-when-cross-origin"},
            {"Referrer-Policy": "unknown"},
            {},
            OriginWhenCrossOriginPolicy,
            True,
        ),
    ]

    def test(self):
        origin = "http://www.scrapy.org"
        target = "http://www.example.com"

        for (
            settings,
            response_headers,
            request_meta,
            policy_class,
            check_warning,
        ) in self.params[3:]:
            mw = RefererMiddleware(Settings(settings))

            response = Response(origin, headers=response_headers)
            request = Request(target, meta=request_meta)

            with warnings.catch_warnings(record=True) as w:
                policy = mw.policy(response, request)
                assert isinstance(policy, policy_class)

                if check_warning:
                    assert len(w) == 1
                    assert w[0].category is RuntimeWarning, w[0].message


class TestSettingsPolicyByName:
    def test_valid_name(self):
        for s, p in [
            (POLICY_SCRAPY_DEFAULT, DefaultReferrerPolicy),
            (POLICY_NO_REFERRER, NoReferrerPolicy),
            (POLICY_NO_REFERRER_WHEN_DOWNGRADE, NoReferrerWhenDowngradePolicy),
            (POLICY_SAME_ORIGIN, SameOriginPolicy),
            (POLICY_ORIGIN, OriginPolicy),
            (POLICY_STRICT_ORIGIN, StrictOriginPolicy),
            (POLICY_ORIGIN_WHEN_CROSS_ORIGIN, OriginWhenCrossOriginPolicy),
            (POLICY_STRICT_ORIGIN_WHEN_CROSS_ORIGIN, StrictOriginWhenCrossOriginPolicy),
            (POLICY_UNSAFE_URL, UnsafeUrlPolicy),
        ]:
            settings = Settings({"REFERRER_POLICY": s})
            mw = RefererMiddleware(settings)
            assert mw.default_policy == p

    def test_valid_name_casevariants(self):
        for s, p in [
            (POLICY_SCRAPY_DEFAULT, DefaultReferrerPolicy),
            (POLICY_NO_REFERRER, NoReferrerPolicy),
            (POLICY_NO_REFERRER_WHEN_DOWNGRADE, NoReferrerWhenDowngradePolicy),
            (POLICY_SAME_ORIGIN, SameOriginPolicy),
            (POLICY_ORIGIN, OriginPolicy),
            (POLICY_STRICT_ORIGIN, StrictOriginPolicy),
            (POLICY_ORIGIN_WHEN_CROSS_ORIGIN, OriginWhenCrossOriginPolicy),
            (POLICY_STRICT_ORIGIN_WHEN_CROSS_ORIGIN, StrictOriginWhenCrossOriginPolicy),
            (POLICY_UNSAFE_URL, UnsafeUrlPolicy),
        ]:
            settings = Settings({"REFERRER_POLICY": s.upper()})
            mw = RefererMiddleware(settings)
            assert mw.default_policy == p

    def test_invalid_name(self):
        settings = Settings({"REFERRER_POLICY": "some-custom-unknown-policy"})
        with pytest.raises(RuntimeError):
            RefererMiddleware(settings)

    def test_multiple_policy_tokens(self):
        # test parsing without space(s) after the comma
        settings1 = Settings(
            {
                "REFERRER_POLICY": (
                    f"some-custom-unknown-policy,"
                    f"{POLICY_SAME_ORIGIN},"
                    f"{POLICY_STRICT_ORIGIN_WHEN_CROSS_ORIGIN},"
                    f"another-custom-unknown-policy"
                )
            }
        )
        mw1 = RefererMiddleware(settings1)
        assert mw1.default_policy == StrictOriginWhenCrossOriginPolicy

        # test parsing with space(s) after the comma
        settings2 = Settings(
            {
                "REFERRER_POLICY": (
                    f"{POLICY_STRICT_ORIGIN_WHEN_CROSS_ORIGIN},"
                    f"    another-custom-unknown-policy,"
                    f"    {POLICY_UNSAFE_URL}"
                )
            }
        )
        mw2 = RefererMiddleware(settings2)
        assert mw2.default_policy == UnsafeUrlPolicy

    def test_multiple_policy_tokens_all_invalid(self):
        settings = Settings(
            {
                "REFERRER_POLICY": (
                    "some-custom-unknown-policy,"
                    "another-custom-unknown-policy,"
                    "yet-another-custom-unknown-policy"
                )
            }
        )
        with pytest.raises(RuntimeError):
            RefererMiddleware(settings)


class TestPolicyHeaderPrecedence001(MixinUnsafeUrl, TestRefererMiddleware):
    settings = {"REFERRER_POLICY": "scrapy.spidermiddlewares.referer.SameOriginPolicy"}
    resp_headers = {"Referrer-Policy": POLICY_UNSAFE_URL.upper()}


class TestPolicyHeaderPrecedence002(MixinNoReferrer, TestRefererMiddleware):
    settings = {
        "REFERRER_POLICY": "scrapy.spidermiddlewares.referer.NoReferrerWhenDowngradePolicy"
    }
    resp_headers = {"Referrer-Policy": POLICY_NO_REFERRER.swapcase()}


class TestPolicyHeaderPrecedence003(
    MixinNoReferrerWhenDowngrade, TestRefererMiddleware
):
    settings = {
        "REFERRER_POLICY": "scrapy.spidermiddlewares.referer.OriginWhenCrossOriginPolicy"
    }
    resp_headers = {"Referrer-Policy": POLICY_NO_REFERRER_WHEN_DOWNGRADE.title()}


class TestPolicyHeaderPrecedence004(
    MixinNoReferrerWhenDowngrade, TestRefererMiddleware
):
    """
    The empty string means "no-referrer-when-downgrade"
    """

    settings = {
        "REFERRER_POLICY": "scrapy.spidermiddlewares.referer.OriginWhenCrossOriginPolicy"
    }
    resp_headers = {"Referrer-Policy": ""}


class TestPolicyMethodResponseParamRename:
    def setup_method(self):
        self.crawler = get_crawler()
        self.mw = build_from_crawler(RefererMiddleware, self.crawler)
        self.request = Request("http://www.example.com")
        self.response = Response("http://www.example.com")

    def test_pos_string(self):
        with warnings.catch_warnings(record=True) as w:
            self.mw.policy("http://old.com", self.request)
            found = False
            for warning in w:
                if "Passing a response URL" in str(warning.message):
                    found = True
                    break
            assert found

    def test_pos_response(self):
        with warnings.catch_warnings(record=True) as w:
            self.mw.policy(self.response, self.request)
            for warning in w:
                assert "resp_or_url" not in str(warning.message)

    def test_key_resp_or_url(self):
        with warnings.catch_warnings(record=True) as w:
            self.mw.policy(resp_or_url=self.response, request=self.request)
            found = False
            for warning in w:
                if "Passing 'resp_or_url' is deprecated, use 'response' instead" in str(
                    warning.message
                ):
                    found = True
                    break
            assert found

    def test_key_response(self):
        with warnings.catch_warnings(record=True) as w:
            self.mw.policy(response=self.response, request=self.request)
            for warning in w:
                assert "resp_or_url" not in str(warning.message)

    def test_key_response_string(self):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            self.mw.policy(response="http://old.com", request=self.request)
            found = False
            for warning in w:
                if "Passing a response URL" in str(warning.message):
                    found = True
                    break
            assert found

    def test_both_resp_or_url_and_response(self):
        with pytest.raises(
            TypeError, match="Cannot pass both 'response' and 'resp_or_url'"
        ):
            self.mw.policy(
                response=self.response, resp_or_url=self.response, request=self.request
            )


@coroutine_test
async def test_response_policy_only_supports_policy_names():
    crawler = get_crawler(settings_dict={"REFERRER_POLICY": "no-referrer"})
    mw = build_from_crawler(RefererMiddleware, crawler)

    async def input_result():
        yield Request("https://example.com/")

    response = Response(
        "https://example.com/",
        headers={
            "Referrer-Policy": "scrapy.spidermiddlewares.referer.NoReferrerWhenDowngradePolicy"
        },
    )
    with pytest.warns(
        RuntimeWarning,
        match=r"Could not load referrer policy 'scrapy\.spidermiddlewares\.referer\.NoReferrerWhenDowngradePolicy' \(import paths from the response Referrer-Policy header are not allowed\)",
    ):
        output = [
            request
            async for request in mw.process_spider_output_async(
                response, input_result()
            )
        ]
    assert len(output) == 1
    assert b"Referer" not in output[0].headers

    response = Response(
        "https://example.com/",
        headers={"Referrer-Policy": "no-referrer-when-downgrade"},
    )
    output = [
        request
        async for request in mw.process_spider_output_async(response, input_result())
    ]
    assert len(output) == 1
    assert output[0].headers == {b"Referer": [b"https://example.com/"]}


@coroutine_test
async def test_referer_policies_setting():
    crawler = get_crawler(
        settings_dict={
            "REFERRER_POLICY": "no-referrer",
            "REFERRER_POLICIES": {
                "no-referrer-when-downgrade": None,
                "custom-policy": CustomPythonOrgPolicy,
                "": CustomPythonOrgPolicy,
            },
        }
    )
    mw = build_from_crawler(RefererMiddleware, crawler)

    async def input_result():
        yield Request("https://example.com/")

    # "no-referrer-when-downgrade": None,
    response = Response(
        "https://example.com/",
        headers={"Referrer-Policy": "no-referrer-when-downgrade"},
    )
    with pytest.warns(
        RuntimeWarning,
        match=r"Could not load referrer policy 'no-referrer-when-downgrade'",
    ):
        output = [
            request
            async for request in mw.process_spider_output_async(
                response, input_result()
            )
        ]
    assert len(output) == 1
    assert b"Referer" not in output[0].headers

    # "custom-policy": CustomPythonOrgPolicy,
    response = Response(
        "https://example.com/",
        headers={"Referrer-Policy": "custom-policy"},
    )
    output = [
        request
        async for request in mw.process_spider_output_async(response, input_result())
    ]
    assert len(output) == 1
    assert output[0].headers == {b"Referer": [b"https://python.org/"]}

    # "": CustomPythonOrgPolicy,
    response = Response(
        "https://example.com/",
        headers={"Referrer-Policy": ""},
    )
    output = [
        request
        async for request in mw.process_spider_output_async(response, input_result())
    ]
    assert len(output) == 1
    assert output[0].headers == {b"Referer": [b"https://python.org/"]}
