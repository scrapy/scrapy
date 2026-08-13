from __future__ import annotations

from http.cookiejar import DefaultCookiePolicy

from scrapy.http import Request, Response
from scrapy.http.cookies import CookieJar, WrappedRequest, WrappedResponse
from scrapy.utils.httpobj import urlparse_cached


class TestCookieJar:
    def setup_method(self):
        self.jar = CookieJar()
        self.request = Request("http://example.com/")
        self.response = Response(
            "http://example.com/",
            headers={"Set-Cookie": "name=value; Domain=example.com; Path=/"},
        )

    def test_extract_cookies(self):
        assert len(self.jar) == 0
        self.jar.extract_cookies(self.response, self.request)
        assert len(self.jar) == 1
        cookie = next(iter(self.jar))
        assert cookie.name == "name"
        assert cookie.value == "value"
        assert ".example.com" in self.jar._cookies

    def test_make_cookies_and_set_cookie(self):
        cookies = self.jar.make_cookies(self.response, self.request)
        assert len(cookies) == 1
        jar = CookieJar()
        for cookie in cookies:
            jar.set_cookie(cookie)
        assert len(jar) == 1

    def test_clear(self):
        self.jar.extract_cookies(self.response, self.request)
        assert len(self.jar) == 1
        self.jar.clear()
        assert len(self.jar) == 0

    def test_clear_session_cookies(self):
        self.jar.extract_cookies(self.response, self.request)
        assert len(self.jar) == 1
        self.jar.clear_session_cookies()
        assert len(self.jar) == 0

    def test_set_policy(self):
        policy = DefaultCookiePolicy()
        self.jar.set_policy(policy)
        assert self.jar.jar._policy is policy  # type: ignore[attr-defined]

    def test_check_expired_frequency(self):
        jar = CookieJar(check_expired_frequency=1)
        jar.add_cookie_header(self.request)
        assert jar.processed == 1


class TestWrappedRequest:
    def setup_method(self):
        self.request = Request(
            "http://www.example.com/page.html", headers={"Content-Type": "text/html"}
        )
        self.wrapped = WrappedRequest(self.request)

    def test_get_full_url(self):
        assert self.wrapped.get_full_url() == self.request.url
        assert self.wrapped.full_url == self.request.url

    def test_get_host(self):
        assert self.wrapped.get_host() == urlparse_cached(self.request).netloc
        assert self.wrapped.host == urlparse_cached(self.request).netloc

    def test_get_type(self):
        assert self.wrapped.get_type() == urlparse_cached(self.request).scheme
        assert self.wrapped.type == urlparse_cached(self.request).scheme

    def test_is_unverifiable(self):
        assert not self.wrapped.is_unverifiable()
        assert not self.wrapped.unverifiable

    def test_is_unverifiable2(self):
        self.request.meta["is_unverifiable"] = True
        assert self.wrapped.is_unverifiable()
        assert self.wrapped.unverifiable

    def test_get_origin_req_host(self):
        assert self.wrapped.origin_req_host == "www.example.com"

    def test_has_header(self):
        assert self.wrapped.has_header("content-type")
        assert not self.wrapped.has_header("xxxxx")

    def test_get_header(self):
        assert self.wrapped.get_header("content-type") == "text/html"
        assert self.wrapped.get_header("xxxxx", "def") == "def"
        assert self.wrapped.get_header("xxxxx") is None
        wrapped = WrappedRequest(
            Request(
                "http://www.example.com/page.html", headers={"empty-binary-header": b""}
            )
        )
        assert wrapped.get_header("empty-binary-header") == ""

    def test_header_items(self):
        assert self.wrapped.header_items() == [("Content-Type", ["text/html"])]

    def test_add_unredirected_header(self):
        self.wrapped.add_unredirected_header("hello", "world")
        assert self.request.headers["hello"] == b"world"


class TestWrappedResponse:
    def setup_method(self):
        self.response = Response(
            "http://www.example.com/page.html", headers={"Content-TYpe": "text/html"}
        )
        self.wrapped = WrappedResponse(self.response)

    def test_info(self):
        assert self.wrapped.info() is self.wrapped

    def test_get_all(self):
        # get_all result must be native string
        assert self.wrapped.get_all("content-type") == ["text/html"]
