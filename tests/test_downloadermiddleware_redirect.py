import unittest
from itertools import chain, product

import pytest

from scrapy.downloadermiddlewares.httpproxy import HttpProxyMiddleware
from scrapy.downloadermiddlewares.redirect import (
    MetaRefreshMiddleware,
    RedirectMiddleware,
)
from scrapy.exceptions import IgnoreRequest
from scrapy.http import HtmlResponse, Request, Response
from scrapy.spiders import Spider
from scrapy.utils.misc import set_environ
from scrapy.utils.test import get_crawler


class Base:
    class Test(unittest.TestCase):
        def test_priority_adjust(self):
            req = Request("http://a.com")
            rsp = self.get_response(req, "http://a.com/redirected")
            req2 = self.mw.process_response(req, rsp, self.spider)
            self.assertGreater(req2.priority, req.priority)

        def test_dont_redirect(self):
            url = "http://www.example.com/301"
            url2 = "http://www.example.com/redirected"
            req = Request(url, meta={"dont_redirect": True})
            rsp = self.get_response(req, url2)

            r = self.mw.process_response(req, rsp, self.spider)
            assert isinstance(r, Response)
            assert r is rsp

            # Test that it redirects when dont_redirect is False
            req = Request(url, meta={"dont_redirect": False})
            rsp = self.get_response(req, url2)

            r = self.mw.process_response(req, rsp, self.spider)
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

            req2 = self.mw.process_response(req, rsp, self.spider)
            assert isinstance(req2, Request)
            self.assertEqual(req2.url, url2)
            self.assertEqual(req2.method, "GET")
            assert (
                "Content-Type" not in req2.headers
            ), "Content-Type header must not be present in redirected request"
            assert (
                "Content-Length" not in req2.headers
            ), "Content-Length header must not be present in redirected request"
            assert not req2.body, f"Redirected body must be empty, not '{req2.body}'"

        def test_max_redirect_times(self):
            self.mw.max_redirect_times = 1
            req = Request("http://scrapytest.org/302")
            rsp = self.get_response(req, "/redirected")

            req = self.mw.process_response(req, rsp, self.spider)
            assert isinstance(req, Request)
            assert "redirect_times" in req.meta
            self.assertEqual(req.meta["redirect_times"], 1)
            self.assertRaises(
                IgnoreRequest, self.mw.process_response, req, rsp, self.spider
            )

        def test_ttl(self):
            self.mw.max_redirect_times = 100
            req = Request("http://scrapytest.org/302", meta={"redirect_ttl": 1})
            rsp = self.get_response(req, "/a")

            req = self.mw.process_response(req, rsp, self.spider)
            assert isinstance(req, Request)
            self.assertRaises(
                IgnoreRequest, self.mw.process_response, req, rsp, self.spider
            )

        def test_redirect_urls(self):
            req1 = Request("http://scrapytest.org/first")
            rsp1 = self.get_response(req1, "/redirected")
            req2 = self.mw.process_response(req1, rsp1, self.spider)
            rsp2 = self.get_response(req1, "/redirected2")
            req3 = self.mw.process_response(req2, rsp2, self.spider)

            self.assertEqual(req2.url, "http://scrapytest.org/redirected")
            self.assertEqual(
                req2.meta["redirect_urls"], ["http://scrapytest.org/first"]
            )
            self.assertEqual(req3.url, "http://scrapytest.org/redirected2")
            self.assertEqual(
                req3.meta["redirect_urls"],
                ["http://scrapytest.org/first", "http://scrapytest.org/redirected"],
            )

        def test_redirect_reasons(self):
            req1 = Request("http://scrapytest.org/first")
            rsp1 = self.get_response(req1, "/redirected1")
            req2 = self.mw.process_response(req1, rsp1, self.spider)
            rsp2 = self.get_response(req2, "/redirected2")
            req3 = self.mw.process_response(req2, rsp2, self.spider)
            self.assertEqual(req2.meta["redirect_reasons"], [self.reason])
            self.assertEqual(req3.meta["redirect_reasons"], [self.reason, self.reason])

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
                original_request, internal_response, self.spider
            )
            self.assertIsInstance(internal_redirect_request, Request)
            self.assertEqual(
                original_request.headers, internal_redirect_request.headers
            )

            # Redirects to the same origin (same scheme, same domain, same port)
            # keep all headers also when the scheme is http.
            http_request = Request(
                "http://example.com",
                headers={**safe_headers, **cookie_header, **authorization_header},
            )
            http_response = self.get_response(http_request, "http://example.com/a")
            http_redirect_request = self.mw.process_response(
                http_request, http_response, self.spider
            )
            self.assertIsInstance(http_redirect_request, Request)
            self.assertEqual(http_request.headers, http_redirect_request.headers)

            # For default ports, whether the port is explicit or implicit does not
            # affect the outcome, it is still the same origin.
            to_explicit_port_response = self.get_response(
                original_request, "https://example.com:443/a"
            )
            to_explicit_port_redirect_request = self.mw.process_response(
                original_request, to_explicit_port_response, self.spider
            )
            self.assertIsInstance(to_explicit_port_redirect_request, Request)
            self.assertEqual(
                original_request.headers, to_explicit_port_redirect_request.headers
            )

            # For default ports, whether the port is explicit or implicit does not
            # affect the outcome, it is still the same origin.
            to_implicit_port_response = self.get_response(
                original_request, "https://example.com/a"
            )
            to_implicit_port_redirect_request = self.mw.process_response(
                original_request, to_implicit_port_response, self.spider
            )
            self.assertIsInstance(to_implicit_port_redirect_request, Request)
            self.assertEqual(
                original_request.headers, to_implicit_port_redirect_request.headers
            )

            # A port change drops the Authorization header because the origin
            # changes, but keeps the Cookie header because the domain remains the
            # same.
            different_port_response = self.get_response(
                original_request, "https://example.com:8080/a"
            )
            different_port_redirect_request = self.mw.process_response(
                original_request, different_port_response, self.spider
            )
            self.assertIsInstance(different_port_redirect_request, Request)
            self.assertEqual(
                {**safe_headers, **cookie_header},
                different_port_redirect_request.headers.to_unicode_dict(),
            )

            # A domain change drops both the Authorization and the Cookie header.
            external_response = self.get_response(
                original_request, "https://example.org/a"
            )
            external_redirect_request = self.mw.process_response(
                original_request, external_response, self.spider
            )
            self.assertIsInstance(external_redirect_request, Request)
            self.assertEqual(
                safe_headers, external_redirect_request.headers.to_unicode_dict()
            )

            # A scheme upgrade (http → https) drops the Authorization header
            # because the origin changes, but keeps the Cookie header because the
            # domain remains the same.
            upgrade_response = self.get_response(http_request, "https://example.com/a")
            upgrade_redirect_request = self.mw.process_response(
                http_request, upgrade_response, self.spider
            )
            self.assertIsInstance(upgrade_redirect_request, Request)
            self.assertEqual(
                {**safe_headers, **cookie_header},
                upgrade_redirect_request.headers.to_unicode_dict(),
            )

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
                original_request, downgrade_response, self.spider
            )
            self.assertIsInstance(downgrade_redirect_request, Request)
            self.assertEqual(
                safe_headers,
                downgrade_redirect_request.headers.to_unicode_dict(),
            )

        def test_meta_proxy_http_absolute(self):
            crawler = get_crawler()
            redirect_mw = self.mwcls.from_crawler(crawler)
            proxy_mw = HttpProxyMiddleware.from_crawler(crawler)

            meta = {"proxy": "https://a:@a.example"}
            request1 = Request("http://example.com", meta=meta)
            spider = None
            proxy_mw.process_request(request1, spider)

            self.assertEqual(request1.headers["Proxy-Authorization"], b"Basic YTo=")
            self.assertEqual(request1.meta["_auth_proxy"], "https://a.example")
            self.assertEqual(request1.meta["proxy"], "https://a.example")

            response1 = self.get_response(request1, "http://example.com")
            request2 = redirect_mw.process_response(request1, response1, spider)

            self.assertIsInstance(request2, Request)
            self.assertEqual(request2.headers["Proxy-Authorization"], b"Basic YTo=")
            self.assertEqual(request2.meta["_auth_proxy"], "https://a.example")
            self.assertEqual(request2.meta["proxy"], "https://a.example")

            proxy_mw.process_request(request2, spider)

            self.assertEqual(request2.headers["Proxy-Authorization"], b"Basic YTo=")
            self.assertEqual(request2.meta["_auth_proxy"], "https://a.example")
            self.assertEqual(request2.meta["proxy"], "https://a.example")

            response2 = self.get_response(request2, "http://example.com")
            request3 = redirect_mw.process_response(request2, response2, spider)

            self.assertIsInstance(request3, Request)
            self.assertEqual(request3.headers["Proxy-Authorization"], b"Basic YTo=")
            self.assertEqual(request3.meta["_auth_proxy"], "https://a.example")
            self.assertEqual(request3.meta["proxy"], "https://a.example")

            proxy_mw.process_request(request3, spider)

            self.assertEqual(request3.headers["Proxy-Authorization"], b"Basic YTo=")
            self.assertEqual(request3.meta["_auth_proxy"], "https://a.example")
            self.assertEqual(request3.meta["proxy"], "https://a.example")

        def test_meta_proxy_http_relative(self):
            crawler = get_crawler()
            redirect_mw = self.mwcls.from_crawler(crawler)
            proxy_mw = HttpProxyMiddleware.from_crawler(crawler)

            meta = {"proxy": "https://a:@a.example"}
            request1 = Request("http://example.com", meta=meta)
            spider = None
            proxy_mw.process_request(request1, spider)

            self.assertEqual(request1.headers["Proxy-Authorization"], b"Basic YTo=")
            self.assertEqual(request1.meta["_auth_proxy"], "https://a.example")
            self.assertEqual(request1.meta["proxy"], "https://a.example")

            response1 = self.get_response(request1, "/a")
            request2 = redirect_mw.process_response(request1, response1, spider)

            self.assertIsInstance(request2, Request)
            self.assertEqual(request2.headers["Proxy-Authorization"], b"Basic YTo=")
            self.assertEqual(request2.meta["_auth_proxy"], "https://a.example")
            self.assertEqual(request2.meta["proxy"], "https://a.example")

            proxy_mw.process_request(request2, spider)

            self.assertEqual(request2.headers["Proxy-Authorization"], b"Basic YTo=")
            self.assertEqual(request2.meta["_auth_proxy"], "https://a.example")
            self.assertEqual(request2.meta["proxy"], "https://a.example")

            response2 = self.get_response(request2, "/a")
            request3 = redirect_mw.process_response(request2, response2, spider)

            self.assertIsInstance(request3, Request)
            self.assertEqual(request3.headers["Proxy-Authorization"], b"Basic YTo=")
            self.assertEqual(request3.meta["_auth_proxy"], "https://a.example")
            self.assertEqual(request3.meta["proxy"], "https://a.example")

            proxy_mw.process_request(request3, spider)

            self.assertEqual(request3.headers["Proxy-Authorization"], b"Basic YTo=")
            self.assertEqual(request3.meta["_auth_proxy"], "https://a.example")
            self.assertEqual(request3.meta["proxy"], "https://a.example")

        def test_meta_proxy_https_absolute(self):
            crawler = get_crawler()
            redirect_mw = self.mwcls.from_crawler(crawler)
            proxy_mw = HttpProxyMiddleware.from_crawler(crawler)

            meta = {"proxy": "https://a:@a.example"}
            request1 = Request("https://example.com", meta=meta)
            spider = None
            proxy_mw.process_request(request1, spider)

            self.assertEqual(request1.headers["Proxy-Authorization"], b"Basic YTo=")
            self.assertEqual(request1.meta["_auth_proxy"], "https://a.example")
            self.assertEqual(request1.meta["proxy"], "https://a.example")

            response1 = self.get_response(request1, "https://example.com")
            request2 = redirect_mw.process_response(request1, response1, spider)

            self.assertIsInstance(request2, Request)
            self.assertEqual(request2.headers["Proxy-Authorization"], b"Basic YTo=")
            self.assertEqual(request2.meta["_auth_proxy"], "https://a.example")
            self.assertEqual(request2.meta["proxy"], "https://a.example")

            proxy_mw.process_request(request2, spider)

            self.assertEqual(request2.headers["Proxy-Authorization"], b"Basic YTo=")
            self.assertEqual(request2.meta["_auth_proxy"], "https://a.example")
            self.assertEqual(request2.meta["proxy"], "https://a.example")

            response2 = self.get_response(request2, "https://example.com")
            request3 = redirect_mw.process_response(request2, response2, spider)

            self.assertIsInstance(request3, Request)
            self.assertEqual(request3.headers["Proxy-Authorization"], b"Basic YTo=")
            self.assertEqual(request3.meta["_auth_proxy"], "https://a.example")
            self.assertEqual(request3.meta["proxy"], "https://a.example")

            proxy_mw.process_request(request3, spider)

            self.assertEqual(request3.headers["Proxy-Authorization"], b"Basic YTo=")
            self.assertEqual(request3.meta["_auth_proxy"], "https://a.example")
            self.assertEqual(request3.meta["proxy"], "https://a.example")

        def test_meta_proxy_https_relative(self):
            crawler = get_crawler()
            redirect_mw = self.mwcls.from_crawler(crawler)
            proxy_mw = HttpProxyMiddleware.from_crawler(crawler)

            meta = {"proxy": "https://a:@a.example"}
            request1 = Request("https://example.com", meta=meta)
            spider = None
            proxy_mw.process_request(request1, spider)

            self.assertEqual(request1.headers["Proxy-Authorization"], b"Basic YTo=")
            self.assertEqual(request1.meta["_auth_proxy"], "https://a.example")
            self.assertEqual(request1.meta["proxy"], "https://a.example")

            response1 = self.get_response(request1, "/a")
            request2 = redirect_mw.process_response(request1, response1, spider)

            self.assertIsInstance(request2, Request)
            self.assertEqual(request2.headers["Proxy-Authorization"], b"Basic YTo=")
            self.assertEqual(request2.meta["_auth_proxy"], "https://a.example")
            self.assertEqual(request2.meta["proxy"], "https://a.example")

            proxy_mw.process_request(request2, spider)

            self.assertEqual(request2.headers["Proxy-Authorization"], b"Basic YTo=")
            self.assertEqual(request2.meta["_auth_proxy"], "https://a.example")
            self.assertEqual(request2.meta["proxy"], "https://a.example")

            response2 = self.get_response(request2, "/a")
            request3 = redirect_mw.process_response(request2, response2, spider)

            self.assertIsInstance(request3, Request)
            self.assertEqual(request3.headers["Proxy-Authorization"], b"Basic YTo=")
            self.assertEqual(request3.meta["_auth_proxy"], "https://a.example")
            self.assertEqual(request3.meta["proxy"], "https://a.example")

            proxy_mw.process_request(request3, spider)

            self.assertEqual(request3.headers["Proxy-Authorization"], b"Basic YTo=")
            self.assertEqual(request3.meta["_auth_proxy"], "https://a.example")
            self.assertEqual(request3.meta["proxy"], "https://a.example")

        def test_meta_proxy_http_to_https(self):
            crawler = get_crawler()
            redirect_mw = self.mwcls.from_crawler(crawler)
            proxy_mw = HttpProxyMiddleware.from_crawler(crawler)

            meta = {"proxy": "https://a:@a.example"}
            request1 = Request("http://example.com", meta=meta)
            spider = None
            proxy_mw.process_request(request1, spider)

            self.assertEqual(request1.headers["Proxy-Authorization"], b"Basic YTo=")
            self.assertEqual(request1.meta["_auth_proxy"], "https://a.example")
            self.assertEqual(request1.meta["proxy"], "https://a.example")

            response1 = self.get_response(request1, "https://example.com")
            request2 = redirect_mw.process_response(request1, response1, spider)

            self.assertIsInstance(request2, Request)
            self.assertEqual(request2.headers["Proxy-Authorization"], b"Basic YTo=")
            self.assertEqual(request2.meta["_auth_proxy"], "https://a.example")
            self.assertEqual(request2.meta["proxy"], "https://a.example")

            proxy_mw.process_request(request2, spider)

            self.assertEqual(request2.headers["Proxy-Authorization"], b"Basic YTo=")
            self.assertEqual(request2.meta["_auth_proxy"], "https://a.example")
            self.assertEqual(request2.meta["proxy"], "https://a.example")

            response2 = self.get_response(request2, "http://example.com")
            request3 = redirect_mw.process_response(request2, response2, spider)

            self.assertIsInstance(request3, Request)
            self.assertEqual(request3.headers["Proxy-Authorization"], b"Basic YTo=")
            self.assertEqual(request3.meta["_auth_proxy"], "https://a.example")
            self.assertEqual(request3.meta["proxy"], "https://a.example")

            proxy_mw.process_request(request3, spider)

            self.assertEqual(request3.headers["Proxy-Authorization"], b"Basic YTo=")
            self.assertEqual(request3.meta["_auth_proxy"], "https://a.example")
            self.assertEqual(request3.meta["proxy"], "https://a.example")

        def test_meta_proxy_https_to_http(self):
            crawler = get_crawler()
            redirect_mw = self.mwcls.from_crawler(crawler)
            proxy_mw = HttpProxyMiddleware.from_crawler(crawler)

            meta = {"proxy": "https://a:@a.example"}
            request1 = Request("https://example.com", meta=meta)
            spider = None
            proxy_mw.process_request(request1, spider)

            self.assertEqual(request1.headers["Proxy-Authorization"], b"Basic YTo=")
            self.assertEqual(request1.meta["_auth_proxy"], "https://a.example")
            self.assertEqual(request1.meta["proxy"], "https://a.example")

            response1 = self.get_response(request1, "http://example.com")
            request2 = redirect_mw.process_response(request1, response1, spider)

            self.assertIsInstance(request2, Request)
            self.assertEqual(request2.headers["Proxy-Authorization"], b"Basic YTo=")
            self.assertEqual(request2.meta["_auth_proxy"], "https://a.example")
            self.assertEqual(request2.meta["proxy"], "https://a.example")

            proxy_mw.process_request(request2, spider)

            self.assertEqual(request2.headers["Proxy-Authorization"], b"Basic YTo=")
            self.assertEqual(request2.meta["_auth_proxy"], "https://a.example")
            self.assertEqual(request2.meta["proxy"], "https://a.example")

            response2 = self.get_response(request2, "https://example.com")
            request3 = redirect_mw.process_response(request2, response2, spider)

            self.assertIsInstance(request3, Request)
            self.assertEqual(request3.headers["Proxy-Authorization"], b"Basic YTo=")
            self.assertEqual(request3.meta["_auth_proxy"], "https://a.example")
            self.assertEqual(request3.meta["proxy"], "https://a.example")

            proxy_mw.process_request(request3, spider)

            self.assertEqual(request3.headers["Proxy-Authorization"], b"Basic YTo=")
            self.assertEqual(request3.meta["_auth_proxy"], "https://a.example")
            self.assertEqual(request3.meta["proxy"], "https://a.example")

        def test_system_proxy_http_absolute(self):
            crawler = get_crawler()
            redirect_mw = self.mwcls.from_crawler(crawler)
            env = {
                "http_proxy": "https://a:@a.example",
            }
            with set_environ(**env):
                proxy_mw = HttpProxyMiddleware.from_crawler(crawler)

            request1 = Request("http://example.com")
            spider = None
            proxy_mw.process_request(request1, spider)

            self.assertEqual(request1.headers["Proxy-Authorization"], b"Basic YTo=")
            self.assertEqual(request1.meta["_auth_proxy"], "https://a.example")
            self.assertEqual(request1.meta["proxy"], "https://a.example")

            response1 = self.get_response(request1, "http://example.com")
            request2 = redirect_mw.process_response(request1, response1, spider)

            self.assertIsInstance(request2, Request)
            self.assertEqual(request2.headers["Proxy-Authorization"], b"Basic YTo=")
            self.assertEqual(request2.meta["_auth_proxy"], "https://a.example")
            self.assertEqual(request2.meta["proxy"], "https://a.example")

            proxy_mw.process_request(request2, spider)

            self.assertEqual(request2.headers["Proxy-Authorization"], b"Basic YTo=")
            self.assertEqual(request2.meta["_auth_proxy"], "https://a.example")
            self.assertEqual(request2.meta["proxy"], "https://a.example")

            response2 = self.get_response(request2, "http://example.com")
            request3 = redirect_mw.process_response(request2, response2, spider)

            self.assertIsInstance(request3, Request)
            self.assertEqual(request3.headers["Proxy-Authorization"], b"Basic YTo=")
            self.assertEqual(request3.meta["_auth_proxy"], "https://a.example")
            self.assertEqual(request3.meta["proxy"], "https://a.example")

            proxy_mw.process_request(request3, spider)

            self.assertEqual(request3.headers["Proxy-Authorization"], b"Basic YTo=")
            self.assertEqual(request3.meta["_auth_proxy"], "https://a.example")
            self.assertEqual(request3.meta["proxy"], "https://a.example")

        def test_system_proxy_http_relative(self):
            crawler = get_crawler()
            redirect_mw = self.mwcls.from_crawler(crawler)
            env = {
                "http_proxy": "https://a:@a.example",
            }
            with set_environ(**env):
                proxy_mw = HttpProxyMiddleware.from_crawler(crawler)

            request1 = Request("http://example.com")
            spider = None
            proxy_mw.process_request(request1, spider)

            self.assertEqual(request1.headers["Proxy-Authorization"], b"Basic YTo=")
            self.assertEqual(request1.meta["_auth_proxy"], "https://a.example")
            self.assertEqual(request1.meta["proxy"], "https://a.example")

            response1 = self.get_response(request1, "/a")
            request2 = redirect_mw.process_response(request1, response1, spider)

            self.assertIsInstance(request2, Request)
            self.assertEqual(request2.headers["Proxy-Authorization"], b"Basic YTo=")
            self.assertEqual(request2.meta["_auth_proxy"], "https://a.example")
            self.assertEqual(request2.meta["proxy"], "https://a.example")

            proxy_mw.process_request(request2, spider)

            self.assertEqual(request2.headers["Proxy-Authorization"], b"Basic YTo=")
            self.assertEqual(request2.meta["_auth_proxy"], "https://a.example")
            self.assertEqual(request2.meta["proxy"], "https://a.example")

            response2 = self.get_response(request2, "/a")
            request3 = redirect_mw.process_response(request2, response2, spider)

            self.assertIsInstance(request3, Request)
            self.assertEqual(request3.headers["Proxy-Authorization"], b"Basic YTo=")
            self.assertEqual(request3.meta["_auth_proxy"], "https://a.example")
            self.assertEqual(request3.meta["proxy"], "https://a.example")

            proxy_mw.process_request(request3, spider)

            self.assertEqual(request3.headers["Proxy-Authorization"], b"Basic YTo=")
            self.assertEqual(request3.meta["_auth_proxy"], "https://a.example")
            self.assertEqual(request3.meta["proxy"], "https://a.example")

        def test_system_proxy_https_absolute(self):
            crawler = get_crawler()
            redirect_mw = self.mwcls.from_crawler(crawler)
            env = {
                "https_proxy": "https://a:@a.example",
            }
            with set_environ(**env):
                proxy_mw = HttpProxyMiddleware.from_crawler(crawler)

            request1 = Request("https://example.com")
            spider = None
            proxy_mw.process_request(request1, spider)

            self.assertEqual(request1.headers["Proxy-Authorization"], b"Basic YTo=")
            self.assertEqual(request1.meta["_auth_proxy"], "https://a.example")
            self.assertEqual(request1.meta["proxy"], "https://a.example")

            response1 = self.get_response(request1, "https://example.com")
            request2 = redirect_mw.process_response(request1, response1, spider)

            self.assertIsInstance(request2, Request)
            self.assertEqual(request2.headers["Proxy-Authorization"], b"Basic YTo=")
            self.assertEqual(request2.meta["_auth_proxy"], "https://a.example")
            self.assertEqual(request2.meta["proxy"], "https://a.example")

            proxy_mw.process_request(request2, spider)

            self.assertEqual(request2.headers["Proxy-Authorization"], b"Basic YTo=")
            self.assertEqual(request2.meta["_auth_proxy"], "https://a.example")
            self.assertEqual(request2.meta["proxy"], "https://a.example")

            response2 = self.get_response(request2, "https://example.com")
            request3 = redirect_mw.process_response(request2, response2, spider)

            self.assertIsInstance(request3, Request)
            self.assertEqual(request3.headers["Proxy-Authorization"], b"Basic YTo=")
            self.assertEqual(request3.meta["_auth_proxy"], "https://a.example")
            self.assertEqual(request3.meta["proxy"], "https://a.example")

            proxy_mw.process_request(request3, spider)

            self.assertEqual(request3.headers["Proxy-Authorization"], b"Basic YTo=")
            self.assertEqual(request3.meta["_auth_proxy"], "https://a.example")
            self.assertEqual(request3.meta["proxy"], "https://a.example")

        def test_system_proxy_https_relative(self):
            crawler = get_crawler()
            redirect_mw = self.mwcls.from_crawler(crawler)
            env = {
                "https_proxy": "https://a:@a.example",
            }
            with set_environ(**env):
                proxy_mw = HttpProxyMiddleware.from_crawler(crawler)

            request1 = Request("https://example.com")
            spider = None
            proxy_mw.process_request(request1, spider)

            self.assertEqual(request1.headers["Proxy-Authorization"], b"Basic YTo=")
            self.assertEqual(request1.meta["_auth_proxy"], "https://a.example")
            self.assertEqual(request1.meta["proxy"], "https://a.example")

            response1 = self.get_response(request1, "/a")
            request2 = redirect_mw.process_response(request1, response1, spider)

            self.assertIsInstance(request2, Request)
            self.assertEqual(request2.headers["Proxy-Authorization"], b"Basic YTo=")
            self.assertEqual(request2.meta["_auth_proxy"], "https://a.example")
            self.assertEqual(request2.meta["proxy"], "https://a.example")

            proxy_mw.process_request(request2, spider)

            self.assertEqual(request2.headers["Proxy-Authorization"], b"Basic YTo=")
            self.assertEqual(request2.meta["_auth_proxy"], "https://a.example")
            self.assertEqual(request2.meta["proxy"], "https://a.example")

            response2 = self.get_response(request2, "/a")
            request3 = redirect_mw.process_response(request2, response2, spider)

            self.assertIsInstance(request3, Request)
            self.assertEqual(request3.headers["Proxy-Authorization"], b"Basic YTo=")
            self.assertEqual(request3.meta["_auth_proxy"], "https://a.example")
            self.assertEqual(request3.meta["proxy"], "https://a.example")

            proxy_mw.process_request(request3, spider)

            self.assertEqual(request3.headers["Proxy-Authorization"], b"Basic YTo=")
            self.assertEqual(request3.meta["_auth_proxy"], "https://a.example")
            self.assertEqual(request3.meta["proxy"], "https://a.example")

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
            spider = None
            proxy_mw.process_request(request1, spider)

            self.assertEqual(request1.headers["Proxy-Authorization"], b"Basic YTo=")
            self.assertEqual(request1.meta["_auth_proxy"], "https://a.example")
            self.assertEqual(request1.meta["proxy"], "https://a.example")

            response1 = self.get_response(request1, "https://example.com")
            request2 = redirect_mw.process_response(request1, response1, spider)

            self.assertIsInstance(request2, Request)
            self.assertNotIn("Proxy-Authorization", request2.headers)
            self.assertNotIn("_auth_proxy", request2.meta)
            self.assertNotIn("proxy", request2.meta)

            proxy_mw.process_request(request2, spider)

            self.assertEqual(request2.headers["Proxy-Authorization"], b"Basic Yjo=")
            self.assertEqual(request2.meta["_auth_proxy"], "https://b.example")
            self.assertEqual(request2.meta["proxy"], "https://b.example")

            response2 = self.get_response(request2, "http://example.com")
            request3 = redirect_mw.process_response(request2, response2, spider)

            self.assertIsInstance(request3, Request)
            self.assertNotIn("Proxy-Authorization", request3.headers)
            self.assertNotIn("_auth_proxy", request3.meta)
            self.assertNotIn("proxy", request3.meta)

            proxy_mw.process_request(request3, spider)

            self.assertEqual(request3.headers["Proxy-Authorization"], b"Basic YTo=")
            self.assertEqual(request3.meta["_auth_proxy"], "https://a.example")
            self.assertEqual(request3.meta["proxy"], "https://a.example")

        def test_system_proxy_proxied_http_to_unproxied_https(self):
            crawler = get_crawler()
            redirect_mw = self.mwcls.from_crawler(crawler)
            env = {
                "http_proxy": "https://a:@a.example",
            }
            with set_environ(**env):
                proxy_mw = HttpProxyMiddleware.from_crawler(crawler)

            request1 = Request("http://example.com")
            spider = None
            proxy_mw.process_request(request1, spider)

            self.assertEqual(request1.headers["Proxy-Authorization"], b"Basic YTo=")
            self.assertEqual(request1.meta["_auth_proxy"], "https://a.example")
            self.assertEqual(request1.meta["proxy"], "https://a.example")

            response1 = self.get_response(request1, "https://example.com")
            request2 = redirect_mw.process_response(request1, response1, spider)

            self.assertIsInstance(request2, Request)
            self.assertNotIn("Proxy-Authorization", request2.headers)
            self.assertNotIn("_auth_proxy", request2.meta)
            self.assertNotIn("proxy", request2.meta)

            proxy_mw.process_request(request2, spider)

            self.assertNotIn("Proxy-Authorization", request2.headers)
            self.assertNotIn("_auth_proxy", request2.meta)
            self.assertNotIn("proxy", request2.meta)

            response2 = self.get_response(request2, "http://example.com")
            request3 = redirect_mw.process_response(request2, response2, spider)

            self.assertIsInstance(request3, Request)
            self.assertNotIn("Proxy-Authorization", request3.headers)
            self.assertNotIn("_auth_proxy", request3.meta)
            self.assertNotIn("proxy", request3.meta)

            proxy_mw.process_request(request3, spider)

            self.assertEqual(request3.headers["Proxy-Authorization"], b"Basic YTo=")
            self.assertEqual(request3.meta["_auth_proxy"], "https://a.example")
            self.assertEqual(request3.meta["proxy"], "https://a.example")

        def test_system_proxy_unproxied_http_to_proxied_https(self):
            crawler = get_crawler()
            redirect_mw = self.mwcls.from_crawler(crawler)
            env = {
                "https_proxy": "https://b:@b.example",
            }
            with set_environ(**env):
                proxy_mw = HttpProxyMiddleware.from_crawler(crawler)

            request1 = Request("http://example.com")
            spider = None
            proxy_mw.process_request(request1, spider)

            self.assertNotIn("Proxy-Authorization", request1.headers)
            self.assertNotIn("_auth_proxy", request1.meta)
            self.assertNotIn("proxy", request1.meta)

            response1 = self.get_response(request1, "https://example.com")
            request2 = redirect_mw.process_response(request1, response1, spider)

            self.assertIsInstance(request2, Request)
            self.assertNotIn("Proxy-Authorization", request2.headers)
            self.assertNotIn("_auth_proxy", request2.meta)
            self.assertNotIn("proxy", request2.meta)

            proxy_mw.process_request(request2, spider)

            self.assertEqual(request2.headers["Proxy-Authorization"], b"Basic Yjo=")
            self.assertEqual(request2.meta["_auth_proxy"], "https://b.example")
            self.assertEqual(request2.meta["proxy"], "https://b.example")

            response2 = self.get_response(request2, "http://example.com")
            request3 = redirect_mw.process_response(request2, response2, spider)

            self.assertIsInstance(request3, Request)
            self.assertNotIn("Proxy-Authorization", request3.headers)
            self.assertNotIn("_auth_proxy", request3.meta)
            self.assertNotIn("proxy", request3.meta)

            proxy_mw.process_request(request3, spider)

            self.assertNotIn("Proxy-Authorization", request3.headers)
            self.assertNotIn("_auth_proxy", request3.meta)
            self.assertNotIn("proxy", request3.meta)

        def test_system_proxy_unproxied_http_to_unproxied_https(self):
            crawler = get_crawler()
            redirect_mw = self.mwcls.from_crawler(crawler)
            proxy_mw = HttpProxyMiddleware.from_crawler(crawler)

            request1 = Request("http://example.com")
            spider = None
            proxy_mw.process_request(request1, spider)

            self.assertNotIn("Proxy-Authorization", request1.headers)
            self.assertNotIn("_auth_proxy", request1.meta)
            self.assertNotIn("proxy", request1.meta)

            response1 = self.get_response(request1, "https://example.com")
            request2 = redirect_mw.process_response(request1, response1, spider)

            self.assertIsInstance(request2, Request)
            self.assertNotIn("Proxy-Authorization", request2.headers)
            self.assertNotIn("_auth_proxy", request2.meta)
            self.assertNotIn("proxy", request2.meta)

            proxy_mw.process_request(request2, spider)

            self.assertNotIn("Proxy-Authorization", request2.headers)
            self.assertNotIn("_auth_proxy", request2.meta)
            self.assertNotIn("proxy", request2.meta)

            response2 = self.get_response(request2, "http://example.com")
            request3 = redirect_mw.process_response(request2, response2, spider)

            self.assertIsInstance(request3, Request)
            self.assertNotIn("Proxy-Authorization", request3.headers)
            self.assertNotIn("_auth_proxy", request3.meta)
            self.assertNotIn("proxy", request3.meta)

            proxy_mw.process_request(request3, spider)

            self.assertNotIn("Proxy-Authorization", request3.headers)
            self.assertNotIn("_auth_proxy", request3.meta)
            self.assertNotIn("proxy", request3.meta)

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
            spider = None
            proxy_mw.process_request(request1, spider)

            self.assertEqual(request1.headers["Proxy-Authorization"], b"Basic Yjo=")
            self.assertEqual(request1.meta["_auth_proxy"], "https://b.example")
            self.assertEqual(request1.meta["proxy"], "https://b.example")

            response1 = self.get_response(request1, "http://example.com")
            request2 = redirect_mw.process_response(request1, response1, spider)

            self.assertIsInstance(request2, Request)
            self.assertNotIn("Proxy-Authorization", request2.headers)
            self.assertNotIn("_auth_proxy", request2.meta)
            self.assertNotIn("proxy", request2.meta)

            proxy_mw.process_request(request2, spider)

            self.assertEqual(request2.headers["Proxy-Authorization"], b"Basic YTo=")
            self.assertEqual(request2.meta["_auth_proxy"], "https://a.example")
            self.assertEqual(request2.meta["proxy"], "https://a.example")

            response2 = self.get_response(request2, "https://example.com")
            request3 = redirect_mw.process_response(request2, response2, spider)

            self.assertIsInstance(request3, Request)
            self.assertNotIn("Proxy-Authorization", request3.headers)
            self.assertNotIn("_auth_proxy", request3.meta)
            self.assertNotIn("proxy", request3.meta)

            proxy_mw.process_request(request3, spider)

            self.assertEqual(request3.headers["Proxy-Authorization"], b"Basic Yjo=")
            self.assertEqual(request3.meta["_auth_proxy"], "https://b.example")
            self.assertEqual(request3.meta["proxy"], "https://b.example")

        def test_system_proxy_proxied_https_to_unproxied_http(self):
            crawler = get_crawler()
            redirect_mw = self.mwcls.from_crawler(crawler)
            env = {
                "https_proxy": "https://b:@b.example",
            }
            with set_environ(**env):
                proxy_mw = HttpProxyMiddleware.from_crawler(crawler)

            request1 = Request("https://example.com")
            spider = None
            proxy_mw.process_request(request1, spider)

            self.assertEqual(request1.headers["Proxy-Authorization"], b"Basic Yjo=")
            self.assertEqual(request1.meta["_auth_proxy"], "https://b.example")
            self.assertEqual(request1.meta["proxy"], "https://b.example")

            response1 = self.get_response(request1, "http://example.com")
            request2 = redirect_mw.process_response(request1, response1, spider)

            self.assertIsInstance(request2, Request)
            self.assertNotIn("Proxy-Authorization", request2.headers)
            self.assertNotIn("_auth_proxy", request2.meta)
            self.assertNotIn("proxy", request2.meta)

            proxy_mw.process_request(request2, spider)

            self.assertNotIn("Proxy-Authorization", request2.headers)
            self.assertNotIn("_auth_proxy", request2.meta)
            self.assertNotIn("proxy", request2.meta)

            response2 = self.get_response(request2, "https://example.com")
            request3 = redirect_mw.process_response(request2, response2, spider)

            self.assertIsInstance(request3, Request)
            self.assertNotIn("Proxy-Authorization", request3.headers)
            self.assertNotIn("_auth_proxy", request3.meta)
            self.assertNotIn("proxy", request3.meta)

            proxy_mw.process_request(request3, spider)

            self.assertEqual(request3.headers["Proxy-Authorization"], b"Basic Yjo=")
            self.assertEqual(request3.meta["_auth_proxy"], "https://b.example")
            self.assertEqual(request3.meta["proxy"], "https://b.example")

        def test_system_proxy_unproxied_https_to_proxied_http(self):
            crawler = get_crawler()
            redirect_mw = self.mwcls.from_crawler(crawler)
            env = {
                "http_proxy": "https://a:@a.example",
            }
            with set_environ(**env):
                proxy_mw = HttpProxyMiddleware.from_crawler(crawler)

            request1 = Request("https://example.com")
            spider = None
            proxy_mw.process_request(request1, spider)

            self.assertNotIn("Proxy-Authorization", request1.headers)
            self.assertNotIn("_auth_proxy", request1.meta)
            self.assertNotIn("proxy", request1.meta)

            response1 = self.get_response(request1, "http://example.com")
            request2 = redirect_mw.process_response(request1, response1, spider)

            self.assertIsInstance(request2, Request)
            self.assertNotIn("Proxy-Authorization", request2.headers)
            self.assertNotIn("_auth_proxy", request2.meta)
            self.assertNotIn("proxy", request2.meta)

            proxy_mw.process_request(request2, spider)

            self.assertEqual(request2.headers["Proxy-Authorization"], b"Basic YTo=")
            self.assertEqual(request2.meta["_auth_proxy"], "https://a.example")
            self.assertEqual(request2.meta["proxy"], "https://a.example")

            response2 = self.get_response(request2, "https://example.com")
            request3 = redirect_mw.process_response(request2, response2, spider)

            self.assertIsInstance(request3, Request)
            self.assertNotIn("Proxy-Authorization", request3.headers)
            self.assertNotIn("_auth_proxy", request3.meta)
            self.assertNotIn("proxy", request3.meta)

            proxy_mw.process_request(request3, spider)

            self.assertNotIn("Proxy-Authorization", request3.headers)
            self.assertNotIn("_auth_proxy", request3.meta)
            self.assertNotIn("proxy", request3.meta)

        def test_system_proxy_unproxied_https_to_unproxied_http(self):
            crawler = get_crawler()
            redirect_mw = self.mwcls.from_crawler(crawler)
            proxy_mw = HttpProxyMiddleware.from_crawler(crawler)

            request1 = Request("https://example.com")
            spider = None
            proxy_mw.process_request(request1, spider)

            self.assertNotIn("Proxy-Authorization", request1.headers)
            self.assertNotIn("_auth_proxy", request1.meta)
            self.assertNotIn("proxy", request1.meta)

            response1 = self.get_response(request1, "http://example.com")
            request2 = redirect_mw.process_response(request1, response1, spider)

            self.assertIsInstance(request2, Request)
            self.assertNotIn("Proxy-Authorization", request2.headers)
            self.assertNotIn("_auth_proxy", request2.meta)
            self.assertNotIn("proxy", request2.meta)

            proxy_mw.process_request(request2, spider)

            self.assertNotIn("Proxy-Authorization", request2.headers)
            self.assertNotIn("_auth_proxy", request2.meta)
            self.assertNotIn("proxy", request2.meta)

            response2 = self.get_response(request2, "https://example.com")
            request3 = redirect_mw.process_response(request2, response2, spider)

            self.assertIsInstance(request3, Request)
            self.assertNotIn("Proxy-Authorization", request3.headers)
            self.assertNotIn("_auth_proxy", request3.meta)
            self.assertNotIn("proxy", request3.meta)

            proxy_mw.process_request(request3, spider)

            self.assertNotIn("Proxy-Authorization", request3.headers)
            self.assertNotIn("_auth_proxy", request3.meta)
            self.assertNotIn("proxy", request3.meta)


class RedirectMiddlewareTest(Base.Test):
    mwcls = RedirectMiddleware
    reason = 302

    def setUp(self):
        self.crawler = get_crawler(Spider)
        self.spider = self.crawler._create_spider("foo")
        self.mw = self.mwcls.from_crawler(self.crawler)

    def get_response(self, request, location, status=302):
        headers = {"Location": location}
        return Response(request.url, status=status, headers=headers)

    def test_redirect_3xx_permanent(self):
        def _test(method, status=301):
            url = f"http://www.example.com/{status}"
            url2 = "http://www.example.com/redirected"
            req = Request(url, method=method)
            rsp = Response(url, headers={"Location": url2}, status=status)

            req2 = self.mw.process_response(req, rsp, self.spider)
            assert isinstance(req2, Request)
            self.assertEqual(req2.url, url2)
            self.assertEqual(req2.method, method)

            # response without Location header but with status code is 3XX should be ignored
            del rsp.headers["Location"]
            assert self.mw.process_response(req, rsp, self.spider) is rsp

        _test("GET")
        _test("POST")
        _test("HEAD")

        _test("GET", status=307)
        _test("POST", status=307)
        _test("HEAD", status=307)

        _test("GET", status=308)
        _test("POST", status=308)
        _test("HEAD", status=308)

    def test_redirect_302_head(self):
        url = "http://www.example.com/302"
        url2 = "http://www.example.com/redirected2"
        req = Request(url, method="HEAD")
        rsp = Response(url, headers={"Location": url2}, status=302)

        req2 = self.mw.process_response(req, rsp, self.spider)
        assert isinstance(req2, Request)
        self.assertEqual(req2.url, url2)
        self.assertEqual(req2.method, "HEAD")

    def test_redirect_302_relative(self):
        url = "http://www.example.com/302"
        url2 = "///i8n.example2.com/302"
        url3 = "http://i8n.example2.com/302"
        req = Request(url, method="HEAD")
        rsp = Response(url, headers={"Location": url2}, status=302)

        req2 = self.mw.process_response(req, rsp, self.spider)
        assert isinstance(req2, Request)
        self.assertEqual(req2.url, url3)
        self.assertEqual(req2.method, "HEAD")

    def test_spider_handling(self):
        smartspider = self.crawler._create_spider("smarty")
        smartspider.handle_httpstatus_list = [404, 301, 302]
        url = "http://www.example.com/301"
        url2 = "http://www.example.com/redirected"
        req = Request(url)
        rsp = Response(url, headers={"Location": url2}, status=301)
        r = self.mw.process_response(req, rsp, smartspider)
        self.assertIs(r, rsp)

    def test_request_meta_handling(self):
        url = "http://www.example.com/301"
        url2 = "http://www.example.com/redirected"

        def _test_passthrough(req):
            rsp = Response(url, headers={"Location": url2}, status=301, request=req)
            r = self.mw.process_response(req, rsp, self.spider)
            self.assertIs(r, rsp)

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
        req_result = self.mw.process_response(req, resp, self.spider)
        perc_encoded_utf8_url = "http://scrapytest.org/a%E7%E3o"
        self.assertEqual(perc_encoded_utf8_url, req_result.url)

    def test_utf8_location(self):
        req = Request("http://scrapytest.org/first")
        utf8_location = "/ação".encode()  # header using UTF-8 encoding
        resp = Response(
            "http://scrapytest.org/first",
            headers={"Location": utf8_location},
            status=302,
        )
        req_result = self.mw.process_response(req, resp, self.spider)
        perc_encoded_utf8_url = "http://scrapytest.org/a%C3%A7%C3%A3o"
        self.assertEqual(perc_encoded_utf8_url, req_result.url)

    def test_no_location(self):
        request = Request("https://example.com")
        response = Response(request.url, status=302)
        assert self.mw.process_response(request, response, self.spider) is response


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


@pytest.mark.parametrize(SCHEME_PARAMS, REDIRECT_SCHEME_CASES)
def test_redirect_schemes(url, location, target):
    crawler = get_crawler(Spider)
    spider = crawler._create_spider("foo")
    mw = RedirectMiddleware.from_crawler(crawler)
    request = Request(url)
    response = Response(url, headers={"Location": location}, status=301)
    redirect = mw.process_response(request, response, spider)
    if target is None:
        assert redirect == response
    else:
        assert isinstance(redirect, Request)
        assert redirect.url == target


def meta_refresh_body(url, interval=5):
    html = f"""<html><head><meta http-equiv="refresh" content="{interval};url={url}"/></head></html>"""
    return html.encode("utf-8")


class MetaRefreshMiddlewareTest(Base.Test):
    mwcls = MetaRefreshMiddleware
    reason = "meta refresh"

    def setUp(self):
        crawler = get_crawler(Spider)
        self.spider = crawler._create_spider("foo")
        self.mw = self.mwcls.from_crawler(crawler)

    def _body(self, interval=5, url="http://example.org/newpage"):
        return meta_refresh_body(url, interval)

    def get_response(self, request, location):
        return HtmlResponse(request.url, body=self._body(url=location))

    def test_meta_refresh(self):
        req = Request(url="http://example.org")
        rsp = HtmlResponse(req.url, body=self._body())
        req2 = self.mw.process_response(req, rsp, self.spider)
        assert isinstance(req2, Request)
        self.assertEqual(req2.url, "http://example.org/newpage")

    def test_meta_refresh_with_high_interval(self):
        # meta-refresh with high intervals don't trigger redirects
        req = Request(url="http://example.org")
        rsp = HtmlResponse(
            url="http://example.org", body=self._body(interval=1000), encoding="utf-8"
        )
        rsp2 = self.mw.process_response(req, rsp, self.spider)
        assert rsp is rsp2

    def test_meta_refresh_trough_posted_request(self):
        req = Request(
            url="http://example.org",
            method="POST",
            body="test",
            headers={"Content-Type": "text/plain", "Content-length": "4"},
        )
        rsp = HtmlResponse(req.url, body=self._body())
        req2 = self.mw.process_response(req, rsp, self.spider)

        assert isinstance(req2, Request)
        self.assertEqual(req2.url, "http://example.org/newpage")
        self.assertEqual(req2.method, "GET")
        assert (
            "Content-Type" not in req2.headers
        ), "Content-Type header must not be present in redirected request"
        assert (
            "Content-Length" not in req2.headers
        ), "Content-Length header must not be present in redirected request"
        assert not req2.body, f"Redirected body must be empty, not '{req2.body}'"

    def test_ignore_tags_default(self):
        req = Request(url="http://example.org")
        body = (
            """<noscript><meta http-equiv="refresh" """
            """content="0;URL='http://example.org/newpage'"></noscript>"""
        )
        rsp = HtmlResponse(req.url, body=body.encode())
        response = self.mw.process_response(req, rsp, self.spider)
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
        response = mw.process_response(req, rsp, self.spider)
        assert isinstance(response, Response)


@pytest.mark.parametrize(
    SCHEME_PARAMS,
    (
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
    ),
)
def test_meta_refresh_schemes(url, location, target):
    crawler = get_crawler(Spider)
    spider = crawler._create_spider("foo")
    mw = MetaRefreshMiddleware.from_crawler(crawler)
    request = Request(url)
    response = HtmlResponse(url, body=meta_refresh_body(location))
    redirect = mw.process_response(request, response, spider)
    if target is None:
        assert redirect == response
    else:
        assert isinstance(redirect, Request)
        assert redirect.url == target


if __name__ == "__main__":
    unittest.main()
