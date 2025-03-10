import pytest

from scrapy import Request, Spider
from scrapy.http import FormRequest, JsonRequest
from scrapy.utils.request import request_from_dict


class CustomRequest(Request):
    pass


class TestRequestSerialization:
    def setup_method(self):
        self.spider = MethodsSpider()

    def test_basic(self):
        r = Request("http://www.example.com")
        self._assert_serializes_ok(r)

    def test_all_attributes(self):
        r = Request(
            url="http://www.example.com",
            callback=self.spider.parse_item,
            errback=self.spider.handle_error,
            method="POST",
            body=b"some body",
            headers={"content-encoding": "text/html; charset=latin-1"},
            cookies={"currency": "руб"},
            encoding="latin-1",
            priority=20,
            meta={"a": "b"},
            cb_kwargs={"k": "v"},
            flags=["testFlag"],
        )
        self._assert_serializes_ok(r, spider=self.spider)

    def test_latin1_body(self):
        r = Request("http://www.example.com", body=b"\xa3")
        self._assert_serializes_ok(r)

    def test_utf8_body(self):
        r = Request("http://www.example.com", body=b"\xc2\xa3")
        self._assert_serializes_ok(r)

    def _assert_serializes_ok(self, request, spider=None):
        d = request.to_dict(spider=spider)
        request2 = request_from_dict(d, spider=spider)
        self._assert_same_request(request, request2)

    def _assert_same_request(self, r1, r2):
        assert r1.__class__ == r2.__class__
        assert r1.url == r2.url
        assert r1.callback == r2.callback
        assert r1.errback == r2.errback
        assert r1.method == r2.method
        assert r1.body == r2.body
        assert r1.headers == r2.headers
        assert r1.cookies == r2.cookies
        assert r1.meta == r2.meta
        assert r1.cb_kwargs == r2.cb_kwargs
        assert r1.encoding == r2.encoding
        assert r1._encoding == r2._encoding
        assert r1.priority == r2.priority
        assert r1.dont_filter == r2.dont_filter
        assert r1.flags == r2.flags
        if isinstance(r1, JsonRequest):
            assert r1.dumps_kwargs == r2.dumps_kwargs

    def test_request_class(self):
        r1 = FormRequest("http://www.example.com")
        self._assert_serializes_ok(r1, spider=self.spider)
        r2 = CustomRequest("http://www.example.com")
        self._assert_serializes_ok(r2, spider=self.spider)
        r3 = JsonRequest("http://www.example.com", dumps_kwargs={"indent": 4})
        self._assert_serializes_ok(r3, spider=self.spider)

    def test_callback_serialization(self):
        r = Request(
            "http://www.example.com",
            callback=self.spider.parse_item,
            errback=self.spider.handle_error,
        )
        self._assert_serializes_ok(r, spider=self.spider)

    def test_reference_callback_serialization(self):
        r = Request(
            "http://www.example.com",
            callback=self.spider.parse_item_reference,
            errback=self.spider.handle_error_reference,
        )
        self._assert_serializes_ok(r, spider=self.spider)
        request_dict = r.to_dict(spider=self.spider)
        assert request_dict["callback"] == "parse_item_reference"
        assert request_dict["errback"] == "handle_error_reference"

    def test_private_reference_callback_serialization(self):
        r = Request(
            "http://www.example.com",
            callback=self.spider._MethodsSpider__parse_item_reference,
            errback=self.spider._MethodsSpider__handle_error_reference,
        )
        self._assert_serializes_ok(r, spider=self.spider)
        request_dict = r.to_dict(spider=self.spider)
        assert request_dict["callback"] == "_MethodsSpider__parse_item_reference"
        assert request_dict["errback"] == "_MethodsSpider__handle_error_reference"

    def test_private_callback_serialization(self):
        r = Request(
            "http://www.example.com",
            callback=self.spider._MethodsSpider__parse_item_private,
            errback=self.spider.handle_error,
        )
        self._assert_serializes_ok(r, spider=self.spider)

    def test_mixin_private_callback_serialization(self):
        r = Request(
            "http://www.example.com",
            callback=self.spider._SpiderMixin__mixin_callback,
            errback=self.spider.handle_error,
        )
        self._assert_serializes_ok(r, spider=self.spider)

    def test_delegated_callback_serialization(self):
        r = Request(
            "http://www.example.com",
            callback=self.spider.delegated_callback,
            errback=self.spider.handle_error,
        )
        self._assert_serializes_ok(r, spider=self.spider)

    def test_unserializable_callback1(self):
        r = Request("http://www.example.com", callback=lambda x: x)
        with pytest.raises(
            ValueError, match="is not an instance method in: <MethodsSpider"
        ):
            r.to_dict(spider=self.spider)

    def test_unserializable_callback2(self):
        r = Request("http://www.example.com", callback=self.spider.parse_item)
        with pytest.raises(ValueError, match="is not an instance method in: None"):
            r.to_dict(spider=None)

    def test_unserializable_callback3(self):
        """Parser method is removed or replaced dynamically."""

        class MySpider(Spider):
            name = "my_spider"

            def parse(self, response):
                pass

        spider = MySpider()
        r = Request("http://www.example.com", callback=spider.parse)
        spider.parse = None
        with pytest.raises(ValueError, match="is not an instance method in: <MySpider"):
            r.to_dict(spider=spider)

    def test_callback_not_available(self):
        """Callback method is not available in the spider passed to from_dict"""
        spider = SpiderDelegation()
        r = Request("http://www.example.com", callback=spider.delegated_callback)
        d = r.to_dict(spider=spider)
        with pytest.raises(
            ValueError, match="Method 'delegated_callback' not found in: <Spider"
        ):
            request_from_dict(d, spider=Spider("foo"))


class SpiderMixin:
    def __mixin_callback(self, response):  # pylint: disable=unused-private-member
        pass


class SpiderDelegation:
    def delegated_callback(self, response):
        pass


def parse_item(response):
    pass


def handle_error(failure):
    pass


def private_parse_item(response):
    pass


def private_handle_error(failure):
    pass


class MethodsSpider(Spider, SpiderMixin):
    name = "test"
    parse_item_reference = parse_item
    handle_error_reference = handle_error
    __parse_item_reference = private_parse_item
    __handle_error_reference = private_handle_error

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.delegated_callback = SpiderDelegation().delegated_callback

    def parse_item(self, response):
        pass

    def handle_error(self, failure):
        pass

    def __parse_item_private(self, response):  # pylint: disable=unused-private-member
        pass
