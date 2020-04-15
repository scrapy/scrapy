import unittest

from scrapy.http import Request
from scrapy.downloadermiddlewares.uriuserinfo import UriUserinfoMiddleware
from scrapy.spiders import Spider


class BaseTestCase:

    class Implementation(unittest.TestCase):

        def setUp(self):
            self.mw = UriUserinfoMiddleware()
            self.spider = Spider('bar')

        def tearDown(self):
            del self.mw

        def test_username_and_password(self):
            req = Request('{}://foo:bar@scrapytest.org/'.format(self.protocol))
            assert self.mw.process_request(req, self.spider) is None
            self.assertEqual(req.meta[self.username_field], 'foo')
            self.assertEqual(req.meta[self.password_field], 'bar')

        def test_username_and_empty_password(self):
            req = Request('{}://foo:@scrapytest.org/'.format(self.protocol))
            assert self.mw.process_request(req, self.spider) is None
            self.assertEqual(req.meta[self.username_field], 'foo')
            self.assertEqual(req.meta[self.password_field], '')

        def test_username_and_no_password(self):
            req = Request('{}://foo@scrapytest.org/'.format(self.protocol))
            assert self.mw.process_request(req, self.spider) is None
            self.assertEqual(req.meta[self.username_field], 'foo')
            self.assertNotIn(self.password_field, req.meta)

        def test_empty_username_and_nonempty_password(self):
            req = Request('{}://:bar@scrapytest.org/'.format(self.protocol))
            assert self.mw.process_request(req, self.spider) is None
            self.assertEqual(req.meta[self.username_field], '')
            self.assertEqual(req.meta[self.password_field], 'bar')

        def test_no_username_and_no_password(self):
            req = Request('{}://scrapytest.org/'.format(self.protocol))
            assert self.mw.process_request(req, self.spider) is None
            self.assertNotIn(self.username_field, req.meta)
            self.assertNotIn(self.password_field, req.meta)

        def test_unquoting(self):
            req = Request(
                '{}://foo%3A:b%40r@scrapytest.org/'.format(self.protocol)
            )
            assert self.mw.process_request(req, self.spider) is None
            self.assertEqual(req.meta[self.username_field], 'foo:')
            self.assertEqual(req.meta[self.password_field], 'b@r')


class UriUserinfoMiddlewareFTPTest(BaseTestCase.Implementation):
    protocol = 'ftp'
    username_field = 'ftp_user'
    password_field = 'ftp_password'


class UriUserinfoMiddlewareHTTPTest(BaseTestCase.Implementation):
    protocol = 'http'
    username_field = 'http_user'
    password_field = 'http_pass'


class UriUserinfoMiddlewareHTTPSTest(BaseTestCase.Implementation):
    protocol = 'https'
    username_field = 'http_user'
    password_field = 'http_pass'
