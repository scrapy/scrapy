# -*- coding: utf-8 -*-
import unittest
import sys

import six

from scrapy.http import Request, FormRequest
from scrapy.spiders import Spider
from scrapy.utils.reqser import request_to_dict, request_from_dict, _is_private_method, _mangle_private_name


class RequestSerializationTest(unittest.TestCase):

    def setUp(self):
        self.spider = TestSpider()

    def test_basic(self):
        r = Request("http://www.example.com")
        self._assert_serializes_ok(r)

    def test_all_attributes(self):
        r = Request("http://www.example.com",
            callback=self.spider.parse_item,
            errback=self.spider.handle_error,
            method="POST",
            body=b"some body",
            headers={'content-encoding': 'text/html; charset=latin-1'},
            cookies={'currency': u'руб'},
            encoding='latin-1',
            priority=20,
            meta={'a': 'b'},
            cb_kwargs={'k': 'v'},
            flags=['testFlag'])
        self._assert_serializes_ok(r, spider=self.spider)

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

    def test_private_callback_serialization(self):
        r = Request("http://www.example.com",
                    callback=self.spider._TestSpider__parse_item_private,
                    errback=self.spider.handle_error)
        self._assert_serializes_ok(r, spider=self.spider)

    def test_mixin_private_callback_serialization(self):
        if sys.version_info[0] < 3:
            return
        r = Request("http://www.example.com",
                    callback=self.spider._TestSpiderMixin__mixin_callback,
                    errback=self.spider.handle_error)
        self._assert_serializes_ok(r, spider=self.spider)

    def test_private_callback_name_matching(self):
        self.assertTrue(_is_private_method('__a'))
        self.assertTrue(_is_private_method('__a_'))
        self.assertTrue(_is_private_method('__a_a'))
        self.assertTrue(_is_private_method('__a_a_'))
        self.assertTrue(_is_private_method('__a__a'))
        self.assertTrue(_is_private_method('__a__a_'))
        self.assertTrue(_is_private_method('__a___a'))
        self.assertTrue(_is_private_method('__a___a_'))
        self.assertTrue(_is_private_method('___a'))
        self.assertTrue(_is_private_method('___a_'))
        self.assertTrue(_is_private_method('___a_a'))
        self.assertTrue(_is_private_method('___a_a_'))
        self.assertTrue(_is_private_method('____a_a_'))

        self.assertFalse(_is_private_method('_a'))
        self.assertFalse(_is_private_method('_a_'))
        self.assertFalse(_is_private_method('__a__'))
        self.assertFalse(_is_private_method('__'))
        self.assertFalse(_is_private_method('___'))
        self.assertFalse(_is_private_method('____'))

    def _assert_mangles_to(self, obj, name):
        func = getattr(obj, name)
        self.assertEqual(
            _mangle_private_name(obj, func, func.__name__),
            name
        )

    def test_private_name_mangling(self):
        self._assert_mangles_to(
            self.spider, '_TestSpider__parse_item_private')
        if sys.version_info[0] >= 3:
            self._assert_mangles_to(
                self.spider, '_TestSpiderMixin__mixin_callback')

    def test_unserializable_callback1(self):
        r = Request("http://www.example.com", callback=lambda x: x)
        self.assertRaises(ValueError, request_to_dict, r)
        self.assertRaises(ValueError, request_to_dict, r, spider=self.spider)

    def test_unserializable_callback2(self):
        r = Request("http://www.example.com", callback=self.spider.parse_item)
        self.assertRaises(ValueError, request_to_dict, r)


class TestSpiderMixin(object):
    def __mixin_callback(self, response):
        pass


class TestSpider(Spider, TestSpiderMixin):
    name = 'test'

    def parse_item(self, response):
        pass

    def handle_error(self, failure):
        pass

    def __parse_item_private(self, response):
        pass


class CustomRequest(Request):
    pass
