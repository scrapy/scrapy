import unittest

from scrapy.downloadermiddlewares.uriuserinfo import UriUserInfoMiddleware
from scrapy.http import Request
from scrapy.spiders import Spider


class AbstractWrapper:
    """Class to define base test case classes that can be inherited but are not
    executed themselves."""

    class BaseTestCase(unittest.TestCase):
        def setUp(self):
            self.mw = UriUserInfoMiddleware()
            self.spider = Spider("bar")

        def tearDown(self):
            del self.mw

    class ProtocolTestCase(BaseTestCase):
        def test_username_and_password(self):
            req = Request(f"{self.protocol}://foo:bar@example.com/")
            userinfoless_url = f"{self.protocol}://example.com/"
            processed_request = self.mw.process_request(req, self.spider)
            assert processed_request.url == userinfoless_url
            self.assertEqual(req.meta[self.username_field], "foo")
            self.assertEqual(req.meta[self.password_field], "bar")

        def test_username_and_empty_password(self):
            req = Request(f"{self.protocol}://foo:@example.com/")
            userinfoless_url = f"{self.protocol}://example.com/"
            processed_request = self.mw.process_request(req, self.spider)
            assert processed_request.url == userinfoless_url
            self.assertEqual(req.meta[self.username_field], "foo")
            self.assertEqual(req.meta[self.password_field], "")

        def test_username_and_no_password(self):
            req = Request(f"{self.protocol}://foo@example.com/")
            userinfoless_url = f"{self.protocol}://example.com/"
            processed_request = self.mw.process_request(req, self.spider)
            assert processed_request.url == userinfoless_url
            self.assertEqual(req.meta[self.username_field], "foo")
            self.assertNotIn(self.password_field, req.meta)

        def test_empty_username_and_nonempty_password(self):
            req = Request(f"{self.protocol}://:bar@example.com/")
            userinfoless_url = f"{self.protocol}://example.com/"
            processed_request = self.mw.process_request(req, self.spider)
            assert processed_request.url == userinfoless_url
            self.assertEqual(req.meta[self.username_field], "")
            self.assertEqual(req.meta[self.password_field], "bar")

        def test_no_username_and_no_password(self):
            req = Request(f"{self.protocol}://example.com/")
            assert self.mw.process_request(req, self.spider) is None
            self.assertNotIn(self.username_field, req.meta)
            self.assertNotIn(self.password_field, req.meta)

        def test_unquoting(self):
            req = Request(f"{self.protocol}://foo%3A:b%40r@example.com/")
            userinfoless_url = f"{self.protocol}://example.com/"
            processed_request = self.mw.process_request(req, self.spider)
            assert processed_request.url == userinfoless_url
            self.assertEqual(req.meta[self.username_field], "foo:")
            self.assertEqual(req.meta[self.password_field], "b@r")


class FTPTest(AbstractWrapper.ProtocolTestCase):
    protocol = "ftp"
    username_field = "ftp_user"
    password_field = "ftp_password"


class HTTPTest(AbstractWrapper.ProtocolTestCase):
    protocol = "http"
    username_field = "http_user"
    password_field = "http_pass"


class HTTPSTest(AbstractWrapper.ProtocolTestCase):
    protocol = "https"
    username_field = "http_user"
    password_field = "http_pass"


class UnhandledProtocolTest(AbstractWrapper.BaseTestCase):
    protocol = "s3"

    def test_unhandled_protocol(self):
        req = Request(f"{self.protocol}://foo:bar@example.com/")
        processed_request = self.mw.process_request(req, self.spider)
        assert processed_request is None
        assert not req.meta
