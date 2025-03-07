import os

import pytest

from scrapy.downloadermiddlewares.httpproxy import HttpProxyMiddleware
from scrapy.exceptions import NotConfigured
from scrapy.http import Request
from scrapy.spiders import Spider
from scrapy.utils.test import get_crawler

spider = Spider("foo")


class TestHttpProxyMiddleware:
    failureException = AssertionError  # type: ignore[assignment]

    def setup_method(self):
        self._oldenv = os.environ.copy()

    def teardown_method(self):
        os.environ = self._oldenv

    def test_not_enabled(self):
        crawler = get_crawler(Spider, {"HTTPPROXY_ENABLED": False})
        with pytest.raises(NotConfigured):
            HttpProxyMiddleware.from_crawler(crawler)

    def test_no_environment_proxies(self):
        os.environ = {"dummy_proxy": "reset_env_and_do_not_raise"}
        mw = HttpProxyMiddleware()

        for url in ("http://e.com", "https://e.com", "file:///tmp/a"):
            req = Request(url)
            assert mw.process_request(req, spider) is None
            assert req.url == url
            assert req.meta == {}

    def test_environment_proxies(self):
        os.environ["http_proxy"] = http_proxy = "https://proxy.for.http:3128"
        os.environ["https_proxy"] = https_proxy = "http://proxy.for.https:8080"
        os.environ.pop("file_proxy", None)
        mw = HttpProxyMiddleware()

        for url, proxy in [
            ("http://e.com", http_proxy),
            ("https://e.com", https_proxy),
            ("file://tmp/a", None),
        ]:
            req = Request(url)
            assert mw.process_request(req, spider) is None
            assert req.url == url
            assert req.meta.get("proxy") == proxy

    def test_proxy_precedence_meta(self):
        os.environ["http_proxy"] = "https://proxy.com"
        mw = HttpProxyMiddleware()
        req = Request("http://scrapytest.org", meta={"proxy": "https://new.proxy:3128"})
        assert mw.process_request(req, spider) is None
        assert req.meta == {"proxy": "https://new.proxy:3128"}

    def test_proxy_auth(self):
        os.environ["http_proxy"] = "https://user:pass@proxy:3128"
        mw = HttpProxyMiddleware()
        req = Request("http://scrapytest.org")
        assert mw.process_request(req, spider) is None
        assert req.meta["proxy"] == "https://proxy:3128"
        assert req.headers.get("Proxy-Authorization") == b"Basic dXNlcjpwYXNz"
        # proxy from request.meta
        req = Request(
            "http://scrapytest.org",
            meta={"proxy": "https://username:password@proxy:3128"},
        )
        assert mw.process_request(req, spider) is None
        assert req.meta["proxy"] == "https://proxy:3128"
        assert (
            req.headers.get("Proxy-Authorization") == b"Basic dXNlcm5hbWU6cGFzc3dvcmQ="
        )

    def test_proxy_auth_empty_passwd(self):
        os.environ["http_proxy"] = "https://user:@proxy:3128"
        mw = HttpProxyMiddleware()
        req = Request("http://scrapytest.org")
        assert mw.process_request(req, spider) is None
        assert req.meta["proxy"] == "https://proxy:3128"
        assert req.headers.get("Proxy-Authorization") == b"Basic dXNlcjo="
        # proxy from request.meta
        req = Request(
            "http://scrapytest.org", meta={"proxy": "https://username:@proxy:3128"}
        )
        assert mw.process_request(req, spider) is None
        assert req.meta["proxy"] == "https://proxy:3128"
        assert req.headers.get("Proxy-Authorization") == b"Basic dXNlcm5hbWU6"

    def test_proxy_auth_encoding(self):
        # utf-8 encoding
        os.environ["http_proxy"] = "https://m\u00e1n:pass@proxy:3128"
        mw = HttpProxyMiddleware(auth_encoding="utf-8")
        req = Request("http://scrapytest.org")
        assert mw.process_request(req, spider) is None
        assert req.meta["proxy"] == "https://proxy:3128"
        assert req.headers.get("Proxy-Authorization") == b"Basic bcOhbjpwYXNz"

        # proxy from request.meta
        req = Request(
            "http://scrapytest.org", meta={"proxy": "https://\u00fcser:pass@proxy:3128"}
        )
        assert mw.process_request(req, spider) is None
        assert req.meta["proxy"] == "https://proxy:3128"
        assert req.headers.get("Proxy-Authorization") == b"Basic w7xzZXI6cGFzcw=="

        # default latin-1 encoding
        mw = HttpProxyMiddleware(auth_encoding="latin-1")
        req = Request("http://scrapytest.org")
        assert mw.process_request(req, spider) is None
        assert req.meta["proxy"] == "https://proxy:3128"
        assert req.headers.get("Proxy-Authorization") == b"Basic beFuOnBhc3M="

        # proxy from request.meta, latin-1 encoding
        req = Request(
            "http://scrapytest.org", meta={"proxy": "https://\u00fcser:pass@proxy:3128"}
        )
        assert mw.process_request(req, spider) is None
        assert req.meta["proxy"] == "https://proxy:3128"
        assert req.headers.get("Proxy-Authorization") == b"Basic /HNlcjpwYXNz"

    def test_proxy_already_seted(self):
        os.environ["http_proxy"] = "https://proxy.for.http:3128"
        mw = HttpProxyMiddleware()
        req = Request("http://noproxy.com", meta={"proxy": None})
        assert mw.process_request(req, spider) is None
        assert "proxy" in req.meta
        assert req.meta["proxy"] is None

    def test_no_proxy(self):
        os.environ["http_proxy"] = "https://proxy.for.http:3128"
        mw = HttpProxyMiddleware()

        os.environ["no_proxy"] = "*"
        req = Request("http://noproxy.com")
        assert mw.process_request(req, spider) is None
        assert "proxy" not in req.meta

        os.environ["no_proxy"] = "other.com"
        req = Request("http://noproxy.com")
        assert mw.process_request(req, spider) is None
        assert "proxy" in req.meta

        os.environ["no_proxy"] = "other.com,noproxy.com"
        req = Request("http://noproxy.com")
        assert mw.process_request(req, spider) is None
        assert "proxy" not in req.meta

        # proxy from meta['proxy'] takes precedence
        os.environ["no_proxy"] = "*"
        req = Request("http://noproxy.com", meta={"proxy": "http://proxy.com"})
        assert mw.process_request(req, spider) is None
        assert req.meta == {"proxy": "http://proxy.com"}

    def test_no_proxy_invalid_values(self):
        os.environ["no_proxy"] = "/var/run/docker.sock"
        mw = HttpProxyMiddleware()
        # '/var/run/docker.sock' may be used by the user for
        # no_proxy value but is not parseable and should be skipped
        assert "no" not in mw.proxies

    def test_add_proxy_without_credentials(self):
        middleware = HttpProxyMiddleware()
        request = Request("https://example.com")
        assert middleware.process_request(request, spider) is None
        request.meta["proxy"] = "https://example.com"
        assert middleware.process_request(request, spider) is None
        assert request.meta["proxy"] == "https://example.com"
        assert b"Proxy-Authorization" not in request.headers

    def test_add_proxy_with_credentials(self):
        middleware = HttpProxyMiddleware()
        request = Request("https://example.com")
        assert middleware.process_request(request, spider) is None
        request.meta["proxy"] = "https://user1:password1@example.com"
        assert middleware.process_request(request, spider) is None
        assert request.meta["proxy"] == "https://example.com"
        encoded_credentials = middleware._basic_auth_header(
            "user1",
            "password1",
        )
        assert request.headers["Proxy-Authorization"] == b"Basic " + encoded_credentials

    def test_remove_proxy_without_credentials(self):
        middleware = HttpProxyMiddleware()
        request = Request(
            "https://example.com",
            meta={"proxy": "https://example.com"},
        )
        assert middleware.process_request(request, spider) is None
        request.meta["proxy"] = None
        assert middleware.process_request(request, spider) is None
        assert request.meta["proxy"] is None
        assert b"Proxy-Authorization" not in request.headers

    def test_remove_proxy_with_credentials(self):
        middleware = HttpProxyMiddleware()
        request = Request(
            "https://example.com",
            meta={"proxy": "https://user1:password1@example.com"},
        )
        assert middleware.process_request(request, spider) is None
        request.meta["proxy"] = None
        assert middleware.process_request(request, spider) is None
        assert request.meta["proxy"] is None
        assert b"Proxy-Authorization" not in request.headers

    def test_add_credentials(self):
        """If the proxy request meta switches to a proxy URL with the same
        proxy and adds credentials (there were no credentials before), the new
        credentials must be used."""
        middleware = HttpProxyMiddleware()
        request = Request(
            "https://example.com",
            meta={"proxy": "https://example.com"},
        )
        assert middleware.process_request(request, spider) is None

        request.meta["proxy"] = "https://user1:password1@example.com"
        assert middleware.process_request(request, spider) is None
        assert request.meta["proxy"] == "https://example.com"
        encoded_credentials = middleware._basic_auth_header(
            "user1",
            "password1",
        )
        assert request.headers["Proxy-Authorization"] == b"Basic " + encoded_credentials

    def test_change_credentials(self):
        """If the proxy request meta switches to a proxy URL with different
        credentials, those new credentials must be used."""
        middleware = HttpProxyMiddleware()
        request = Request(
            "https://example.com",
            meta={"proxy": "https://user1:password1@example.com"},
        )
        assert middleware.process_request(request, spider) is None
        request.meta["proxy"] = "https://user2:password2@example.com"
        assert middleware.process_request(request, spider) is None
        assert request.meta["proxy"] == "https://example.com"
        encoded_credentials = middleware._basic_auth_header(
            "user2",
            "password2",
        )
        assert request.headers["Proxy-Authorization"] == b"Basic " + encoded_credentials

    def test_remove_credentials(self):
        """If the proxy request meta switches to a proxy URL with the same
        proxy but no credentials, the original credentials must be still
        used.

        To remove credentials while keeping the same proxy URL, users must
        delete the Proxy-Authorization header.
        """
        middleware = HttpProxyMiddleware()
        request = Request(
            "https://example.com",
            meta={"proxy": "https://user1:password1@example.com"},
        )
        assert middleware.process_request(request, spider) is None

        request.meta["proxy"] = "https://example.com"
        assert middleware.process_request(request, spider) is None
        assert request.meta["proxy"] == "https://example.com"
        encoded_credentials = middleware._basic_auth_header(
            "user1",
            "password1",
        )
        assert request.headers["Proxy-Authorization"] == b"Basic " + encoded_credentials

        request.meta["proxy"] = "https://example.com"
        del request.headers[b"Proxy-Authorization"]
        assert middleware.process_request(request, spider) is None
        assert request.meta["proxy"] == "https://example.com"
        assert b"Proxy-Authorization" not in request.headers

    def test_change_proxy_add_credentials(self):
        middleware = HttpProxyMiddleware()
        request = Request(
            "https://example.com",
            meta={"proxy": "https://example.com"},
        )
        assert middleware.process_request(request, spider) is None

        request.meta["proxy"] = "https://user1:password1@example.org"
        assert middleware.process_request(request, spider) is None
        assert request.meta["proxy"] == "https://example.org"
        encoded_credentials = middleware._basic_auth_header(
            "user1",
            "password1",
        )
        assert request.headers["Proxy-Authorization"] == b"Basic " + encoded_credentials

    def test_change_proxy_keep_credentials(self):
        middleware = HttpProxyMiddleware()
        request = Request(
            "https://example.com",
            meta={"proxy": "https://user1:password1@example.com"},
        )
        assert middleware.process_request(request, spider) is None

        request.meta["proxy"] = "https://user1:password1@example.org"
        assert middleware.process_request(request, spider) is None
        assert request.meta["proxy"] == "https://example.org"
        encoded_credentials = middleware._basic_auth_header(
            "user1",
            "password1",
        )
        assert request.headers["Proxy-Authorization"] == b"Basic " + encoded_credentials

        # Make sure, indirectly, that _auth_proxy is updated.
        request.meta["proxy"] = "https://example.com"
        assert middleware.process_request(request, spider) is None
        assert request.meta["proxy"] == "https://example.com"
        assert b"Proxy-Authorization" not in request.headers

    def test_change_proxy_change_credentials(self):
        middleware = HttpProxyMiddleware()
        request = Request(
            "https://example.com",
            meta={"proxy": "https://user1:password1@example.com"},
        )
        assert middleware.process_request(request, spider) is None

        request.meta["proxy"] = "https://user2:password2@example.org"
        assert middleware.process_request(request, spider) is None
        assert request.meta["proxy"] == "https://example.org"
        encoded_credentials = middleware._basic_auth_header(
            "user2",
            "password2",
        )
        assert request.headers["Proxy-Authorization"] == b"Basic " + encoded_credentials

    def test_change_proxy_remove_credentials(self):
        """If the proxy request meta switches to a proxy URL with a different
        proxy and no credentials, no credentials must be used."""
        middleware = HttpProxyMiddleware()
        request = Request(
            "https://example.com",
            meta={"proxy": "https://user1:password1@example.com"},
        )
        assert middleware.process_request(request, spider) is None
        request.meta["proxy"] = "https://example.org"
        assert middleware.process_request(request, spider) is None
        assert request.meta == {"proxy": "https://example.org"}
        assert b"Proxy-Authorization" not in request.headers

    def test_change_proxy_remove_credentials_preremoved_header(self):
        """Corner case of proxy switch with credentials removal where the
        credentials have been removed beforehand.

        It ensures that our implementation does not assume that the credentials
        header exists when trying to remove it.
        """
        middleware = HttpProxyMiddleware()
        request = Request(
            "https://example.com",
            meta={"proxy": "https://user1:password1@example.com"},
        )
        assert middleware.process_request(request, spider) is None
        request.meta["proxy"] = "https://example.org"
        del request.headers[b"Proxy-Authorization"]
        assert middleware.process_request(request, spider) is None
        assert request.meta == {"proxy": "https://example.org"}
        assert b"Proxy-Authorization" not in request.headers

    def test_proxy_authentication_header_undefined_proxy(self):
        middleware = HttpProxyMiddleware()
        request = Request(
            "https://example.com",
            headers={"Proxy-Authorization": "Basic foo"},
        )
        assert middleware.process_request(request, spider) is None
        assert "proxy" not in request.meta
        assert b"Proxy-Authorization" not in request.headers

    def test_proxy_authentication_header_disabled_proxy(self):
        middleware = HttpProxyMiddleware()
        request = Request(
            "https://example.com",
            headers={"Proxy-Authorization": "Basic foo"},
            meta={"proxy": None},
        )
        assert middleware.process_request(request, spider) is None
        assert request.meta["proxy"] is None
        assert b"Proxy-Authorization" not in request.headers

    def test_proxy_authentication_header_proxy_without_credentials(self):
        """As long as the proxy URL in request metadata remains the same, the
        Proxy-Authorization header is used and kept, and may even be
        changed."""
        middleware = HttpProxyMiddleware()
        request = Request(
            "https://example.com",
            headers={"Proxy-Authorization": "Basic foo"},
            meta={"proxy": "https://example.com"},
        )
        assert middleware.process_request(request, spider) is None
        assert request.meta["proxy"] == "https://example.com"
        assert request.headers["Proxy-Authorization"] == b"Basic foo"

        assert middleware.process_request(request, spider) is None
        assert request.meta["proxy"] == "https://example.com"
        assert request.headers["Proxy-Authorization"] == b"Basic foo"

        request.headers["Proxy-Authorization"] = b"Basic bar"
        assert middleware.process_request(request, spider) is None
        assert request.meta["proxy"] == "https://example.com"
        assert request.headers["Proxy-Authorization"] == b"Basic bar"

    def test_proxy_authentication_header_proxy_with_same_credentials(self):
        middleware = HttpProxyMiddleware()
        encoded_credentials = middleware._basic_auth_header(
            "user1",
            "password1",
        )
        request = Request(
            "https://example.com",
            headers={"Proxy-Authorization": b"Basic " + encoded_credentials},
            meta={"proxy": "https://user1:password1@example.com"},
        )
        assert middleware.process_request(request, spider) is None
        assert request.meta["proxy"] == "https://example.com"
        assert request.headers["Proxy-Authorization"] == b"Basic " + encoded_credentials

    def test_proxy_authentication_header_proxy_with_different_credentials(self):
        middleware = HttpProxyMiddleware()
        encoded_credentials1 = middleware._basic_auth_header(
            "user1",
            "password1",
        )
        request = Request(
            "https://example.com",
            headers={"Proxy-Authorization": b"Basic " + encoded_credentials1},
            meta={"proxy": "https://user2:password2@example.com"},
        )
        assert middleware.process_request(request, spider) is None
        assert request.meta["proxy"] == "https://example.com"
        encoded_credentials2 = middleware._basic_auth_header(
            "user2",
            "password2",
        )
        assert (
            request.headers["Proxy-Authorization"] == b"Basic " + encoded_credentials2
        )
