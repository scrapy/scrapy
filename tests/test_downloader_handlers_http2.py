import json
from unittest import mock, skipIf

from pytest import mark
from testfixtures import LogCapture
from twisted.internet import defer, error, reactor
from twisted.trial import unittest
from twisted.web import server
from twisted.web.error import SchemeNotSupported
from twisted.web.http import H2_ENABLED

from scrapy.http import Request
from scrapy.spiders import Spider
from scrapy.utils.misc import create_instance
from scrapy.utils.test import get_crawler
from tests.mockserver import ssl_context_factory
from tests.test_downloader_handlers import (
    Https11TestCase, Https11CustomCiphers,
    Http11MockServerTestCase, Http11ProxyTestCase,
    UriResource
)


@skipIf(not H2_ENABLED, "HTTP/2 support in Twisted is not enabled")
class Https2TestCase(Https11TestCase):

    scheme = 'https'
    HTTP2_DATALOSS_SKIP_REASON = "Content-Length mismatch raises InvalidBodyLengthError"

    @classmethod
    def setUpClass(cls):
        from scrapy.core.downloader.handlers.http2 import H2DownloadHandler
        cls.download_handler_cls = H2DownloadHandler

    def test_protocol(self):
        request = Request(self.getURL("host"), method="GET")
        d = self.download_request(request, Spider("foo"))
        d.addCallback(lambda r: r.protocol)
        d.addCallback(self.assertEqual, "h2")
        return d

    @defer.inlineCallbacks
    def test_download_with_maxsize_very_large_file(self):
        with mock.patch('scrapy.core.http2.stream.logger') as logger:
            request = Request(self.getURL('largechunkedfile'))

            def check(logger):
                logger.error.assert_called_once_with(mock.ANY)

            d = self.download_request(request, Spider('foo', download_maxsize=1500))
            yield self.assertFailure(d, defer.CancelledError, error.ConnectionAborted)

            # As the error message is logged in the dataReceived callback, we
            # have to give a bit of time to the reactor to process the queue
            # after closing the connection.
            d = defer.Deferred()
            d.addCallback(check)
            reactor.callLater(.1, d.callback, logger)
            yield d

    @defer.inlineCallbacks
    def test_unsupported_scheme(self):
        request = Request("ftp://unsupported.scheme")
        d = self.download_request(request, Spider("foo"))
        yield self.assertFailure(d, SchemeNotSupported)

    def test_download_broken_content_cause_data_loss(self, url='broken'):
        raise unittest.SkipTest(self.HTTP2_DATALOSS_SKIP_REASON)

    def test_download_broken_chunked_content_cause_data_loss(self):
        raise unittest.SkipTest(self.HTTP2_DATALOSS_SKIP_REASON)

    def test_download_broken_content_allow_data_loss(self, url='broken'):
        raise unittest.SkipTest(self.HTTP2_DATALOSS_SKIP_REASON)

    def test_download_broken_chunked_content_allow_data_loss(self):
        raise unittest.SkipTest(self.HTTP2_DATALOSS_SKIP_REASON)

    def test_download_broken_content_allow_data_loss_via_setting(self, url='broken'):
        raise unittest.SkipTest(self.HTTP2_DATALOSS_SKIP_REASON)

    def test_download_broken_chunked_content_allow_data_loss_via_setting(self):
        raise unittest.SkipTest(self.HTTP2_DATALOSS_SKIP_REASON)

    def test_concurrent_requests_same_domain(self):
        spider = Spider('foo')

        request1 = Request(self.getURL('file'))
        d1 = self.download_request(request1, spider)
        d1.addCallback(lambda r: r.body)
        d1.addCallback(self.assertEqual, b"0123456789")

        request2 = Request(self.getURL('echo'), method='POST')
        d2 = self.download_request(request2, spider)
        d2.addCallback(lambda r: r.headers['Content-Length'])
        d2.addCallback(self.assertEqual, b"79")

        return defer.DeferredList([d1, d2])

    @mark.xfail(reason="https://github.com/python-hyper/h2/issues/1247")
    def test_connect_request(self):
        request = Request(self.getURL('file'), method='CONNECT')
        d = self.download_request(request, Spider('foo'))
        d.addCallback(lambda r: r.body)
        d.addCallback(self.assertEqual, b'')
        return d

    def test_custom_content_length_good(self):
        request = Request(self.getURL('contentlength'))
        custom_content_length = str(len(request.body))
        request.headers['Content-Length'] = custom_content_length
        d = self.download_request(request, Spider('foo'))
        d.addCallback(lambda r: r.text)
        d.addCallback(self.assertEqual, custom_content_length)
        return d

    def test_custom_content_length_bad(self):
        request = Request(self.getURL('contentlength'))
        actual_content_length = str(len(request.body))
        bad_content_length = str(len(request.body) + 1)
        request.headers['Content-Length'] = bad_content_length
        log = LogCapture()
        d = self.download_request(request, Spider('foo'))
        d.addCallback(lambda r: r.text)
        d.addCallback(self.assertEqual, actual_content_length)
        d.addCallback(
            lambda _: log.check_present(
                (
                    'scrapy.core.http2.stream',
                    'WARNING',
                    f'Ignoring bad Content-Length header '
                    f'{bad_content_length!r} of request {request}, sending '
                    f'{actual_content_length!r} instead',
                )
            )
        )
        d.addCallback(
            lambda _: log.uninstall()
        )
        return d

    def test_duplicate_header(self):
        request = Request(self.getURL('echo'))
        header, value1, value2 = 'Custom-Header', 'foo', 'bar'
        request.headers.appendlist(header, value1)
        request.headers.appendlist(header, value2)
        d = self.download_request(request, Spider('foo'))
        d.addCallback(lambda r: json.loads(r.text)['headers'][header])
        d.addCallback(self.assertEqual, [value1, value2])
        return d


class Https2WrongHostnameTestCase(Https2TestCase):
    tls_log_message = (
        'SSL connection certificate: issuer "/C=XW/ST=XW/L=The '
        'Internet/O=Scrapy/CN=www.example.com/emailAddress=test@example.com", '
        'subject "/C=XW/ST=XW/L=The '
        'Internet/O=Scrapy/CN=www.example.com/emailAddress=test@example.com"'
    )

    # above tests use a server certificate for "localhost",
    # client connection to "localhost" too.
    # here we test that even if the server certificate is for another domain,
    # "www.example.com" in this case,
    # the tests still pass
    keyfile = 'keys/example-com.key.pem'
    certfile = 'keys/example-com.cert.pem'


class Https2InvalidDNSId(Https2TestCase):
    """Connect to HTTPS hosts with IP while certificate uses domain names IDs."""

    def setUp(self):
        super(Https2InvalidDNSId, self).setUp()
        self.host = '127.0.0.1'


class Https2InvalidDNSPattern(Https2TestCase):
    """Connect to HTTPS hosts where the certificate are issued to an ip instead of a domain."""

    keyfile = 'keys/localhost.ip.key'
    certfile = 'keys/localhost.ip.crt'

    def setUp(self):
        try:
            from service_identity.exceptions import CertificateError  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("cryptography lib is too old")
        self.tls_log_message = (
            'SSL connection certificate: issuer "/C=IE/O=Scrapy/CN=127.0.0.1", '
            'subject "/C=IE/O=Scrapy/CN=127.0.0.1"'
        )
        super(Https2InvalidDNSPattern, self).setUp()


@skipIf(not H2_ENABLED, "HTTP/2 support in Twisted is not enabled")
class Https2CustomCiphers(Https11CustomCiphers):
    scheme = 'https'

    @classmethod
    def setUpClass(cls):
        from scrapy.core.downloader.handlers.http2 import H2DownloadHandler
        cls.download_handler_cls = H2DownloadHandler


class Http2MockServerTestCase(Http11MockServerTestCase):
    """HTTP 2.0 test case with MockServer"""
    settings_dict = {
        'DOWNLOAD_HANDLERS': {
            'https': 'scrapy.core.downloader.handlers.http2.H2DownloadHandler'
        }
    }


@skipIf(not H2_ENABLED, "HTTP/2 support in Twisted is not enabled")
class Https2ProxyTestCase(Http11ProxyTestCase):
    # only used for HTTPS tests
    keyfile = 'keys/localhost.key'
    certfile = 'keys/localhost.crt'

    scheme = 'https'
    host = '127.0.0.1'

    expected_http_proxy_request_body = b'/'

    @classmethod
    def setUpClass(cls):
        from scrapy.core.downloader.handlers.http2 import H2DownloadHandler
        cls.download_handler_cls = H2DownloadHandler

    def setUp(self):
        site = server.Site(UriResource(), timeout=None)
        self.port = reactor.listenSSL(
            0, site,
            ssl_context_factory(self.keyfile, self.certfile),
            interface=self.host
        )
        self.portno = self.port.getHost().port
        self.download_handler = create_instance(self.download_handler_cls, None, get_crawler())
        self.download_request = self.download_handler.download_request

    def getURL(self, path):
        return f"{self.scheme}://{self.host}:{self.portno}/{path}"

    def test_download_with_proxy_https_noconnect(self):
        def _test(response):
            self.assertEqual(response.status, 200)
            self.assertEqual(response.url, request.url)
            self.assertEqual(response.body, b'/')

        http_proxy = f"{self.getURL('')}?noconnect"
        request = Request('https://example.com', meta={'proxy': http_proxy})
        with self.assertWarnsRegex(
            Warning,
            r'Using HTTPS proxies in the noconnect mode is not supported by the '
            r'downloader handler.'
        ):
            return self.download_request(request, Spider('foo')).addCallback(_test)

    @defer.inlineCallbacks
    def test_download_with_proxy_https_timeout(self):
        with self.assertRaises(NotImplementedError):
            yield super(Https2ProxyTestCase, self).test_download_with_proxy_https_timeout()
