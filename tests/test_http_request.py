import warnings
import xmlrpc.client
from typing import Any

import pytest

from scrapy.http import Headers, Request, XmlRpcRequest
from scrapy.http.request import NO_CALLBACK
from scrapy.utils.python import to_bytes


class TestRequest:
    request_class = Request
    default_method = "GET"
    default_headers: dict[bytes, list[bytes]] = {}
    default_meta: dict[str, Any] = {}

    def test_init(self):
        # Request requires url in the __init__ method
        with pytest.raises(TypeError):
            self.request_class()

        # url argument must be basestring
        with pytest.raises(TypeError):
            self.request_class(123)
        r = self.request_class("http://www.example.com")

        r = self.request_class("http://www.example.com")
        assert isinstance(r.url, str)
        assert r.url == "http://www.example.com"
        assert r.method == self.default_method

        assert isinstance(r.headers, Headers)
        assert r.headers == self.default_headers
        assert r.meta == self.default_meta

        meta = {"lala": "lolo"}
        headers = {b"caca": b"coco"}
        r = self.request_class(
            "http://www.example.com", meta=meta, headers=headers, body="a body"
        )

        assert r.meta is not meta
        assert r.meta == meta
        assert r.headers is not headers
        assert r.headers[b"caca"] == b"coco"

    def test_url_scheme(self):
        # This test passes by not raising any (ValueError) exception
        self.request_class("http://example.org")
        self.request_class("https://example.org")
        self.request_class("s3://example.org")
        self.request_class("ftp://example.org")
        self.request_class("about:config")
        self.request_class("data:,Hello%2C%20World!")

    def test_url_no_scheme(self):
        msg = "Missing scheme in request url:"
        with pytest.raises(ValueError, match=msg):
            self.request_class("foo")
        with pytest.raises(ValueError, match=msg):
            self.request_class("/foo/")
        with pytest.raises(ValueError, match=msg):
            self.request_class("/foo:bar")

    def test_headers(self):
        # Different ways of setting headers attribute
        url = "http://www.scrapy.org"
        headers = {b"Accept": "gzip", b"Custom-Header": "nothing to tell you"}
        r = self.request_class(url=url, headers=headers)
        p = self.request_class(url=url, headers=r.headers)

        assert r.headers == p.headers
        assert r.headers is not headers
        assert p.headers is not r.headers

        # headers must not be unicode
        h = Headers({"key1": "val1", "key2": "val2"})
        h["newkey"] = "newval"
        for k, v in h.items():
            assert isinstance(k, bytes)
            for s in v:
                assert isinstance(s, bytes)

    def test_eq(self):
        url = "http://www.scrapy.org"
        r1 = self.request_class(url=url)
        r2 = self.request_class(url=url)
        assert r1 != r2

        set_ = set()
        set_.add(r1)
        set_.add(r2)
        assert len(set_) == 2

    def test_url(self):
        r = self.request_class(url="http://www.scrapy.org/path")
        assert r.url == "http://www.scrapy.org/path"

    def test_url_quoting(self):
        r = self.request_class(url="http://www.scrapy.org/blank%20space")
        assert r.url == "http://www.scrapy.org/blank%20space"
        r = self.request_class(url="http://www.scrapy.org/blank space")
        assert r.url == "http://www.scrapy.org/blank%20space"

    def test_url_encoding(self):
        r = self.request_class(url="http://www.scrapy.org/price/£")
        assert r.url == "http://www.scrapy.org/price/%C2%A3"

    def test_url_encoding_other(self):
        # encoding affects only query part of URI, not path
        # path part should always be UTF-8 encoded before percent-escaping
        r = self.request_class(url="http://www.scrapy.org/price/£", encoding="utf-8")
        assert r.url == "http://www.scrapy.org/price/%C2%A3"

        r = self.request_class(url="http://www.scrapy.org/price/£", encoding="latin1")
        assert r.url == "http://www.scrapy.org/price/%C2%A3"

    def test_url_encoding_query(self):
        r1 = self.request_class(url="http://www.scrapy.org/price/£?unit=µ")
        assert r1.url == "http://www.scrapy.org/price/%C2%A3?unit=%C2%B5"

        # should be same as above
        r2 = self.request_class(
            url="http://www.scrapy.org/price/£?unit=µ", encoding="utf-8"
        )
        assert r2.url == "http://www.scrapy.org/price/%C2%A3?unit=%C2%B5"

    def test_url_encoding_query_latin1(self):
        # encoding is used for encoding query-string before percent-escaping;
        # path is still UTF-8 encoded before percent-escaping
        r3 = self.request_class(
            url="http://www.scrapy.org/price/µ?currency=£", encoding="latin1"
        )
        assert r3.url == "http://www.scrapy.org/price/%C2%B5?currency=%A3"

    def test_url_encoding_nonutf8_untouched(self):
        # percent-escaping sequences that do not match valid UTF-8 sequences
        # should be kept untouched (just upper-cased perhaps)
        #
        # See https://datatracker.ietf.org/doc/html/rfc3987#section-3.2
        #
        # "Conversions from URIs to IRIs MUST NOT use any character encoding
        # other than UTF-8 in steps 3 and 4, even if it might be possible to
        # guess from the context that another character encoding than UTF-8 was
        # used in the URI.  For example, the URI
        # "http://www.example.org/r%E9sum%E9.html" might with some guessing be
        # interpreted to contain two e-acute characters encoded as iso-8859-1.
        # It must not be converted to an IRI containing these e-acute
        # characters.  Otherwise, in the future the IRI will be mapped to
        # "http://www.example.org/r%C3%A9sum%C3%A9.html", which is a different
        # URI from "http://www.example.org/r%E9sum%E9.html".
        r1 = self.request_class(url="http://www.scrapy.org/price/%a3")
        assert r1.url == "http://www.scrapy.org/price/%a3"

        r2 = self.request_class(url="http://www.scrapy.org/r%C3%A9sum%C3%A9/%a3")
        assert r2.url == "http://www.scrapy.org/r%C3%A9sum%C3%A9/%a3"

        r3 = self.request_class(url="http://www.scrapy.org/résumé/%a3")
        assert r3.url == "http://www.scrapy.org/r%C3%A9sum%C3%A9/%a3"

        r4 = self.request_class(url="http://www.example.org/r%E9sum%E9.html")
        assert r4.url == "http://www.example.org/r%E9sum%E9.html"

    def test_body(self):
        r1 = self.request_class(url="http://www.example.com/")
        assert r1.body == b""

        r2 = self.request_class(url="http://www.example.com/", body=b"")
        assert isinstance(r2.body, bytes)
        assert r2.encoding == "utf-8"  # default encoding

        r3 = self.request_class(
            url="http://www.example.com/", body="Price: \xa3100", encoding="utf-8"
        )
        assert isinstance(r3.body, bytes)
        assert r3.body == b"Price: \xc2\xa3100"

        r4 = self.request_class(
            url="http://www.example.com/", body="Price: \xa3100", encoding="latin1"
        )
        assert isinstance(r4.body, bytes)
        assert r4.body == b"Price: \xa3100"

    def test_copy(self):
        """Test Request copy"""

        def somecallback():
            pass

        r1 = self.request_class(
            "http://www.example.com",
            flags=["f1", "f2"],
            callback=somecallback,
            errback=somecallback,
        )
        r1.meta["foo"] = "bar"
        r1.cb_kwargs["key"] = "value"
        r2 = r1.copy()

        # make sure copy does not propagate callbacks
        assert r1.callback is somecallback
        assert r1.errback is somecallback
        assert r2.callback is r1.callback
        assert r2.errback is r2.errback

        # make sure flags list is shallow copied
        assert r1.flags is not r2.flags, "flags must be a shallow copy, not identical"
        assert r1.flags == r2.flags

        # make sure cb_kwargs dict is shallow copied
        assert r1.cb_kwargs is not r2.cb_kwargs, (
            "cb_kwargs must be a shallow copy, not identical"
        )
        assert r1.cb_kwargs == r2.cb_kwargs

        # make sure meta dict is shallow copied
        assert r1.meta is not r2.meta, "meta must be a shallow copy, not identical"
        assert r1.meta == r2.meta

        # make sure headers attribute is shallow copied
        assert r1.headers is not r2.headers, (
            "headers must be a shallow copy, not identical"
        )
        assert r1.headers == r2.headers
        assert r1.encoding == r2.encoding
        assert r1.dont_filter == r2.dont_filter

        # Request.body can be identical since it's an immutable object (str)

    def test_copy_inherited_classes(self):
        """Test Request children copies preserve their class"""

        class CustomRequest(self.request_class):
            pass

        r1 = CustomRequest("http://www.example.com")
        r2 = r1.copy()

        assert isinstance(r2, CustomRequest)

    def test_replace(self):
        """Test Request.replace() method"""
        r1 = self.request_class("http://www.example.com", method="GET")
        hdrs = Headers(r1.headers)
        hdrs[b"key"] = b"value"
        r2 = r1.replace(method="POST", body="New body", headers=hdrs)
        assert r1.url == r2.url
        assert (r1.method, r2.method) == ("GET", "POST")
        assert (r1.body, r2.body) == (b"", b"New body")
        assert (r1.headers, r2.headers) == (self.default_headers, hdrs)

        # Empty attributes (which may fail if not compared properly)
        r3 = self.request_class(
            "http://www.example.com", meta={"a": 1}, dont_filter=True
        )
        r4 = r3.replace(
            url="http://www.example.com/2", body=b"", meta={}, dont_filter=False
        )
        assert r4.url == "http://www.example.com/2"
        assert r4.body == b""
        assert r4.meta == {}
        assert r4.dont_filter is False

    def test_method_always_str(self):
        r = self.request_class("http://www.example.com", method="POST")
        assert isinstance(r.method, str)

    def test_immutable_attributes(self):
        r = self.request_class("http://example.com")
        with pytest.raises(AttributeError):
            r.url = "http://example2.com"
        with pytest.raises(AttributeError):
            r.body = "xxx"

    def test_callback_and_errback(self):
        def a_function():
            pass

        r1 = self.request_class("http://example.com")
        assert r1.callback is None
        assert r1.errback is None

        r2 = self.request_class("http://example.com", callback=a_function)
        assert r2.callback is a_function
        assert r2.errback is None

        r3 = self.request_class("http://example.com", errback=a_function)
        assert r3.callback is None
        assert r3.errback is a_function

        r4 = self.request_class(
            url="http://example.com",
            callback=a_function,
            errback=a_function,
        )
        assert r4.callback is a_function
        assert r4.errback is a_function

        r5 = self.request_class(
            url="http://example.com",
            callback=NO_CALLBACK,
            errback=NO_CALLBACK,
        )
        assert r5.callback is NO_CALLBACK
        assert r5.errback is NO_CALLBACK

    def test_callback_and_errback_type(self):
        with pytest.raises(TypeError):
            self.request_class("http://example.com", callback="a_function")
        with pytest.raises(TypeError):
            self.request_class("http://example.com", errback="a_function")
        with pytest.raises(TypeError):
            self.request_class(
                url="http://example.com",
                callback="a_function",
                errback="a_function",
            )

    def test_setters(self):
        request = self.request_class("http://example.com")

        request.cb_kwargs = {"a": 1}
        assert request.cb_kwargs == {"a": 1}

        request.meta = {"k": "v"}
        assert request.meta == {"k": "v"}

        request.flags = ["f1"]
        assert request.flags == ["f1"]

        request.cookies = {"sid": "1"}
        assert request.cookies == {"sid": "1"}

        headers = Headers({b"X-Test": b"1"})
        request.headers = headers
        assert request._headers is headers
        request.headers = {b"A": b"b"}
        assert isinstance(request.headers, Headers)
        assert request._headers[b"A"] == b"b"

    def test_setter_mutable_lazy_loading(self):
        """Mutable attributes are set internally to None only until they are
        read, then they always return the same falsy instance of the
        corresponding mutable structure.

        Setting them to None causes the next read to return a different object.
        """

        request = self.request_class("http://example.com")

        assert request._cb_kwargs is None
        assert request.cb_kwargs == {}
        assert request.cb_kwargs is request.cb_kwargs
        assert request._cb_kwargs == {}
        original_cb_kwargs = request.cb_kwargs
        request.cb_kwargs = None
        assert request.cb_kwargs == {}
        assert request.cb_kwargs is not original_cb_kwargs

        assert request._meta is None
        assert request.meta == {}
        assert request.meta is request.meta
        assert request._meta == {}
        original_meta = request.meta
        request.meta = None
        assert request.meta == {}
        assert request.meta is not original_meta

        assert request._flags is None
        assert request.flags == []
        assert request.flags is request.flags
        assert request._flags == []
        original_flags = request.flags
        request.flags = None
        assert request.flags == []
        assert request.flags is not original_flags

        assert request._cookies is None
        assert request.cookies == {}
        assert request.cookies is request.cookies
        assert request._cookies == {}
        original_cookies = request.cookies
        request.cookies = None
        assert request.cookies == {}
        assert request.cookies is not original_cookies

        if self.default_headers:
            assert request._headers == self.default_headers
            assert request._headers is not self.default_headers
            assert request.headers == self.default_headers
        else:
            assert request._headers is None
            assert request.headers == {}
        assert request.headers is request.headers
        assert isinstance(request.headers, Headers)
        assert isinstance(request._headers, Headers)
        original_headers = request.headers
        request.headers = None
        assert request.headers == {}
        assert request.headers is not original_headers

    def test_no_callback(self):
        with pytest.raises(RuntimeError):
            NO_CALLBACK()

    def test_from_curl(self):
        # Note: more curated tests regarding curl conversion are in
        # `test_utils_curl.py`
        curl_command = (
            "curl 'http://httpbin.org/post' -X POST -H 'Cookie: _gauges_unique"
            "_year=1; _gauges_unique=1; _gauges_unique_month=1; _gauges_unique"
            "_hour=1; _gauges_unique_day=1' -H 'Origin: http://httpbin.org' -H"
            " 'Accept-Encoding: gzip, deflate' -H 'Accept-Language: en-US,en;q"
            "=0.9,ru;q=0.8,es;q=0.7' -H 'Upgrade-Insecure-Requests: 1' -H 'Use"
            "r-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTM"
            "L, like Gecko) Ubuntu Chromium/62.0.3202.75 Chrome/62.0.3202.75 S"
            "afari/537.36' -H 'Content-Type: application /x-www-form-urlencode"
            "d' -H 'Accept: text/html,application/xhtml+xml,application/xml;q="
            "0.9,image/webp,image/apng,*/*;q=0.8' -H 'Cache-Control: max-age=0"
            "' -H 'Referer: http://httpbin.org/forms/post' -H 'Connection: kee"
            "p-alive' --data 'custname=John+Smith&custtel=500&custemail=jsmith"
            "%40example.org&size=small&topping=cheese&topping=onion&delivery=1"
            "2%3A15&comments=' --compressed"
        )
        r = self.request_class.from_curl(curl_command)
        assert r.method == "POST"
        assert r.url == "http://httpbin.org/post"
        assert (
            r.body == b"custname=John+Smith&custtel=500&custemail=jsmith%40"
            b"example.org&size=small&topping=cheese&topping=onion"
            b"&delivery=12%3A15&comments="
        )
        assert r.cookies == {
            "_gauges_unique_year": "1",
            "_gauges_unique": "1",
            "_gauges_unique_month": "1",
            "_gauges_unique_hour": "1",
            "_gauges_unique_day": "1",
        }
        assert r.headers == {
            b"Origin": [b"http://httpbin.org"],
            b"Accept-Encoding": [b"gzip, deflate"],
            b"Accept-Language": [b"en-US,en;q=0.9,ru;q=0.8,es;q=0.7"],
            b"Upgrade-Insecure-Requests": [b"1"],
            b"User-Agent": [
                b"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537."
                b"36 (KHTML, like Gecko) Ubuntu Chromium/62.0.3202"
                b".75 Chrome/62.0.3202.75 Safari/537.36"
            ],
            b"Content-Type": [b"application /x-www-form-urlencoded"],
            b"Accept": [
                b"text/html,application/xhtml+xml,application/xml;q=0."
                b"9,image/webp,image/apng,*/*;q=0.8"
            ],
            b"Cache-Control": [b"max-age=0"],
            b"Referer": [b"http://httpbin.org/forms/post"],
            b"Connection": [b"keep-alive"],
        }

    def test_from_curl_with_kwargs(self):
        r = self.request_class.from_curl(
            'curl -X PATCH "http://example.org"', method="POST", meta={"key": "value"}
        )
        assert r.method == "POST"
        assert r.meta == {"key": "value"}

    def test_from_curl_ignore_unknown_options(self):
        # By default: it works and ignores the unknown options: --foo and -z
        with warnings.catch_warnings():  # avoid warning when executing tests
            warnings.simplefilter("ignore")
            r = self.request_class.from_curl(
                'curl -X DELETE "http://example.org" --foo -z',
            )
            assert r.method == "DELETE"

        # If `ignore_unknown_options` is set to `False` it raises an error with
        # the unknown options: --foo and -z
        with pytest.raises(ValueError, match="Unrecognized options:"):
            self.request_class.from_curl(
                'curl -X PATCH "http://example.org" --foo -z',
                ignore_unknown_options=False,
            )


class TestXmlRpcRequest(TestRequest):
    request_class = XmlRpcRequest
    default_method = "POST"
    default_headers = {b"Content-Type": [b"text/xml"]}

    def _test_request(self, **kwargs):
        r = self.request_class("http://scrapytest.org/rpc2", **kwargs)
        assert r.headers[b"Content-Type"] == b"text/xml"
        assert r.body == to_bytes(
            xmlrpc.client.dumps(**kwargs), encoding=kwargs.get("encoding", "utf-8")
        )
        assert r.method == "POST"
        assert r.encoding == kwargs.get("encoding", "utf-8")
        assert r.dont_filter

    def test_xmlrpc_dumps(self):
        self._test_request(params=("value",))
        self._test_request(params=("username", "password"), methodname="login")
        self._test_request(params=("response",), methodresponse="login")
        self._test_request(params=("pas£",), encoding="utf-8")
        self._test_request(params=(None,), allow_none=1)
        with pytest.raises(TypeError):
            self._test_request()
        with pytest.raises(TypeError):
            self._test_request(params=(None,))

    def test_latin1(self):
        self._test_request(params=("pas£",), encoding="latin1")
