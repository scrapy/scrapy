from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import pytest

from scrapy.downloadermiddlewares.httpproxy import HttpProxyMiddleware
from scrapy.exceptions import IgnoreRequest
from scrapy.http import Request, Response
from scrapy.utils.misc import build_from_crawler, set_environ
from scrapy.utils.test import get_crawler

PROXY_A = "https://a:@a.example"
PROXY_B = "https://b:@b.example"

# Proxy ID → (expected Proxy-Authorization header, expected proxy URL).
PROXIES = {
    "a": (b"Basic YTo=", "https://a.example"),
    "b": (b"Basic Yjo=", "https://b.example"),
}


def assert_proxy(request: Request, expected: str | None) -> None:
    """Check that *request* uses the proxy with the *expected* ID, or no proxy
    at all if *expected* is ``None``."""
    if expected is None:
        assert "Proxy-Authorization" not in request.headers
        assert "_auth_proxy" not in request.meta
        assert "proxy" not in request.meta
        return
    auth, url = PROXIES[expected]
    assert request.headers["Proxy-Authorization"] == auth
    assert request.meta["_auth_proxy"] == url
    assert request.meta["proxy"] == url


class TestRedirectBase(ABC):
    mwcls: type[Any]
    mw: Any
    reason: int | str

    @abstractmethod
    def get_response(
        self, request: Request, location: str, status: int = 302
    ) -> Response:
        raise NotImplementedError

    def test_priority_adjust(self):
        req = Request("http://a.example")
        rsp = self.get_response(req, "http://a.example/redirected")
        req2 = self.mw.process_response(req, rsp)
        assert req2.priority > req.priority

    def test_dont_redirect(self):
        url = "http://www.example.com/301"
        url2 = "http://www.example.com/redirected"
        req = Request(url, meta={"dont_redirect": True})
        rsp = self.get_response(req, url2)

        r = self.mw.process_response(req, rsp)
        assert isinstance(r, Response)
        assert r is rsp

        # Test that it redirects when dont_redirect is False
        req = Request(url, meta={"dont_redirect": False})
        rsp = self.get_response(req, url2)

        r = self.mw.process_response(req, rsp)
        assert isinstance(r, Request)

    def test_post(self):
        url = "http://www.example.com/302"
        url2 = "http://www.example.com/redirected2"
        req = Request(
            url,
            method="POST",
            body="test",
            headers={"Content-Type": "text/plain", "Content-length": "4"},
        )
        rsp = self.get_response(req, url2)

        req2 = self.mw.process_response(req, rsp)
        assert isinstance(req2, Request)
        assert req2.url == url2
        assert req2.method == "GET"
        assert "Content-Type" not in req2.headers, (
            "Content-Type header must not be present in redirected request"
        )
        assert "Content-Length" not in req2.headers, (
            "Content-Length header must not be present in redirected request"
        )
        assert not req2.body, f"Redirected body must be empty, not '{req2.body!r}'"

    def test_max_redirect_times(self):
        self.mw.max_redirect_times = 1
        req = Request("http://a.example/302")
        rsp = self.get_response(req, "/redirected")

        req = self.mw.process_response(req, rsp)
        assert isinstance(req, Request)
        assert "redirect_times" in req.meta
        assert req.meta["redirect_times"] == 1
        with pytest.raises(IgnoreRequest):
            self.mw.process_response(req, rsp)

    def test_ttl(self):
        self.mw.max_redirect_times = 100
        req = Request("http://a.example/302", meta={"redirect_ttl": 1})
        rsp = self.get_response(req, "/a")

        req = self.mw.process_response(req, rsp)
        assert isinstance(req, Request)
        with pytest.raises(IgnoreRequest):
            self.mw.process_response(req, rsp)

    def test_redirect_urls(self):
        req1 = Request("http://a.example/first")
        rsp1 = self.get_response(req1, "/redirected")
        req2 = self.mw.process_response(req1, rsp1)
        rsp2 = self.get_response(req2, "/redirected2")
        req3 = self.mw.process_response(req2, rsp2)

        assert req2.url == "http://a.example/redirected"
        assert req2.meta["redirect_urls"] == ["http://a.example/first"]
        assert req3.url == "http://a.example/redirected2"
        assert req3.meta["redirect_urls"] == [
            "http://a.example/first",
            "http://a.example/redirected",
        ]

    def test_redirect_reasons(self):
        req1 = Request("http://a.example/first")
        rsp1 = self.get_response(req1, "/redirected1")
        req2 = self.mw.process_response(req1, rsp1)
        rsp2 = self.get_response(req2, "/redirected2")
        req3 = self.mw.process_response(req2, rsp2)
        assert req2.meta["redirect_reasons"] == [self.reason]
        assert req3.meta["redirect_reasons"] == [self.reason, self.reason]

    def test_cross_origin_header_dropping(self):
        safe_headers = {"A": "B"}
        cookie_header = {"Cookie": "a=b"}
        authorization_header = {"Authorization": "Bearer 123456"}

        original_request = Request(
            "https://example.com",
            headers=safe_headers | cookie_header | authorization_header,
        )

        # Redirects to the same origin (same scheme, same domain, same port)
        # keep all headers.
        internal_response = self.get_response(original_request, "https://example.com/a")
        internal_redirect_request = self.mw.process_response(
            original_request, internal_response
        )
        assert isinstance(internal_redirect_request, Request)
        assert original_request.headers == internal_redirect_request.headers

        # Redirects to the same origin (same scheme, same domain, same port)
        # keep all headers also when the scheme is http.
        http_request = Request(
            "http://example.com",
            headers=safe_headers | cookie_header | authorization_header,
        )
        http_response = self.get_response(http_request, "http://example.com/a")
        http_redirect_request = self.mw.process_response(http_request, http_response)
        assert isinstance(http_redirect_request, Request)
        assert http_request.headers == http_redirect_request.headers

        # For default ports, whether the port is explicit or implicit does not
        # affect the outcome, it is still the same origin.
        to_explicit_port_response = self.get_response(
            original_request, "https://example.com:443/a"
        )
        to_explicit_port_redirect_request = self.mw.process_response(
            original_request, to_explicit_port_response
        )
        assert isinstance(to_explicit_port_redirect_request, Request)
        assert original_request.headers == to_explicit_port_redirect_request.headers

        # For default ports, whether the port is explicit or implicit does not
        # affect the outcome, it is still the same origin.
        to_implicit_port_response = self.get_response(
            original_request, "https://example.com/a"
        )
        to_implicit_port_redirect_request = self.mw.process_response(
            original_request, to_implicit_port_response
        )
        assert isinstance(to_implicit_port_redirect_request, Request)
        assert original_request.headers == to_implicit_port_redirect_request.headers

        # A port change drops the Authorization header because the origin
        # changes, but keeps the Cookie header because the domain remains the
        # same.
        different_port_response = self.get_response(
            original_request, "https://example.com:8080/a"
        )
        different_port_redirect_request = self.mw.process_response(
            original_request, different_port_response
        )
        assert isinstance(different_port_redirect_request, Request)
        assert {
            **safe_headers,
            **cookie_header,
        } == dict(different_port_redirect_request.headers.to_tuple_list())

        # A domain change drops both the Authorization and the Cookie header.
        external_response = self.get_response(original_request, "https://example.org/a")
        external_redirect_request = self.mw.process_response(
            original_request, external_response
        )
        assert isinstance(external_redirect_request, Request)
        assert safe_headers == dict(external_redirect_request.headers.to_tuple_list())

        # A scheme upgrade (http → https) drops the Authorization header
        # because the origin changes, but keeps the Cookie header because the
        # domain remains the same.
        upgrade_response = self.get_response(http_request, "https://example.com/a")
        upgrade_redirect_request = self.mw.process_response(
            http_request, upgrade_response
        )
        assert isinstance(upgrade_redirect_request, Request)
        assert {
            **safe_headers,
            **cookie_header,
        } == dict(upgrade_redirect_request.headers.to_tuple_list())

        # A scheme downgrade (https → http) drops the Authorization header
        # because the origin changes, and the Cookie header because its value
        # cannot indicate whether the cookies were secure (HTTPS-only) or not.
        #
        # Note: If the Cookie header is set by the cookie management
        # middleware, as recommended in the docs, the dropping of Cookie on
        # scheme downgrade is not an issue, because the cookie management
        # middleware will add again the Cookie header to the new request if
        # appropriate.
        downgrade_response = self.get_response(original_request, "http://example.com/a")
        downgrade_redirect_request = self.mw.process_response(
            original_request, downgrade_response
        )
        assert isinstance(downgrade_redirect_request, Request)
        assert safe_headers == dict(downgrade_redirect_request.headers.to_tuple_list())

    def _check_proxy_scenario(
        self,
        *,
        env: dict[str, str],
        meta: dict[str, Any],
        url: str,
        location1: str,
        location2: str,
        expected: tuple[str | None, ...],
    ) -> None:
        """Send a request through 2 redirects and check its proxy state at 5
        points: after the first HttpProxyMiddleware.process_request() call and,
        for each redirect, after the redirect middleware builds the redirected
        request and after HttpProxyMiddleware.process_request() runs on it.

        Each item of *expected* is a key of PROXIES, or ``None`` for no proxy.
        """
        crawler = get_crawler()
        redirect_mw = build_from_crawler(self.mwcls, crawler)
        with set_environ(**env):
            proxy_mw = build_from_crawler(HttpProxyMiddleware, crawler)

        request1 = Request(url, meta=meta)
        proxy_mw.process_request(request1)
        assert_proxy(request1, expected[0])

        response1 = self.get_response(request1, location1)
        request2 = redirect_mw.process_response(request1, response1)
        assert isinstance(request2, Request)
        assert_proxy(request2, expected[1])
        proxy_mw.process_request(request2)
        assert_proxy(request2, expected[2])

        response2 = self.get_response(request2, location2)
        request3 = redirect_mw.process_response(request2, response2)
        assert isinstance(request3, Request)
        assert_proxy(request3, expected[3])
        proxy_mw.process_request(request3)
        assert_proxy(request3, expected[4])

    # A proxy set through Request.meta is kept on redirects, even on
    # cross-scheme ones.
    @pytest.mark.parametrize(
        ("url", "location1", "location2"),
        [
            pytest.param(
                "http://example.com",
                "http://example.com",
                "http://example.com",
                id="http-absolute",
            ),
            pytest.param("http://example.com", "/a", "/a", id="http-relative"),
            pytest.param(
                "https://example.com",
                "https://example.com",
                "https://example.com",
                id="https-absolute",
            ),
            pytest.param("https://example.com", "/a", "/a", id="https-relative"),
            pytest.param(
                "http://example.com",
                "https://example.com",
                "http://example.com",
                id="http-to-https",
            ),
            pytest.param(
                "https://example.com",
                "http://example.com",
                "https://example.com",
                id="https-to-http",
            ),
        ],
    )
    def test_meta_proxy(self, url: str, location1: str, location2: str) -> None:
        self._check_proxy_scenario(
            env={},
            meta={"proxy": PROXY_A},
            url=url,
            location1=location1,
            location2=location2,
            expected=("a", "a", "a", "a", "a"),
        )

    # A proxy set from the environment is scheme-specific, so a cross-scheme
    # redirect drops it and HttpProxyMiddleware then sets the proxy of the new
    # scheme, if any. Cross-scheme scenarios use proxy a for http and proxy b
    # for https.
    @pytest.mark.parametrize(
        ("env", "url", "location1", "location2", "expected"),
        [
            pytest.param(
                {"http_proxy": PROXY_A},
                "http://example.com",
                "http://example.com",
                "http://example.com",
                ("a", "a", "a", "a", "a"),
                id="http-absolute",
            ),
            pytest.param(
                {"http_proxy": PROXY_A},
                "http://example.com",
                "/a",
                "/a",
                ("a", "a", "a", "a", "a"),
                id="http-relative",
            ),
            pytest.param(
                {"https_proxy": PROXY_A},
                "https://example.com",
                "https://example.com",
                "https://example.com",
                ("a", "a", "a", "a", "a"),
                id="https-absolute",
            ),
            pytest.param(
                {"https_proxy": PROXY_A},
                "https://example.com",
                "/a",
                "/a",
                ("a", "a", "a", "a", "a"),
                id="https-relative",
            ),
            pytest.param(
                {"http_proxy": PROXY_A, "https_proxy": PROXY_B},
                "http://example.com",
                "https://example.com",
                "http://example.com",
                ("a", None, "b", None, "a"),
                id="proxied-http-to-proxied-https",
            ),
            pytest.param(
                {"http_proxy": PROXY_A},
                "http://example.com",
                "https://example.com",
                "http://example.com",
                ("a", None, None, None, "a"),
                id="proxied-http-to-unproxied-https",
            ),
            pytest.param(
                {"https_proxy": PROXY_B},
                "http://example.com",
                "https://example.com",
                "http://example.com",
                (None, None, "b", None, None),
                id="unproxied-http-to-proxied-https",
            ),
            pytest.param(
                {},
                "http://example.com",
                "https://example.com",
                "http://example.com",
                (None, None, None, None, None),
                id="unproxied-http-to-unproxied-https",
            ),
            pytest.param(
                {"http_proxy": PROXY_A, "https_proxy": PROXY_B},
                "https://example.com",
                "http://example.com",
                "https://example.com",
                ("b", None, "a", None, "b"),
                id="proxied-https-to-proxied-http",
            ),
            pytest.param(
                {"https_proxy": PROXY_B},
                "https://example.com",
                "http://example.com",
                "https://example.com",
                ("b", None, None, None, "b"),
                id="proxied-https-to-unproxied-http",
            ),
            pytest.param(
                {"http_proxy": PROXY_A},
                "https://example.com",
                "http://example.com",
                "https://example.com",
                (None, None, "a", None, None),
                id="unproxied-https-to-proxied-http",
            ),
            pytest.param(
                {},
                "https://example.com",
                "http://example.com",
                "https://example.com",
                (None, None, None, None, None),
                id="unproxied-https-to-unproxied-http",
            ),
        ],
    )
    def test_system_proxy(
        self,
        env: dict[str, str],
        url: str,
        location1: str,
        location2: str,
        expected: tuple[str | None, ...],
    ) -> None:
        self._check_proxy_scenario(
            env=env,
            meta={},
            url=url,
            location1=location1,
            location2=location2,
            expected=expected,
        )
