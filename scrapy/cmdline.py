import unittest
from scrapy import Request, Spider
from scrapy.http import FormRequest, JsonRequest
from scrapy.utils.request import request_from_dict

class CustomRequest(Request):
    pass

class RequestSerializationTest(unittest.TestCase):
    def setUp(self):
        self.spider = TestSpider()

    def test_basic(self):
        r = Request("http://www.example.com")
        self.assert_serializes_ok(r)

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
        self.assert_serializes_ok(r, spider=self.spider)

    def test_latin1_body(self):
        r = Request("http://www.example.com", body=b"\xa3")
        self.assert_serializes_ok(r)

    def test_utf8_body(self):
        r = Request("http://www.example.com", body=b"\xc2\xa3")
        self.assert_serializes_ok(r)

    def assert_serializes_ok(self, request, spider=None):
        d = request.to_dict(spider=spider)
        request2 = request_from_dict(d, spider=spider)
        self.assert_same_request(request, request2)

    def assert_same_request(self, r1, r2):
        self.assertEqual(type(r1), type(r2))
        for attr in [
            "url", "callback", "errback", "method", "body",
            "headers", "cookies", "meta", "cb_kwargs",
            "encoding", "_encoding", "priority", "dont_filter",
            "flags"
        ]:
            self.assertEqual(getattr(r1, attr), getattr(r2, attr))
        if isinstance(r1, JsonRequest):
            self.assertEqual(r1.dumps_kwargs, r2.dumps_kwargs)

    def test_request_class(self):
        r1 = FormRequest("http://www.example.com")
        self.assert_serializes_ok(r1, spider=self.spider)
        r2 = CustomRequest("http://www.example.com")
        self.assert_serializes_ok(r2, spider=self.spider)
        r3 = JsonRequest("http://www.example.com", dumps_kwargs={"indent": 4})
        self.assert_serializes_ok(r3, spider=self.spider)

    def test_callback_serialization(self):
        r = Request(
            "http://www.example.com",
            callback=self.spider.parse_item,
            errback=self.spider.handle_error,
        )

    def test_reference_callback_serialization(self):
        r = Request(
            "http://www.example.com",
            callback=self.spider.parse_item_reference,
            errback=self.spider.handle_error_reference,
        )
        self.assert_serializes_ok(r, spider=self.spider)
        request_dict = r.to_dict(spider=self.spider)
        self.assertEqual(request_dict["callback"], "parse_item_reference")
        self.assertEqual(request_dict["errback"], "handle_error_reference")

    def test_private_reference_callback_serialization(self):
        r = Request(
            "http://www.example.com",
            callback=self.spider._TestSpider__parse_item_reference,
            errback=self.spider._TestSpider__handle_error_reference,
        )
        self.assert_serializes_ok(r, spider=self.spider)
        request_dict = r.to_dict(spider=self.spider)
        self.assertEqual(request_dict["callback"], "_TestSpider__parse_item_reference")
        self.assertEqual(request_dict["errback"], "_TestSpider__handle_error_reference")

    def test_private_callback_serialization(self):
        r = Request(
            "http://www.example.com",
            callback=self.spider._TestSpider__parse_item_private,
            errback=self.spider.handle_error,
        )
        self.assert_serializes_ok(r, spider=self.spider)

    def test_mixin_private_callback_serialization(self):
        r = Request(
            "http://www.example.com",
            callback=self.spider._TestSpiderMixin__mixin_callback,
            errback=self.spider.handle_error,
        )
        self.assert_serializes_ok(r, spider=self.spider)

    def test_delegated_callback_serialization(self):
        r = Request(
            "http://www.example.com",
            callback=self.spider.delegated_callback,
            errback=self.spider.handle_error,
        )
        self.assert_serializes_ok(r, spider=self.spider)

    def test_unserializable_callback1(self):
        r = Request("http://www.example.com", callback=lambda x: x)
        self.assertRaises(ValueError, r.to_dict, spider=self.spider)

    def test_unserializable_callback2(self):
        r = Request("http://www.example.com", callback=self.spider.parse_item)
        self.assertRaises(ValueError, r.to_dict, spider=None)

    def test_unserializable_callback3(self):
        """Parser method is removed or replaced dynamically."""

        class MySpider(Spider):
            name = "my_spider"

            def parse(self, response):
                pass

        spider = MySpider()
        r = Request("http://www.example.com", callback=spider.parse)
        setattr(spider, "parse", None)
        self.assertRaises(ValueError, r.to_dict, spider=spider)

    def test_callback_not_available(self):
        """Callback method is not available in the spider passed to from_dict"""
        spider = TestSpiderDelegation()
        r = Request("http://www.example.com", callback=spider.delegated_callback)
        d = r.to_dict(spider=spider)
        self.assertRaises(ValueError, request_from_dict, d, spider=Spider("foo"))


class DeprecatedMethodsRequestSerializationTest(RequestSerializationTest):
    def assert_serializes_ok(self, request, spider=None):
        with self.assertWarns(
            category=ScrapyDeprecationWarning,
            msg=(
                "Module scrapy.utils.reqser is deprecated, please use request.to_dict method"
                " and/or scrapy.utils.request.request_from_dict instead"
            )
        ):
            request_copy = request_from_dict(request.to_dict(spider=spider), spider)
            self.assert_same_request(request, request_copy)


class TestSpiderMixin:
    def __mixin_callback(self, response):
        pass


class TestSpiderDelegation:
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


class TestSpider(Spider, TestSpiderMixin):
    name = "test"
    parse_item_reference = parse_item
    handle_error_reference = handle_error
    __parse_item_reference = private_parse_item
    __handle_error_reference = private_handle_error

    def __init__(self):
        self.delegated_callback = TestSpiderDelegation().delegated_callback

    def parse_item(self, response):
        pass

    def handle_error(self, failure):
        pass

    def __parse_item_private(self, response):
        pass