import unittest
import warnings

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.http import Request, FormRequest
from scrapy.spiders import Spider


class CustomRequest(Request):
    pass


class RequestSerializationTest(unittest.TestCase):

    def setUp(self):
        self.spider = TestSpider()

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
            headers={'content-encoding': 'text/html; charset=latin-1'},
            cookies={'currency': 'руб'},
            encoding='latin-1',
            priority=20,
            meta={'a': 'b'},
            cb_kwargs={'k': 'v'},
            flags=['testFlag'],
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
        request2 = Request.from_dict(d, spider=spider)
        self._assert_same_request(request, request2)

    def _assert_same_request(self, r1, r2):
        self.assertEqual(r1.__class__, r2.__class__)
        self.assertEqual(r1.url, r2.url)
        self.assertEqual(r1.callback, r2.callback)
        self.assertEqual(r1.errback, r2.errback)
        self.assertEqual(r1.method, r2.method)
        self.assertEqual(r1.body, r2.body)
        self.assertEqual(r1.headers, r2.headers)
        self.assertEqual(r1.cookies, r2.cookies)
        self.assertEqual(r1.meta, r2.meta)
        self.assertEqual(r1.cb_kwargs, r2.cb_kwargs)
        self.assertEqual(r1._encoding, r2._encoding)
        self.assertEqual(r1.priority, r2.priority)
        self.assertEqual(r1.dont_filter, r2.dont_filter)
        self.assertEqual(r1.flags, r2.flags)

    def test_request_class(self):
        r = FormRequest("http://www.example.com")
        self._assert_serializes_ok(r, spider=self.spider)
        r = CustomRequest("http://www.example.com")
        self._assert_serializes_ok(r, spider=self.spider)

    def test_callback_serialization(self):
        r = Request("http://www.example.com", callback=self.spider.parse_item,
                    errback=self.spider.handle_error)
        self._assert_serializes_ok(r, spider=self.spider)

    def test_reference_callback_serialization(self):
        r = Request("http://www.example.com",
                    callback=self.spider.parse_item_reference,
                    errback=self.spider.handle_error_reference)
        self._assert_serializes_ok(r, spider=self.spider)
        request_dict = r.to_dict(self.spider)
        self.assertEqual(request_dict['callback'], 'parse_item_reference')
        self.assertEqual(request_dict['errback'], 'handle_error_reference')

    def test_private_reference_callback_serialization(self):
        r = Request("http://www.example.com",
                    callback=self.spider._TestSpider__parse_item_reference,
                    errback=self.spider._TestSpider__handle_error_reference)
        self._assert_serializes_ok(r, spider=self.spider)
        request_dict = r.to_dict(self.spider)
        self.assertEqual(request_dict['callback'],
                         '_TestSpider__parse_item_reference')
        self.assertEqual(request_dict['errback'],
                         '_TestSpider__handle_error_reference')

    def test_private_callback_serialization(self):
        r = Request("http://www.example.com",
                    callback=self.spider._TestSpider__parse_item_private,
                    errback=self.spider.handle_error)
        self._assert_serializes_ok(r, spider=self.spider)

    def test_mixin_private_callback_serialization(self):
        r = Request("http://www.example.com",
                    callback=self.spider._TestSpiderMixin__mixin_callback,
                    errback=self.spider.handle_error)
        self._assert_serializes_ok(r, spider=self.spider)

    def test_delegated_callback_serialization(self):
        r = Request("http://www.example.com",
                    callback=self.spider.delegated_callback,
                    errback=self.spider.handle_error)
        self._assert_serializes_ok(r, spider=self.spider)

    def test_unserializable_callback1(self):
        r = Request("http://www.example.com", callback=lambda x: x)
        self.assertRaises(ValueError, r.to_dict)
        self.assertRaises(ValueError, r.to_dict, spider=self.spider)

    def test_unserializable_callback2(self):
        r = Request("http://www.example.com", callback=self.spider.parse_item)
        self.assertRaises(ValueError, r.to_dict)

    def test_unserializable_callback3(self):
        """Parser method is removed or replaced dynamically."""

        class MySpider(Spider):
            name = 'my_spider'

            def parse(self, response):
                pass

        spider = MySpider()
        r = Request("http://www.example.com", callback=spider.parse)
        setattr(spider, 'parse', None)
        self.assertRaises(ValueError, r.to_dict, spider=spider)

    def test_callback_not_available(self):
        """Callback method is not available in the spider passed to from_dict"""
        spider = TestSpiderDelegation()
        r = Request("http://www.example.com", callback=spider.delegated_callback)
        d = r.to_dict(spider=spider)
        self.assertRaises(ValueError, Request.from_dict, d, spider=Spider("foo"))


class DeprecatedMethodsRequestSerializationTest(RequestSerializationTest):
    @classmethod
    def setUpClass(cls):
        with warnings.catch_warnings(record=True) as w:
            from scrapy.utils.reqser import request_from_dict, request_to_dict  # noqa: F401
            assert len(w) == 1
            assert issubclass(w[0].category, ScrapyDeprecationWarning)
            assert "Module `scrapy.utils.reqser` is deprecated" in str(w[0].message)

    def _assert_serializes_ok(self, request, spider=None):
        from scrapy.utils.reqser import request_from_dict, request_to_dict
        d = request_to_dict(request, spider=spider)
        request2 = request_from_dict(d, spider=spider)
        self._assert_same_request(request, request2)


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
    name = 'test'
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
