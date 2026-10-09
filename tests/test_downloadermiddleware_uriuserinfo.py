from __future__ import annotations

import pytest

from scrapy.downloadermiddlewares.uriuserinfo import UriUserInfoMiddleware
from scrapy.http import Request
from scrapy.utils.misc import build_from_crawler
from scrapy.utils.test import get_crawler


def _meta_fields(protocol: str) -> tuple[str, str]:
    if protocol == "ftp":
        return "ftp_user", "ftp_password"
    return "http_user", "http_pass"


@pytest.mark.parametrize("protocol", ["ftp", "http", "https"])
@pytest.mark.parametrize(
    ("userinfo", "user", "password"),
    [
        ("foo:bar@", "foo", "bar"),
        ("foo:@", "foo", ""),
        # No password in the URL means no password meta key.
        ("foo@", "foo", None),
        (":bar@", "", "bar"),
        # Percent-encoded delimiters are unquoted.
        ("foo%3A:b%40r@", "foo:", "b@r"),
    ],
)
def test_userinfo(
    protocol: str, userinfo: str, user: str, password: str | None
) -> None:
    user_field, password_field = _meta_fields(protocol)
    mw = build_from_crawler(UriUserInfoMiddleware, get_crawler())
    request = Request(f"{protocol}://{userinfo}example.com/")
    processed_request = mw.process_request(request)
    assert isinstance(processed_request, Request)
    assert processed_request.url == f"{protocol}://example.com/"
    assert request.meta[user_field] == user
    if password is None:
        assert password_field not in request.meta
    else:
        assert request.meta[password_field] == password


@pytest.mark.parametrize("protocol", ["ftp", "http", "https"])
def test_no_userinfo(protocol: str) -> None:
    mw = build_from_crawler(UriUserInfoMiddleware, get_crawler())
    request = Request(f"{protocol}://example.com/")
    assert mw.process_request(request) is None
    assert not request.meta


@pytest.mark.parametrize("protocol", ["ftp", "http", "https"])
def test_meta_takes_precedence(protocol: str) -> None:
    user_field, password_field = _meta_fields(protocol)
    mw = build_from_crawler(UriUserInfoMiddleware, get_crawler())
    request = Request(
        f"{protocol}://foo:bar@example.com/",
        meta={user_field: "baz", password_field: "qux"},
    )
    processed_request = mw.process_request(request)
    assert isinstance(processed_request, Request)
    assert processed_request.url == f"{protocol}://example.com/"
    assert request.meta[user_field] == "baz"
    assert request.meta[password_field] == "qux"


def test_unhandled_protocol() -> None:
    mw = build_from_crawler(UriUserInfoMiddleware, get_crawler())
    request = Request("s3://foo:bar@example.com/")
    assert mw.process_request(request) is None
    assert not request.meta
