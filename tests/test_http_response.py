import pytest
from packaging.version import Version as parse_version
from w3lib import __version__ as w3lib_version
from w3lib.encoding import resolve_encoding

from scrapy.exceptions import NotSupported
from scrapy.http import Headers, Request, Response
from scrapy.link import Link
from tests import get_testdata


class TestResponse:
    response_class = Response

    def test_init(self):
        # Response requires url in the constructor
        with pytest.raises(TypeError):
            self.response_class()
        assert isinstance(
            self.response_class("http://example.com/"), self.response_class
        )
        with pytest.raises(TypeError):
            self.response_class(b"http://example.com")
        with pytest.raises(TypeError):
            self.response_class(url="http://example.com", body={})
        # body can be str or None
        assert isinstance(
            self.response_class("http://example.com/", body=b""),
            self.response_class,
        )
        assert isinstance(
            self.response_class("http://example.com/", body=b"body"),
            self.response_class,
        )
        # test presence of all optional parameters
        assert isinstance(
            self.response_class(
                "http://example.com/", body=b"", headers={}, status=200
            ),
            self.response_class,
        )

        r = self.response_class("http://www.example.com")
        assert isinstance(r.url, str)
        assert r.url == "http://www.example.com"
        assert r.status == 200

        assert isinstance(r.headers, Headers)
        assert not r.headers

        headers = {"foo": "bar"}
        body = b"a body"
        r = self.response_class("http://www.example.com", headers=headers, body=body)

        assert r.headers is not headers
        assert r.headers[b"foo"] == b"bar"

        r = self.response_class("http://www.example.com", status=301)
        assert r.status == 301
        r = self.response_class("http://www.example.com", status="301")
        assert r.status == 301
        with pytest.raises(ValueError, match=r"invalid literal for int\(\)"):
            self.response_class("http://example.com", status="lala200")

    def test_copy(self):
        """Test Response copy"""

        r1 = self.response_class("http://www.example.com", body=b"Some body")
        r1.flags.append("cached")
        r2 = r1.copy()

        assert r1.status == r2.status
        assert r1.body == r2.body

        # make sure flags list is shallow copied
        assert r1.flags is not r2.flags, "flags must be a shallow copy, not identical"
        assert r1.flags == r2.flags

        # make sure headers attribute is shallow copied
        assert r1.headers is not r2.headers, (
            "headers must be a shallow copy, not identical"
        )
        assert r1.headers == r2.headers

    def test_copy_meta(self):
        req = Request("http://www.example.com")
        req.meta["foo"] = "bar"
        r1 = self.response_class(
            "http://www.example.com", body=b"Some body", request=req
        )
        assert r1.meta is req.meta

    def test_copy_cb_kwargs(self):
        req = Request("http://www.example.com")
        req.cb_kwargs["foo"] = "bar"
        r1 = self.response_class(
            "http://www.example.com", body=b"Some body", request=req
        )
        assert r1.cb_kwargs is req.cb_kwargs

    def test_unavailable_meta(self):
        r1 = self.response_class("http://www.example.com", body=b"Some body")
        with pytest.raises(AttributeError, match=r"Response\.meta not available"):
            r1.meta

    def test_unavailable_cb_kwargs(self):
        r1 = self.response_class("http://www.example.com", body=b"Some body")
        with pytest.raises(AttributeError, match=r"Response\.cb_kwargs not available"):
            r1.cb_kwargs

    def test_copy_inherited_classes(self):
        """Test Response children copies preserve their class"""

        class CustomResponse(self.response_class):
            pass

        r1 = CustomResponse("http://www.example.com")
        r2 = r1.copy()

        assert isinstance(r2, CustomResponse)

    def test_replace(self):
        """Test Response.replace() method"""
        hdrs = Headers({"key": "value"})
        r1 = self.response_class("http://www.example.com")
        r2 = r1.replace(status=301, body=b"New body", headers=hdrs)
        assert r1.body == b""
        assert r1.url == r2.url
        assert (r1.status, r2.status) == (200, 301)
        assert (r1.body, r2.body) == (b"", b"New body")
        assert (r1.headers, r2.headers) == ({}, hdrs)

        # Empty attributes (which may fail if not compared properly)
        r3 = self.response_class("http://www.example.com", flags=["cached"])
        r4 = r3.replace(body=b"", flags=[])
        assert r4.body == b""
        assert not r4.flags

    def _assert_response_values(self, response, encoding, body):
        if isinstance(body, str):
            body_unicode = body
            body_bytes = body.encode(encoding)
        else:
            body_unicode = body.decode(encoding)
            body_bytes = body

        assert isinstance(response.body, bytes)
        assert isinstance(response.text, str)
        self._assert_response_encoding(response, encoding)
        assert response.body == body_bytes
        assert response.text == body_unicode

    def _assert_response_encoding(self, response, encoding):
        assert response.encoding == resolve_encoding(encoding)

    def test_immutable_attributes(self):
        r = self.response_class("http://example.com")
        with pytest.raises(AttributeError):
            r.url = "http://example2.com"
        with pytest.raises(AttributeError):
            r.body = "xxx"

    def test_urljoin(self):
        """Test urljoin shortcut (only for existence, since behavior equals urljoin)"""
        joined = self.response_class("http://www.example.com").urljoin("/test")
        absolute = "http://www.example.com/test"
        assert joined == absolute

    def test_shortcut_attributes(self):
        r = self.response_class("http://example.com", body=b"hello")
        if self.response_class == Response:
            msg = "Response content isn't text"
            with pytest.raises(AttributeError, match=msg):
                r.text
            with pytest.raises(NotSupported, match=msg):
                r.css("body")
            with pytest.raises(NotSupported, match=msg):
                r.xpath("//body")
            with pytest.raises(NotSupported, match=msg):
                r.jmespath("body")
        else:
            r.text
            r.css("body")
            r.xpath("//body")

    # Response.follow

    def test_follow_url_absolute(self):
        self._assert_followed_url("http://foo.example.com", "http://foo.example.com")

    def test_follow_url_relative(self):
        self._assert_followed_url("foo", "http://example.com/foo")

    def test_follow_link(self):
        self._assert_followed_url(
            Link("http://example.com/foo"), "http://example.com/foo"
        )

    def test_follow_None_url(self):
        r = self.response_class("http://example.com")
        with pytest.raises(ValueError, match="url can't be None"):
            r.follow(None)

    @pytest.mark.xfail(
        parse_version(w3lib_version) < parse_version("2.1.1"),
        reason="https://github.com/scrapy/w3lib/pull/207",
        strict=True,
    )
    def test_follow_whitespace_url(self):
        self._assert_followed_url("foo ", "http://example.com/foo")

    @pytest.mark.xfail(
        parse_version(w3lib_version) < parse_version("2.1.1"),
        reason="https://github.com/scrapy/w3lib/pull/207",
        strict=True,
    )
    def test_follow_whitespace_link(self):
        self._assert_followed_url(
            Link("http://example.com/foo "), "http://example.com/foo"
        )

    def test_follow_flags(self):
        res = self.response_class("http://example.com/")
        fol = res.follow("http://example.com/", flags=["cached", "allowed"])
        assert fol.flags == ["cached", "allowed"]

    # Response.follow_all

    def test_follow_all_absolute(self):
        url_list = [
            "http://example.org",
            "http://www.example.org",
            "http://example.com",
            "http://www.example.com",
        ]
        self._assert_followed_all_urls(url_list, url_list)

    def test_follow_all_relative(self):
        relative = ["foo", "bar", "foo/bar", "bar/foo"]
        absolute = [
            "http://example.com/foo",
            "http://example.com/bar",
            "http://example.com/foo/bar",
            "http://example.com/bar/foo",
        ]
        self._assert_followed_all_urls(relative, absolute)

    def test_follow_all_links(self):
        absolute = [
            "http://example.com/foo",
            "http://example.com/bar",
            "http://example.com/foo/bar",
            "http://example.com/bar/foo",
        ]
        links = map(Link, absolute)
        self._assert_followed_all_urls(links, absolute)

    def test_follow_all_empty(self):
        r = self.response_class("http://example.com")
        assert not list(r.follow_all([]))

    def test_follow_all_invalid(self):
        r = self.response_class("http://example.com")
        if self.response_class == Response:
            with pytest.raises(TypeError):
                list(r.follow_all(urls=None))
            with pytest.raises(TypeError):
                list(r.follow_all(urls=12345))
            with pytest.raises(ValueError, match="url can't be None"):
                list(r.follow_all(urls=[None]))
        else:
            with pytest.raises(
                ValueError, match="Please supply exactly one of the following arguments"
            ):
                list(r.follow_all(urls=None))
            with pytest.raises(TypeError):
                list(r.follow_all(urls=12345))
            with pytest.raises(ValueError, match="url can't be None"):
                list(r.follow_all(urls=[None]))

    def test_follow_all_whitespace(self):
        relative = ["foo ", "bar ", "foo/bar ", "bar/foo "]
        absolute = [
            "http://example.com/foo%20",
            "http://example.com/bar%20",
            "http://example.com/foo/bar%20",
            "http://example.com/bar/foo%20",
        ]
        self._assert_followed_all_urls(relative, absolute)

    def test_follow_all_whitespace_links(self):
        absolute = [
            "http://example.com/foo ",
            "http://example.com/bar ",
            "http://example.com/foo/bar ",
            "http://example.com/bar/foo ",
        ]
        links = map(Link, absolute)
        expected = [u.replace(" ", "%20") for u in absolute]
        self._assert_followed_all_urls(links, expected)

    def test_follow_all_flags(self):
        re = self.response_class("http://www.example.com/")
        urls = [
            "http://www.example.com/",
            "http://www.example.com/2",
            "http://www.example.com/foo",
        ]
        fol = re.follow_all(urls, flags=["cached", "allowed"])
        for req in fol:
            assert req.flags == ["cached", "allowed"]

    def _assert_followed_url(self, follow_obj, target_url, response=None):
        if response is None:
            response = self._links_response()
        req = response.follow(follow_obj)
        assert req.url == target_url
        return req

    def _assert_followed_all_urls(self, follow_obj, target_urls, response=None):
        if response is None:
            response = self._links_response()
        followed = response.follow_all(follow_obj)
        for req, target in zip(followed, target_urls, strict=False):
            assert req.url == target
            yield req

    def _links_response(self):
        body = get_testdata("link_extractor", "linkextractor.html")
        return self.response_class("http://example.com/index", body=body)

    def _links_response_no_href(self):
        body = get_testdata("link_extractor", "linkextractor_no_href.html")
        return self.response_class("http://example.com/index", body=body)
