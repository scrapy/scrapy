from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Any, TypeAlias
from urllib.parse import urlparse

import pytest

from scrapy.exceptions import NotConfigured, ScrapyDeprecationWarning
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

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


ScenarioTable: TypeAlias = list[tuple[str, str, bytes | None]]

# Referrer policy scenarios, as (origin, target, expected Referer) triples.

# Based on https://www.w3.org/TR/referrer-policy/#referrer-policy-no-referrer-when-downgrade
# with some additional filtering of s3://
SCENARII_DEFAULT: ScenarioTable = [
    ("http://scrapytest.org", "http://scrapytest.org/", b"http://scrapytest.org"),
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

SCENARII_NO_REFERRER: ScenarioTable = [
    ("https://example.com/page.html", "https://example.com/", None),
    ("http://www.example.com/", "https://scrapy.org/", None),
    ("http://www.example.com/", "http://scrapy.org/", None),
    ("https://www.example.com/", "http://scrapy.org/", None),
    ("file:///home/path/to/somefile.html", "http://scrapy.org/", None),
]

SCENARII_NO_REFERRER_WHEN_DOWNGRADE: ScenarioTable = [
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

SCENARII_SAME_ORIGIN: ScenarioTable = [
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
    ("ftps://example.com/urls.zip", "http://example.com/not-page.html", None),
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

SCENARII_ORIGIN: ScenarioTable = [
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

SCENARII_STRICT_ORIGIN: ScenarioTable = [
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

SCENARII_ORIGIN_WHEN_CROSS_ORIGIN: ScenarioTable = [
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
        "http://example4.com/not-page.html",
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

SCENARII_STRICT_ORIGIN_WHEN_CROSS_ORIGIN: ScenarioTable = [
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
        "ftp://example4.com/urls.zip",
        "http://example4.com/not-page.html",
        b"ftp://example4.com/",
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

SCENARII_UNSAFE_URL: ScenarioTable = [
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

# Each policy, as (REFERRER_POLICY setting, Request.meta value, scenarios); the
# Request.meta value doubles as the test id. A None setting means that the
# policy is the default one, so the setting is left alone.
POLICY_CASES: list[tuple[str | None, str, ScenarioTable]] = [
    (None, POLICY_SCRAPY_DEFAULT, SCENARII_DEFAULT),
    (
        "scrapy.spidermiddlewares.referer.NoReferrerPolicy",
        POLICY_NO_REFERRER,
        SCENARII_NO_REFERRER,
    ),
    (
        "scrapy.spidermiddlewares.referer.NoReferrerWhenDowngradePolicy",
        POLICY_NO_REFERRER_WHEN_DOWNGRADE,
        SCENARII_NO_REFERRER_WHEN_DOWNGRADE,
    ),
    (
        "scrapy.spidermiddlewares.referer.SameOriginPolicy",
        POLICY_SAME_ORIGIN,
        SCENARII_SAME_ORIGIN,
    ),
    (
        "scrapy.spidermiddlewares.referer.OriginPolicy",
        POLICY_ORIGIN,
        SCENARII_ORIGIN,
    ),
    (
        "scrapy.spidermiddlewares.referer.StrictOriginPolicy",
        POLICY_STRICT_ORIGIN,
        SCENARII_STRICT_ORIGIN,
    ),
    (
        "scrapy.spidermiddlewares.referer.OriginWhenCrossOriginPolicy",
        POLICY_ORIGIN_WHEN_CROSS_ORIGIN,
        SCENARII_ORIGIN_WHEN_CROSS_ORIGIN,
    ),
    (
        "scrapy.spidermiddlewares.referer.StrictOriginWhenCrossOriginPolicy",
        POLICY_STRICT_ORIGIN_WHEN_CROSS_ORIGIN,
        SCENARII_STRICT_ORIGIN_WHEN_CROSS_ORIGIN,
    ),
    (
        "scrapy.spidermiddlewares.referer.UnsafeUrlPolicy",
        POLICY_UNSAFE_URL,
        SCENARII_UNSAFE_URL,
    ),
]


def assert_scenarii(
    scenarii: ScenarioTable,
    *,
    settings: dict[str, Any] | None = None,
    req_meta: dict[str, Any] | None = None,
    resp_headers: dict[str, str] | None = None,
) -> None:
    mw = RefererMiddleware(Settings(settings or {}))
    for origin, target, referrer in scenarii:
        response = Response(origin, headers=resp_headers or {})
        request = Request(target, meta=req_meta or {})
        out = list(mw.process_spider_output(response, [request]))
        assert out[0].headers.get("Referer") == referrer, f"{origin} -> {target}"


@pytest.mark.parametrize(
    ("policy_path", "policy_name", "scenarii"),
    [
        pytest.param(policy_path, policy_name, scenarii, id=policy_name)
        for policy_path, policy_name, scenarii in POLICY_CASES
    ],
)
@pytest.mark.parametrize("channel", ["settings", "req_meta"])
def test_policy(
    channel: str,
    policy_path: str | None,
    policy_name: str,
    scenarii: ScenarioTable,
) -> None:
    """Each policy, set either as a class path in the settings or as a policy
    name in ``Request.meta``."""
    settings = (
        {"REFERRER_POLICY": policy_path}
        if channel == "settings" and policy_path is not None
        else {}
    )
    req_meta = {"referrer_policy": policy_name} if channel == "req_meta" else {}
    assert_scenarii(scenarii, settings=settings, req_meta=req_meta)


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


SCENARII_CUSTOM_POLICY: ScenarioTable = [
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


def test_custom_policy() -> None:
    assert_scenarii(
        SCENARII_CUSTOM_POLICY, settings={"REFERRER_POLICY": CustomPythonOrgPolicy}
    )


@pytest.mark.parametrize(
    ("settings", "req_meta", "resp_headers", "scenarii"),
    [
        # Request.meta takes precedence over the setting.
        pytest.param(
            {"REFERRER_POLICY": "scrapy.spidermiddlewares.referer.SameOriginPolicy"},
            {"referrer_policy": POLICY_UNSAFE_URL},
            {},
            SCENARII_UNSAFE_URL,
            id="meta-over-same-origin",
        ),
        pytest.param(
            {
                "REFERRER_POLICY": "scrapy.spidermiddlewares.referer.NoReferrerWhenDowngradePolicy"
            },
            {"referrer_policy": POLICY_NO_REFERRER},
            {},
            SCENARII_NO_REFERRER,
            id="meta-over-no-referrer-when-downgrade",
        ),
        pytest.param(
            {
                "REFERRER_POLICY": "scrapy.spidermiddlewares.referer.OriginWhenCrossOriginPolicy"
            },
            {"referrer_policy": POLICY_UNSAFE_URL},
            {},
            SCENARII_UNSAFE_URL,
            id="meta-over-origin-when-cross-origin",
        ),
        # The response Referrer-Policy header takes precedence over the
        # setting, whatever its case.
        pytest.param(
            {"REFERRER_POLICY": "scrapy.spidermiddlewares.referer.SameOriginPolicy"},
            {},
            {"Referrer-Policy": POLICY_UNSAFE_URL.upper()},
            SCENARII_UNSAFE_URL,
            id="header-uppercase",
        ),
        pytest.param(
            {
                "REFERRER_POLICY": "scrapy.spidermiddlewares.referer.NoReferrerWhenDowngradePolicy"
            },
            {},
            {"Referrer-Policy": POLICY_NO_REFERRER.swapcase()},
            SCENARII_NO_REFERRER,
            id="header-swapcase",
        ),
        pytest.param(
            {
                "REFERRER_POLICY": "scrapy.spidermiddlewares.referer.OriginWhenCrossOriginPolicy"
            },
            {},
            {"Referrer-Policy": POLICY_NO_REFERRER_WHEN_DOWNGRADE.title()},
            SCENARII_NO_REFERRER_WHEN_DOWNGRADE,
            id="header-titlecase",
        ),
        # The empty string means "no-referrer-when-downgrade".
        pytest.param(
            {
                "REFERRER_POLICY": "scrapy.spidermiddlewares.referer.OriginWhenCrossOriginPolicy"
            },
            {},
            {"Referrer-Policy": ""},
            SCENARII_NO_REFERRER_WHEN_DOWNGRADE,
            id="header-empty",
        ),
    ],
)
def test_policy_precedence(
    settings: dict[str, Any],
    req_meta: dict[str, Any],
    resp_headers: dict[str, str],
    scenarii: ScenarioTable,
) -> None:
    assert_scenarii(
        scenarii, settings=settings, req_meta=req_meta, resp_headers=resp_headers
    )


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
        ) in self.params:
            mw = RefererMiddleware(Settings(settings))

            response = Response(origin, headers=response_headers)
            request = Request(target, meta=request_meta)

            if check_warning:
                with pytest.warns(
                    RuntimeWarning, match="Could not load referrer policy"
                ):
                    policy = mw.policy(response, request)
            else:
                policy = mw.policy(response, request)
            assert isinstance(policy, policy_class)


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


class TestPolicyMethodResponseParamRename:
    def setup_method(self):
        self.crawler = get_crawler()
        self.mw = build_from_crawler(RefererMiddleware, self.crawler)
        self.request = Request("http://www.example.com")
        self.response = Response("http://www.example.com")

    def test_pos_string(self):
        with pytest.warns(
            ScrapyDeprecationWarning,
            match=r"Passing a response URL to RefererMiddleware\.policy\(\)",
        ):
            self.mw.policy("http://old.com", self.request)

    def test_pos_response(self):
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "error",
                category=ScrapyDeprecationWarning,
                message=r"Passing 'resp_or_url' is deprecated",
            )
            self.mw.policy(self.response, self.request)

    def test_key_resp_or_url(self):
        with pytest.warns(
            ScrapyDeprecationWarning, match=r"Passing 'resp_or_url' is deprecated"
        ):
            self.mw.policy(resp_or_url=self.response, request=self.request)

    def test_key_response(self):
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "error",
                category=ScrapyDeprecationWarning,
                message=r"Passing 'resp_or_url' is deprecated",
            )
            self.mw.policy(response=self.response, request=self.request)

    def test_key_response_string(self):
        with pytest.warns(ScrapyDeprecationWarning, match="Passing a response URL"):
            self.mw.policy(response="http://old.com", request=self.request)

    def test_both_resp_or_url_and_response(self):
        with pytest.raises(
            TypeError, match="Cannot pass both 'response' and 'resp_or_url'"
        ):
            self.mw.policy(
                response=self.response, resp_or_url=self.response, request=self.request
            )

    def test_missing_response(self):
        with pytest.raises(TypeError, match="Missing required argument: 'response'"):
            self.mw.policy(request=self.request)

    def test_missing_request(self):
        with pytest.raises(TypeError, match="Missing required argument: 'request'"):
            self.mw.policy(response=self.response)


@coroutine_test
async def test_response_policy_only_supports_policy_names():
    crawler = get_crawler(settings_dict={"REFERRER_POLICY": "no-referrer"})
    mw = build_from_crawler(RefererMiddleware, crawler)

    async def input_result() -> AsyncIterator[Any]:
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

    async def input_result() -> AsyncIterator[Any]:
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


class TestReferrerPolicyHelpers:
    def test_origin_referrer_local_scheme(self):
        # A local scheme yields no referrer.
        assert UnsafeUrlPolicy().origin_referrer("data:,foo") is None

    def test_strip_url_empty(self):
        assert UnsafeUrlPolicy().strip_url("") is None

    def test_potentially_trustworthy_data_scheme(self):
        assert UnsafeUrlPolicy().potentially_trustworthy("data:,foo") is False


def test_default_policy():
    crawler = get_crawler()
    mw = build_from_crawler(RefererMiddleware, crawler)
    assert mw.default_policy is DefaultReferrerPolicy


def test_no_settings_constructor():
    with pytest.warns(
        ScrapyDeprecationWarning,
        match="Instantiating RefererMiddleware without a 'settings' argument",
    ):
        mw = RefererMiddleware()
    assert mw.default_policy is DefaultReferrerPolicy


def test_not_configured_when_disabled():
    crawler = get_crawler(settings_dict={"REFERER_ENABLED": False})
    with pytest.raises(NotConfigured):
        build_from_crawler(RefererMiddleware, crawler)
