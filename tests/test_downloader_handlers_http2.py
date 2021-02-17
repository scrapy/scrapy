from unittest import mock

from twisted.internet import defer, error, reactor
from twisted.trial import unittest
from twisted.web import server
from twisted.web.error import SchemeNotSupported

from scrapy.core.downloader.handlers.http2 import H2DownloadHandler
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


class Https2TestCase(Https11TestCase):
    scheme = 'https'
    download_handler_cls = H2DownloadHandler
    HTTP2_DATALOSS_SKIP_REASON = "Content-Length mismatch raises InvalidBodyLengthError"

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


class Https2CustomCiphers(Https11CustomCiphers):
    scheme = 'https'
    download_handler_cls = H2DownloadHandler


class Http2MockServerTestCase(Http11MockServerTestCase):
    """HTTP 2.0 test case with MockServer"""
    settings_dict = {
        'DOWNLOAD_HANDLERS': {
            'https': 'scrapy.core.downloader.handlers.http2.H2DownloadHandler'
        }
    }


class Https2ProxyTestCase(Http11ProxyTestCase):
    # only used for HTTPS tests
    keyfile = 'keys/localhost.key'
    certfile = 'keys/localhost.crt'

    scheme = 'https'
    host = u'127.0.0.1'

    download_handler_cls = H2DownloadHandler
    expected_http_proxy_request_body = b'/'

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

        http_proxy = '%s?noconnect' % self.getURL('')
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
