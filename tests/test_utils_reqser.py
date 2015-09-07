# -*- coding: utf-8 -*-
import unittest

from scrapy.http import Request
from scrapy.spiders import Spider
from scrapy.utils.reqser import request_to_dict, request_from_dict


class RequestSerializationTest(unittest.TestCase):

    def setUp(self):
        self.spider = TestSpider()

    def test_basic(self):
        r = Request("http://www.example.com")
        self._assert_serializes_ok(r)

    def test_all_attributes(self):
        r = Request("http://www.example.com",
            callback='parse_item',
            errback='handle_error',
            method="POST",
            body=b"some body",
            headers={'content-encoding': 'text/html; charset=latin-1'},
            cookies={'currency': u'руб'},
            encoding='latin-1',
            priority=20,
            meta={'a': 'b'})
        self._assert_serializes_ok(r)

    def test_latin1_body(self):
        r = Request("http://www.example.com", body=b"\xa3")
        self._assert_serializes_ok(r)

    def test_utf8_body(self):
        r = Request("http://www.example.com", body=b"\xc2\xa3")
        self._assert_serializes_ok(r)

    def _assert_serializes_ok(self, request, spider=None):
        d = request_to_dict(request, spider=spider)
        request2 = request_from_dict(d, spider=spider)
        self._assert_same_request(request, request2)

    def _assert_same_request(self, r1, r2):
        self.assertEqual(r1.url, r2.url)
        self.assertEqual(r1.callback, r2.callback)
        self.assertEqual(r1.errback, r2.errback)
        self.assertEqual(r1.method, r2.method)
        self.assertEqual(r1.body, r2.body)
        self.assertEqual(r1.headers, r2.headers)
        self.assertEqual(r1.cookies, r2.cookies)
        self.assertEqual(r1.meta, r2.meta)
        self.assertEqual(r1._encoding, r2._encoding)
        self.assertEqual(r1.priority, r2.priority)
        self.assertEqual(r1.dont_filter, r2.dont_filter)

    def test_callback_serialization(self):
        r = Request("http://www.example.com", callback=self.spider.parse_item,
                    errback=self.spider.handle_error)
        self._assert_serializes_ok(r, spider=self.spider)

    def test_unserializable_callback1(self):
        r = Request("http://www.example.com", callback=lambda x: x)
        self.assertRaises(ValueError, request_to_dict, r)
        self.assertRaises(ValueError, request_to_dict, r, spider=self.spider)

    def test_unserializable_callback2(self):
        r = Request("http://www.example.com", callback=self.spider.parse_item)
        self.assertRaises(ValueError, request_to_dict, r)


class TestSpider(Spider):
    name = 'test'

    def parse_item(self, response):
        pass

    def handle_error(self, failure):
        pass
