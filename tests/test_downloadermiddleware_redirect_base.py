from __future__ import annotations

from itertools import product

import pytest

from scrapy.downloadermiddlewares.httpproxy import HttpProxyMiddleware
from scrapy.exceptions import IgnoreRequest
from scrapy.http import Request, Response
from scrapy.utils.misc import set_environ
from scrapy.utils.test import get_crawler

SCHEME_PARAMS = ("url", "location", "target")
HTTP_SCHEMES = ("http", "https")
NON_HTTP_SCHEMES = ("data", "file", "ftp", "s3", "foo")
REDIRECT_SCHEME_CASES = (
    # http/https → http/https redirects
    *(
        (
            f"{input_scheme}://example.com/a",
            f"{output_scheme}://example.com/b",
            f"{output_scheme}://example.com/b",
        )
        for input_scheme, output_scheme in product(HTTP_SCHEMES, repeat=2)
    ),
    # http/https → data/file/ftp/s3/foo does not redirect
    *(
        (
            f"{input_scheme}://example.com/a",
            f"{output_scheme}://example.com/b",
            None,
        )
        for input_scheme in HTTP_SCHEMES
        for output_scheme in NON_HTTP_SCHEMES
    ),
    # http/https → relative redirects
    *(
        (
            f"{scheme}://example.com/a",
            location,
            f"{scheme}://example.com/b",
        )
        for scheme in HTTP_SCHEMES
        for location in ("//example.com/b", "/b")
    ),
    # Note: We do not test data/file/ftp/s3 schemes for the initial URL
    # because their download handlers cannot return a status code of 3xx.
)


class Base:
    class Test:
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
            assert not req2.body, f"Redirected body must be empty, not '{req2.body}'"

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
            rsp2 = self.get_response(req1, "/redirected2")
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
                headers={**safe_headers, **cookie_header, **authorization_header},
            )

            # Redirects to the same origin (same scheme, same domain, same port)
            # keep all headers.
            internal_response = self.get_response(
                original_request, "https://example.com/a"
            )
            internal_redirect_request = self.mw.process_response(
                original_request, internal_response
            )
            assert isinstance(internal_redirect_request, Request)
            assert original_request.headers == internal_redirect_request.headers

            # Redirects to the same origin (same scheme, same domain, same port)
            # keep all headers also when the scheme is http.
            http_request = Request(
                "http://example.com",
                headers={**safe_headers, **cookie_header, **authorization_header},
            )
            http_response = self.get_response(http_request, "http://example.com/a")
            http_redirect_request = self.mw.process_response(
                http_request, http_response
            )
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
            } == different_port_redirect_request.headers.to_unicode_dict()

            # A domain change drops both the Authorization and the Cookie header.
            external_response = self.get_response(
                original_request, "https://example.org/a"
            )
            external_redirect_request = self.mw.process_response(
                original_request, external_response
            )
            assert isinstance(external_redirect_request, Request)
            assert safe_headers == external_redirect_request.headers.to_unicode_dict()

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
            } == upgrade_redirect_request.headers.to_unicode_dict()

            # A scheme downgrade (https → http) drops the Authorization header
            # because the origin changes, and the Cookie header because its value
            # cannot indicate whether the cookies were secure (HTTPS-only) or not.
            #
            # Note: If the Cookie header is set by the cookie management
            # middleware, as recommended in the docs, the dropping of Cookie on
            # scheme downgrade is not an issue, because the cookie management
            # middleware will add again the Cookie header to the new request if
            # appropriate.
            downgrade_response = self.get_response(
                original_request, "http://example.com/a"
            )
            downgrade_redirect_request = self.mw.process_response(
                original_request, downgrade_response
            )
            assert isinstance(downgrade_redirect_request, Request)
            assert safe_headers == downgrade_redirect_request.headers.to_unicode_dict()

        def test_meta_proxy_http_absolute(self):
            crawler = get_crawler()
            redirect_mw = self.mwcls.from_crawler(crawler)
            proxy_mw = HttpProxyMiddleware.from_crawler(crawler)

            meta = {"proxy": "https://a:@a.example"}
            request1 = Request("http://example.com", meta=meta)
            proxy_mw.process_request(request1)

            assert request1.headers["Proxy-Authorization"] == b"Basic YTo="
            assert request1.meta["_auth_proxy"] == "https://a.example"
            assert request1.meta["proxy"] == "https://a.example"

            response1 = self.get_response(request1, "http://example.com")
            request2 = redirect_mw.process_response(request1, response1)

            assert isinstance(request2, Request)
            assert request2.headers["Proxy-Authorization"] == b"Basic YTo="
            assert request2.meta["_auth_proxy"] == "https://a.example"
            assert request2.meta["proxy"] == "https://a.example"

            proxy_mw.process_request(request2)

            assert request2.headers["Proxy-Authorization"] == b"Basic YTo="
            assert request2.meta["_auth_proxy"] == "https://a.example"
            assert request2.meta["proxy"] == "https://a.example"

            response2 = self.get_response(request2, "http://example.com")
            request3 = redirect_mw.process_response(request2, response2)

            assert isinstance(request3, Request)
            assert request3.headers["Proxy-Authorization"] == b"Basic YTo="
            assert request3.meta["_auth_proxy"] == "https://a.example"
            assert request3.meta["proxy"] == "https://a.example"

            proxy_mw.process_request(request3)

            assert request3.headers["Proxy-Authorization"] == b"Basic YTo="
            assert request3.meta["_auth_proxy"] == "https://a.example"
            assert request3.meta["proxy"] == "https://a.example"

        def test_meta_proxy_http_relative(self):
            crawler = get_crawler()
            redirect_mw = self.mwcls.from_crawler(crawler)
            proxy_mw = HttpProxyMiddleware.from_crawler(crawler)

            meta = {"proxy": "https://a:@a.example"}
            request1 = Request("http://example.com", meta=meta)
            proxy_mw.process_request(request1)

            assert request1.headers["Proxy-Authorization"] == b"Basic YTo="
            assert request1.meta["_auth_proxy"] == "https://a.example"
            assert request1.meta["proxy"] == "https://a.example"

            response1 = self.get_response(request1, "/a")
            request2 = redirect_mw.process_response(request1, response1)

            assert isinstance(request2, Request)
            assert request2.headers["Proxy-Authorization"] == b"Basic YTo="
            assert request2.meta["_auth_proxy"] == "https://a.example"
            assert request2.meta["proxy"] == "https://a.example"

            proxy_mw.process_request(request2)

            assert request2.headers["Proxy-Authorization"] == b"Basic YTo="
            assert request2.meta["_auth_proxy"] == "https://a.example"
            assert request2.meta["proxy"] == "https://a.example"

            response2 = self.get_response(request2, "/a")
            request3 = redirect_mw.process_response(request2, response2)

            assert isinstance(request3, Request)
            assert request3.headers["Proxy-Authorization"] == b"Basic YTo="
            assert request3.meta["_auth_proxy"] == "https://a.example"
            assert request3.meta["proxy"] == "https://a.example"

            proxy_mw.process_request(request3)

            assert request3.headers["Proxy-Authorization"] == b"Basic YTo="
            assert request3.meta["_auth_proxy"] == "https://a.example"
            assert request3.meta["proxy"] == "https://a.example"

        def test_meta_proxy_https_absolute(self):
            crawler = get_crawler()
            redirect_mw = self.mwcls.from_crawler(crawler)
            proxy_mw = HttpProxyMiddleware.from_crawler(crawler)

            meta = {"proxy": "https://a:@a.example"}
            request1 = Request("https://example.com", meta=meta)
            proxy_mw.process_request(request1)

            assert request1.headers["Proxy-Authorization"] == b"Basic YTo="
            assert request1.meta["_auth_proxy"] == "https://a.example"
            assert request1.meta["proxy"] == "https://a.example"

            response1 = self.get_response(request1, "https://example.com")
            request2 = redirect_mw.process_response(request1, response1)

            assert isinstance(request2, Request)
            assert request2.headers["Proxy-Authorization"] == b"Basic YTo="
            assert request2.meta["_auth_proxy"] == "https://a.example"
            assert request2.meta["proxy"] == "https://a.example"

            proxy_mw.process_request(request2)

            assert request2.headers["Proxy-Authorization"] == b"Basic YTo="
            assert request2.meta["_auth_proxy"] == "https://a.example"
            assert request2.meta["proxy"] == "https://a.example"

            response2 = self.get_response(request2, "https://example.com")
            request3 = redirect_mw.process_response(request2, response2)

            assert isinstance(request3, Request)
            assert request3.headers["Proxy-Authorization"] == b"Basic YTo="
            assert request3.meta["_auth_proxy"] == "https://a.example"
            assert request3.meta["proxy"] == "https://a.example"

            proxy_mw.process_request(request3)

            assert request3.headers["Proxy-Authorization"] == b"Basic YTo="
            assert request3.meta["_auth_proxy"] == "https://a.example"
            assert request3.meta["proxy"] == "https://a.example"

        def test_meta_proxy_https_relative(self):
            crawler = get_crawler()
            redirect_mw = self.mwcls.from_crawler(crawler)
            proxy_mw = HttpProxyMiddleware.from_crawler(crawler)

            meta = {"proxy": "https://a:@a.example"}
            request1 = Request("https://example.com", meta=meta)
            proxy_mw.process_request(request1)

            assert request1.headers["Proxy-Authorization"] == b"Basic YTo="
            assert request1.meta["_auth_proxy"] == "https://a.example"
            assert request1.meta["proxy"] == "https://a.example"

            response1 = self.get_response(request1, "/a")
            request2 = redirect_mw.process_response(request1, response1)

            assert isinstance(request2, Request)
            assert request2.headers["Proxy-Authorization"] == b"Basic YTo="
            assert request2.meta["_auth_proxy"] == "https://a.example"
            assert request2.meta["proxy"] == "https://a.example"

            proxy_mw.process_request(request2)

            assert request2.headers["Proxy-Authorization"] == b"Basic YTo="
            assert request2.meta["_auth_proxy"] == "https://a.example"
            assert request2.meta["proxy"] == "https://a.example"

            response2 = self.get_response(request2, "/a")
            request3 = redirect_mw.process_response(request2, response2)

            assert isinstance(request3, Request)
            assert request3.headers["Proxy-Authorization"] == b"Basic YTo="
            assert request3.meta["_auth_proxy"] == "https://a.example"
            assert request3.meta["proxy"] == "https://a.example"

            proxy_mw.process_request(request3)

            assert request3.headers["Proxy-Authorization"] == b"Basic YTo="
            assert request3.meta["_auth_proxy"] == "https://a.example"
            assert request3.meta["proxy"] == "https://a.example"

        def test_meta_proxy_http_to_https(self):
            crawler = get_crawler()
            redirect_mw = self.mwcls.from_crawler(crawler)
            proxy_mw = HttpProxyMiddleware.from_crawler(crawler)

            meta = {"proxy": "https://a:@a.example"}
            request1 = Request("http://example.com", meta=meta)
            proxy_mw.process_request(request1)

            assert request1.headers["Proxy-Authorization"] == b"Basic YTo="
            assert request1.meta["_auth_proxy"] == "https://a.example"
            assert request1.meta["proxy"] == "https://a.example"

            response1 = self.get_response(request1, "https://example.com")
            request2 = redirect_mw.process_response(request1, response1)

            assert isinstance(request2, Request)
            assert request2.headers["Proxy-Authorization"] == b"Basic YTo="
            assert request2.meta["_auth_proxy"] == "https://a.example"
            assert request2.meta["proxy"] == "https://a.example"

            proxy_mw.process_request(request2)

            assert request2.headers["Proxy-Authorization"] == b"Basic YTo="
            assert request2.meta["_auth_proxy"] == "https://a.example"
            assert request2.meta["proxy"] == "https://a.example"

            response2 = self.get_response(request2, "http://example.com")
            request3 = redirect_mw.process_response(request2, response2)

            assert isinstance(request3, Request)
            assert request3.headers["Proxy-Authorization"] == b"Basic YTo="
            assert request3.meta["_auth_proxy"] == "https://a.example"
            assert request3.meta["proxy"] == "https://a.example"

            proxy_mw.process_request(request3)

            assert request3.headers["Proxy-Authorization"] == b"Basic YTo="
            assert request3.meta["_auth_proxy"] == "https://a.example"
            assert request3.meta["proxy"] == "https://a.example"

        def test_meta_proxy_https_to_http(self):
            crawler = get_crawler()
            redirect_mw = self.mwcls.from_crawler(crawler)
            proxy_mw = HttpProxyMiddleware.from_crawler(crawler)

            meta = {"proxy": "https://a:@a.example"}
            request1 = Request("https://example.com", meta=meta)
            proxy_mw.process_request(request1)

            assert request1.headers["Proxy-Authorization"] == b"Basic YTo="
            assert request1.meta["_auth_proxy"] == "https://a.example"
            assert request1.meta["proxy"] == "https://a.example"

            response1 = self.get_response(request1, "http://example.com")
            request2 = redirect_mw.process_response(request1, response1)

            assert isinstance(request2, Request)
            assert request2.headers["Proxy-Authorization"] == b"Basic YTo="
            assert request2.meta["_auth_proxy"] == "https://a.example"
            assert request2.meta["proxy"] == "https://a.example"

            proxy_mw.process_request(request2)

            assert request2.headers["Proxy-Authorization"] == b"Basic YTo="
            assert request2.meta["_auth_proxy"] == "https://a.example"
            assert request2.meta["proxy"] == "https://a.example"

            response2 = self.get_response(request2, "https://example.com")
            request3 = redirect_mw.process_response(request2, response2)

            assert isinstance(request3, Request)
            assert request3.headers["Proxy-Authorization"] == b"Basic YTo="
            assert request3.meta["_auth_proxy"] == "https://a.example"
            assert request3.meta["proxy"] == "https://a.example"

            proxy_mw.process_request(request3)

            assert request3.headers["Proxy-Authorization"] == b"Basic YTo="
            assert request3.meta["_auth_proxy"] == "https://a.example"
            assert request3.meta["proxy"] == "https://a.example"

        def test_system_proxy_http_absolute(self):
            crawler = get_crawler()
            redirect_mw = self.mwcls.from_crawler(crawler)
            env = {
                "http_proxy": "https://a:@a.example",
            }
            with set_environ(**env):
                proxy_mw = HttpProxyMiddleware.from_crawler(crawler)

            request1 = Request("http://example.com")
            proxy_mw.process_request(request1)

            assert request1.headers["Proxy-Authorization"] == b"Basic YTo="
            assert request1.meta["_auth_proxy"] == "https://a.example"
            assert request1.meta["proxy"] == "https://a.example"

            response1 = self.get_response(request1, "http://example.com")
            request2 = redirect_mw.process_response(request1, response1)

            assert isinstance(request2, Request)
            assert request2.headers["Proxy-Authorization"] == b"Basic YTo="
            assert request2.meta["_auth_proxy"] == "https://a.example"
            assert request2.meta["proxy"] == "https://a.example"

            proxy_mw.process_request(request2)

            assert request2.headers["Proxy-Authorization"] == b"Basic YTo="
            assert request2.meta["_auth_proxy"] == "https://a.example"
            assert request2.meta["proxy"] == "https://a.example"

            response2 = self.get_response(request2, "http://example.com")
            request3 = redirect_mw.process_response(request2, response2)

            assert isinstance(request3, Request)
            assert request3.headers["Proxy-Authorization"] == b"Basic YTo="
            assert request3.meta["_auth_proxy"] == "https://a.example"
            assert request3.meta["proxy"] == "https://a.example"

            proxy_mw.process_request(request3)

            assert request3.headers["Proxy-Authorization"] == b"Basic YTo="
            assert request3.meta["_auth_proxy"] == "https://a.example"
            assert request3.meta["proxy"] == "https://a.example"

        def test_system_proxy_http_relative(self):
            crawler = get_crawler()
            redirect_mw = self.mwcls.from_crawler(crawler)
            env = {
                "http_proxy": "https://a:@a.example",
            }
            with set_environ(**env):
                proxy_mw = HttpProxyMiddleware.from_crawler(crawler)

            request1 = Request("http://example.com")
            proxy_mw.process_request(request1)

            assert request1.headers["Proxy-Authorization"] == b"Basic YTo="
            assert request1.meta["_auth_proxy"] == "https://a.example"
            assert request1.meta["proxy"] == "https://a.example"

            response1 = self.get_response(request1, "/a")
            request2 = redirect_mw.process_response(request1, response1)

            assert isinstance(request2, Request)
            assert request2.headers["Proxy-Authorization"] == b"Basic YTo="
            assert request2.meta["_auth_proxy"] == "https://a.example"
            assert request2.meta["proxy"] == "https://a.example"

            proxy_mw.process_request(request2)

            assert request2.headers["Proxy-Authorization"] == b"Basic YTo="
            assert request2.meta["_auth_proxy"] == "https://a.example"
            assert request2.meta["proxy"] == "https://a.example"

            response2 = self.get_response(request2, "/a")
            request3 = redirect_mw.process_response(request2, response2)

            assert isinstance(request3, Request)
            assert request3.headers["Proxy-Authorization"] == b"Basic YTo="
            assert request3.meta["_auth_proxy"] == "https://a.example"
            assert request3.meta["proxy"] == "https://a.example"

            proxy_mw.process_request(request3)

            assert request3.headers["Proxy-Authorization"] == b"Basic YTo="
            assert request3.meta["_auth_proxy"] == "https://a.example"
            assert request3.meta["proxy"] == "https://a.example"

        def test_system_proxy_https_absolute(self):
            crawler = get_crawler()
            redirect_mw = self.mwcls.from_crawler(crawler)
            env = {
                "https_proxy": "https://a:@a.example",
            }
            with set_environ(**env):
                proxy_mw = HttpProxyMiddleware.from_crawler(crawler)

            request1 = Request("https://example.com")
            proxy_mw.process_request(request1)

            assert request1.headers["Proxy-Authorization"] == b"Basic YTo="
            assert request1.meta["_auth_proxy"] == "https://a.example"
            assert request1.meta["proxy"] == "https://a.example"

            response1 = self.get_response(request1, "https://example.com")
            request2 = redirect_mw.process_response(request1, response1)

            assert isinstance(request2, Request)
            assert request2.headers["Proxy-Authorization"] == b"Basic YTo="
            assert request2.meta["_auth_proxy"] == "https://a.example"
            assert request2.meta["proxy"] == "https://a.example"

            proxy_mw.process_request(request2)

            assert request2.headers["Proxy-Authorization"] == b"Basic YTo="
            assert request2.meta["_auth_proxy"] == "https://a.example"
            assert request2.meta["proxy"] == "https://a.example"

            response2 = self.get_response(request2, "https://example.com")
            request3 = redirect_mw.process_response(request2, response2)

            assert isinstance(request3, Request)
            assert request3.headers["Proxy-Authorization"] == b"Basic YTo="
            assert request3.meta["_auth_proxy"] == "https://a.example"
            assert request3.meta["proxy"] == "https://a.example"

            proxy_mw.process_request(request3)

            assert request3.headers["Proxy-Authorization"] == b"Basic YTo="
            assert request3.meta["_auth_proxy"] == "https://a.example"
            assert request3.meta["proxy"] == "https://a.example"

        def test_system_proxy_https_relative(self):
            crawler = get_crawler()
            redirect_mw = self.mwcls.from_crawler(crawler)
            env = {
                "https_proxy": "https://a:@a.example",
            }
            with set_environ(**env):
                proxy_mw = HttpProxyMiddleware.from_crawler(crawler)

            request1 = Request("https://example.com")
            proxy_mw.process_request(request1)

            assert request1.headers["Proxy-Authorization"] == b"Basic YTo="
            assert request1.meta["_auth_proxy"] == "https://a.example"
            assert request1.meta["proxy"] == "https://a.example"

            response1 = self.get_response(request1, "/a")
            request2 = redirect_mw.process_response(request1, response1)

            assert isinstance(request2, Request)
            assert request2.headers["Proxy-Authorization"] == b"Basic YTo="
            assert request2.meta["_auth_proxy"] == "https://a.example"
            assert request2.meta["proxy"] == "https://a.example"

            proxy_mw.process_request(request2)

            assert request2.headers["Proxy-Authorization"] == b"Basic YTo="
            assert request2.meta["_auth_proxy"] == "https://a.example"
            assert request2.meta["proxy"] == "https://a.example"

            response2 = self.get_response(request2, "/a")
            request3 = redirect_mw.process_response(request2, response2)

            assert isinstance(request3, Request)
            assert request3.headers["Proxy-Authorization"] == b"Basic YTo="
            assert request3.meta["_auth_proxy"] == "https://a.example"
            assert request3.meta["proxy"] == "https://a.example"

            proxy_mw.process_request(request3)

            assert request3.headers["Proxy-Authorization"] == b"Basic YTo="
            assert request3.meta["_auth_proxy"] == "https://a.example"
            assert request3.meta["proxy"] == "https://a.example"

        def test_system_proxy_proxied_http_to_proxied_https(self):
            crawler = get_crawler()
            redirect_mw = self.mwcls.from_crawler(crawler)
            env = {
                "http_proxy": "https://a:@a.example",
                "https_proxy": "https://b:@b.example",
            }
            with set_environ(**env):
                proxy_mw = HttpProxyMiddleware.from_crawler(crawler)

            request1 = Request("http://example.com")
            proxy_mw.process_request(request1)

            assert request1.headers["Proxy-Authorization"] == b"Basic YTo="
            assert request1.meta["_auth_proxy"] == "https://a.example"
            assert request1.meta["proxy"] == "https://a.example"

            response1 = self.get_response(request1, "https://example.com")
            request2 = redirect_mw.process_response(request1, response1)

            assert isinstance(request2, Request)
            assert "Proxy-Authorization" not in request2.headers
            assert "_auth_proxy" not in request2.meta
            assert "proxy" not in request2.meta

            proxy_mw.process_request(request2)

            assert request2.headers["Proxy-Authorization"] == b"Basic Yjo="
            assert request2.meta["_auth_proxy"] == "https://b.example"
            assert request2.meta["proxy"] == "https://b.example"

            response2 = self.get_response(request2, "http://example.com")
            request3 = redirect_mw.process_response(request2, response2)

            assert isinstance(request3, Request)
            assert "Proxy-Authorization" not in request3.headers
            assert "_auth_proxy" not in request3.meta
            assert "proxy" not in request3.meta

            proxy_mw.process_request(request3)

            assert request3.headers["Proxy-Authorization"] == b"Basic YTo="
            assert request3.meta["_auth_proxy"] == "https://a.example"
            assert request3.meta["proxy"] == "https://a.example"

        def test_system_proxy_proxied_http_to_unproxied_https(self):
            crawler = get_crawler()
            redirect_mw = self.mwcls.from_crawler(crawler)
            env = {
                "http_proxy": "https://a:@a.example",
            }
            with set_environ(**env):
                proxy_mw = HttpProxyMiddleware.from_crawler(crawler)

            request1 = Request("http://example.com")
            proxy_mw.process_request(request1)

            assert request1.headers["Proxy-Authorization"] == b"Basic YTo="
            assert request1.meta["_auth_proxy"] == "https://a.example"
            assert request1.meta["proxy"] == "https://a.example"

            response1 = self.get_response(request1, "https://example.com")
            request2 = redirect_mw.process_response(request1, response1)

            assert isinstance(request2, Request)
            assert "Proxy-Authorization" not in request2.headers
            assert "_auth_proxy" not in request2.meta
            assert "proxy" not in request2.meta

            proxy_mw.process_request(request2)

            assert "Proxy-Authorization" not in request2.headers
            assert "_auth_proxy" not in request2.meta
            assert "proxy" not in request2.meta

            response2 = self.get_response(request2, "http://example.com")
            request3 = redirect_mw.process_response(request2, response2)

            assert isinstance(request3, Request)
            assert "Proxy-Authorization" not in request3.headers
            assert "_auth_proxy" not in request3.meta
            assert "proxy" not in request3.meta

            proxy_mw.process_request(request3)

            assert request3.headers["Proxy-Authorization"] == b"Basic YTo="
            assert request3.meta["_auth_proxy"] == "https://a.example"
            assert request3.meta["proxy"] == "https://a.example"

        def test_system_proxy_unproxied_http_to_proxied_https(self):
            crawler = get_crawler()
            redirect_mw = self.mwcls.from_crawler(crawler)
            env = {
                "https_proxy": "https://b:@b.example",
            }
            with set_environ(**env):
                proxy_mw = HttpProxyMiddleware.from_crawler(crawler)

            request1 = Request("http://example.com")
            proxy_mw.process_request(request1)

            assert "Proxy-Authorization" not in request1.headers
            assert "_auth_proxy" not in request1.meta
            assert "proxy" not in request1.meta

            response1 = self.get_response(request1, "https://example.com")
            request2 = redirect_mw.process_response(request1, response1)

            assert isinstance(request2, Request)
            assert "Proxy-Authorization" not in request2.headers
            assert "_auth_proxy" not in request2.meta
            assert "proxy" not in request2.meta

            proxy_mw.process_request(request2)

            assert request2.headers["Proxy-Authorization"] == b"Basic Yjo="
            assert request2.meta["_auth_proxy"] == "https://b.example"
            assert request2.meta["proxy"] == "https://b.example"

            response2 = self.get_response(request2, "http://example.com")
            request3 = redirect_mw.process_response(request2, response2)

            assert isinstance(request3, Request)
            assert "Proxy-Authorization" not in request3.headers
            assert "_auth_proxy" not in request3.meta
            assert "proxy" not in request3.meta

            proxy_mw.process_request(request3)

            assert "Proxy-Authorization" not in request3.headers
            assert "_auth_proxy" not in request3.meta
            assert "proxy" not in request3.meta

        def test_system_proxy_unproxied_http_to_unproxied_https(self):
            crawler = get_crawler()
            redirect_mw = self.mwcls.from_crawler(crawler)
            proxy_mw = HttpProxyMiddleware.from_crawler(crawler)

            request1 = Request("http://example.com")
            proxy_mw.process_request(request1)

            assert "Proxy-Authorization" not in request1.headers
            assert "_auth_proxy" not in request1.meta
            assert "proxy" not in request1.meta

            response1 = self.get_response(request1, "https://example.com")
            request2 = redirect_mw.process_response(request1, response1)

            assert isinstance(request2, Request)
            assert "Proxy-Authorization" not in request2.headers
            assert "_auth_proxy" not in request2.meta
            assert "proxy" not in request2.meta

            proxy_mw.process_request(request2)

            assert "Proxy-Authorization" not in request2.headers
            assert "_auth_proxy" not in request2.meta
            assert "proxy" not in request2.meta

            response2 = self.get_response(request2, "http://example.com")
            request3 = redirect_mw.process_response(request2, response2)

            assert isinstance(request3, Request)
            assert "Proxy-Authorization" not in request3.headers
            assert "_auth_proxy" not in request3.meta
            assert "proxy" not in request3.meta

            proxy_mw.process_request(request3)

            assert "Proxy-Authorization" not in request3.headers
            assert "_auth_proxy" not in request3.meta
            assert "proxy" not in request3.meta

        def test_system_proxy_proxied_https_to_proxied_http(self):
            crawler = get_crawler()
            redirect_mw = self.mwcls.from_crawler(crawler)
            env = {
                "http_proxy": "https://a:@a.example",
                "https_proxy": "https://b:@b.example",
            }
            with set_environ(**env):
                proxy_mw = HttpProxyMiddleware.from_crawler(crawler)

            request1 = Request("https://example.com")
            proxy_mw.process_request(request1)

            assert request1.headers["Proxy-Authorization"] == b"Basic Yjo="
            assert request1.meta["_auth_proxy"] == "https://b.example"
            assert request1.meta["proxy"] == "https://b.example"

            response1 = self.get_response(request1, "http://example.com")
            request2 = redirect_mw.process_response(request1, response1)

            assert isinstance(request2, Request)
            assert "Proxy-Authorization" not in request2.headers
            assert "_auth_proxy" not in request2.meta
            assert "proxy" not in request2.meta

            proxy_mw.process_request(request2)

            assert request2.headers["Proxy-Authorization"] == b"Basic YTo="
            assert request2.meta["_auth_proxy"] == "https://a.example"
            assert request2.meta["proxy"] == "https://a.example"

            response2 = self.get_response(request2, "https://example.com")
            request3 = redirect_mw.process_response(request2, response2)

            assert isinstance(request3, Request)
            assert "Proxy-Authorization" not in request3.headers
            assert "_auth_proxy" not in request3.meta
            assert "proxy" not in request3.meta

            proxy_mw.process_request(request3)

            assert request3.headers["Proxy-Authorization"] == b"Basic Yjo="
            assert request3.meta["_auth_proxy"] == "https://b.example"
            assert request3.meta["proxy"] == "https://b.example"

        def test_system_proxy_proxied_https_to_unproxied_http(self):
            crawler = get_crawler()
            redirect_mw = self.mwcls.from_crawler(crawler)
            env = {
                "https_proxy": "https://b:@b.example",
            }
            with set_environ(**env):
                proxy_mw = HttpProxyMiddleware.from_crawler(crawler)

            request1 = Request("https://example.com")
            proxy_mw.process_request(request1)

            assert request1.headers["Proxy-Authorization"] == b"Basic Yjo="
            assert request1.meta["_auth_proxy"] == "https://b.example"
            assert request1.meta["proxy"] == "https://b.example"

            response1 = self.get_response(request1, "http://example.com")
            request2 = redirect_mw.process_response(request1, response1)

            assert isinstance(request2, Request)
            assert "Proxy-Authorization" not in request2.headers
            assert "_auth_proxy" not in request2.meta
            assert "proxy" not in request2.meta

            proxy_mw.process_request(request2)

            assert "Proxy-Authorization" not in request2.headers
            assert "_auth_proxy" not in request2.meta
            assert "proxy" not in request2.meta

            response2 = self.get_response(request2, "https://example.com")
            request3 = redirect_mw.process_response(request2, response2)

            assert isinstance(request3, Request)
            assert "Proxy-Authorization" not in request3.headers
            assert "_auth_proxy" not in request3.meta
            assert "proxy" not in request3.meta

            proxy_mw.process_request(request3)

            assert request3.headers["Proxy-Authorization"] == b"Basic Yjo="
            assert request3.meta["_auth_proxy"] == "https://b.example"
            assert request3.meta["proxy"] == "https://b.example"

        def test_system_proxy_unproxied_https_to_proxied_http(self):
            crawler = get_crawler()
            redirect_mw = self.mwcls.from_crawler(crawler)
            env = {
                "http_proxy": "https://a:@a.example",
            }
            with set_environ(**env):
                proxy_mw = HttpProxyMiddleware.from_crawler(crawler)

            request1 = Request("https://example.com")
            proxy_mw.process_request(request1)

            assert "Proxy-Authorization" not in request1.headers
            assert "_auth_proxy" not in request1.meta
            assert "proxy" not in request1.meta

            response1 = self.get_response(request1, "http://example.com")
            request2 = redirect_mw.process_response(request1, response1)

            assert isinstance(request2, Request)
            assert "Proxy-Authorization" not in request2.headers
            assert "_auth_proxy" not in request2.meta
            assert "proxy" not in request2.meta

            proxy_mw.process_request(request2)

            assert request2.headers["Proxy-Authorization"] == b"Basic YTo="
            assert request2.meta["_auth_proxy"] == "https://a.example"
            assert request2.meta["proxy"] == "https://a.example"

            response2 = self.get_response(request2, "https://example.com")
            request3 = redirect_mw.process_response(request2, response2)

            assert isinstance(request3, Request)
            assert "Proxy-Authorization" not in request3.headers
            assert "_auth_proxy" not in request3.meta
            assert "proxy" not in request3.meta

            proxy_mw.process_request(request3)

            assert "Proxy-Authorization" not in request3.headers
            assert "_auth_proxy" not in request3.meta
            assert "proxy" not in request3.meta

        def test_system_proxy_unproxied_https_to_unproxied_http(self):
            crawler = get_crawler()
            redirect_mw = self.mwcls.from_crawler(crawler)
            proxy_mw = HttpProxyMiddleware.from_crawler(crawler)

            request1 = Request("https://example.com")
            proxy_mw.process_request(request1)

            assert "Proxy-Authorization" not in request1.headers
            assert "_auth_proxy" not in request1.meta
            assert "proxy" not in request1.meta

            response1 = self.get_response(request1, "http://example.com")
            request2 = redirect_mw.process_response(request1, response1)

            assert isinstance(request2, Request)
            assert "Proxy-Authorization" not in request2.headers
            assert "_auth_proxy" not in request2.meta
            assert "proxy" not in request2.meta

            proxy_mw.process_request(request2)

            assert "Proxy-Authorization" not in request2.headers
            assert "_auth_proxy" not in request2.meta
            assert "proxy" not in request2.meta

            response2 = self.get_response(request2, "https://example.com")
            request3 = redirect_mw.process_response(request2, response2)

            assert isinstance(request3, Request)
            assert "Proxy-Authorization" not in request3.headers
            assert "_auth_proxy" not in request3.meta
            assert "proxy" not in request3.meta

            proxy_mw.process_request(request3)

            assert "Proxy-Authorization" not in request3.headers
            assert "_auth_proxy" not in request3.meta
            assert "proxy" not in request3.meta
