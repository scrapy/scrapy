from unittest import mock

from twisted.internet import error, reactor
from twisted.internet.defer import CancelledError, Deferred, DeferredList, inlineCallbacks
from twisted.trial.unittest import TestCase, SkipTest
from twisted.web.server import Site
from twisted.internet.endpoints import TCP4ServerEndpoint, SSL4ServerEndpoint
from scrapy.core.downloader.handlers.negotiation import HTTPNegotiateDownloadHandler
from scrapy.http import Request
from scrapy.spiders import Spider
from scrapy.utils.test import get_crawler
from tests.mockserver import ssl_context_factory, Root as MockServerRoot
from tests.spiders import SingleRequestSpider
from tests.test_downloader_handlers import (
    Https11TestCase, Https11CustomCiphers,
    Http11MockServerTestCase, Http11ProxyTestCase
)


class NegotiationTestCase(Https11TestCase):
    scheme = 'https'
    download_handler_cls = HTTPNegotiateDownloadHandler
    HTTP2_DATALOSS_SKIP_REASON = "Content-Length mismatch raises InvalidBodyLengthError"

    @inlineCallbacks
    def test_download_with_maxsize_very_large_file(self):
        with mock.patch('scrapy.core.http2.stream.logger') as logger:
            request = Request(self.getURL('largechunkedfile'))

            def check(logger):
                logger.error.assert_called_once_with(mock.ANY)

            d = self.download_request(request, Spider('foo', download_maxsize=1500))
            yield self.assertFailure(d, CancelledError, error.ConnectionAborted)

            # As the error message is logged in the dataReceived callback, we
            # have to give a bit of time to the reactor to process the queue
            # after closing the connection.
            d = Deferred()
            d.addCallback(check)
            reactor.callLater(.1, d.callback, logger)
            yield d

    def test_download_broken_content_cause_data_loss(self, url='broken'):
        raise SkipTest(self.HTTP2_DATALOSS_SKIP_REASON)

    def test_download_broken_chunked_content_cause_data_loss(self):
        raise SkipTest(self.HTTP2_DATALOSS_SKIP_REASON)

    def test_download_broken_content_allow_data_loss(self, url='broken'):
        raise SkipTest(self.HTTP2_DATALOSS_SKIP_REASON)

    def test_download_broken_chunked_content_allow_data_loss(self):
        raise SkipTest(self.HTTP2_DATALOSS_SKIP_REASON)

    def test_download_broken_content_allow_data_loss_via_setting(self, url='broken'):
        raise SkipTest(self.HTTP2_DATALOSS_SKIP_REASON)

    def test_download_broken_chunked_content_allow_data_loss_via_setting(self):
        raise SkipTest(self.HTTP2_DATALOSS_SKIP_REASON)


class NegotiationWrongHostnameTestCase(NegotiationTestCase):
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


class NegotiationInvalidDNSId(NegotiationTestCase):
    """Connect to HTTPS hosts with IP while certificate uses domain names IDs."""

    def setUp(self):
        super(NegotiationInvalidDNSId, self).setUp()
        self.host = '127.0.0.1'


class NegotiationInvalidDNSPattern(NegotiationTestCase):
    """Connect to HTTPS hosts where the certificate are issued to an ip instead of a domain."""

    keyfile = 'keys/localhost.ip.key'
    certfile = 'keys/localhost.ip.crt'

    def setUp(self):
        try:
            from service_identity.exceptions import CertificateError  # noqa: F401
        except ImportError:
            raise SkipTest("cryptography lib is too old")
        self.tls_log_message = (
            'SSL connection certificate: issuer "/C=IE/O=Scrapy/CN=127.0.0.1", '
            'subject "/C=IE/O=Scrapy/CN=127.0.0.1"'
        )
        super(NegotiationInvalidDNSPattern, self).setUp()


class NegotiationCustomCiphers(Https11CustomCiphers):
    scheme = 'https'
    download_handler_cls = HTTPNegotiateDownloadHandler


class NegotiationMockServerTestCase(Http11MockServerTestCase):
    # download_handler_cls = pass
    settings_dict = {
        'DOWNLOAD_HANDLERS': {
            'https': 'scrapy.core.downloader.handlers.negotiation.HTTPNegotiateDownloadHandler'
        }
    }


class NegotiationProxyTestCase(Http11ProxyTestCase):
    # only used for HTTPS tests
    download_handler_cls = HTTPNegotiateDownloadHandler


class ProtocolsSite(Site):
    def __init__(self, resource, acceptable_protocols, requestFactory=None, *args, **kwargs):
        super().__init__(resource, requestFactory, *args, **kwargs)
        self.acceptable_protocols = acceptable_protocols

    def acceptableProtocols(self):
        return self.acceptable_protocols


class NegotiationHttp11TestCase(TestCase):
    server_acceptable_protocols = [b'http/1.1']
    expected_negotiated_protocol = 'http/1.1'
    settings_dict = {
        'DOWNLOAD_HANDLERS': {
            'https': 'scrapy.core.downloader.handlers.negotiation.HTTPNegotiateDownloadHandler'
        }
    }

    @inlineCallbacks
    def setUp(self) -> None:
        root = MockServerRoot()
        site = ProtocolsSite(root, self.server_acceptable_protocols)
        context_factory = ssl_context_factory()

        self.hostname = u'localhost'
        https_endpoint = SSL4ServerEndpoint(reactor, 0, context_factory, interface=self.hostname)
        self.https_server = yield https_endpoint.listen(site)
        https_host = self.https_server.getHost()
        self.https_address = f'https://{https_host.host}:{https_host.port}'

        http_endpoint = TCP4ServerEndpoint(reactor, 0, interface=self.hostname)
        self.http_server = yield http_endpoint.listen(site)
        http_host = self.http_server.getHost()
        self.http_address = f'http://{http_host.host}:{http_host.port}'

    @inlineCallbacks
    def tearDown(self) -> None:
        yield self.http_server.stopListening()
        yield self.https_server.stopListening()

    def get_url(self, path, is_secure=True):
        if is_secure:
            return f'{self.https_address}{path}'

        return f'{self.http_address}{path}'

    @inlineCallbacks
    def _check_request_protocol(self, request: Request, expected_protocol: str):
        crawler = get_crawler(SingleRequestSpider, self.settings_dict)
        yield crawler.crawl(seed=request)
        failure = crawler.spider.meta.get('failure')
        self.assertTrue(failure is None)
        reason = crawler.spider.meta['close_reason']
        self.assertTrue(reason, 'finished')

        self.assertGreater(len(crawler.spider.meta['responses']), 0)
        for response in crawler.spider.meta['responses']:
            self.assertEqual(response._protocol, expected_protocol)

    def test_insecure_request_uses_http11(self):
        return self._check_request_protocol(
            Request(url=self.get_url('', is_secure=False)),
            'http/1.1'
        )

    def test_secure_request(self):
        return self._check_request_protocol(
            Request(url=self.get_url('', is_secure=True)),
            self.expected_negotiated_protocol
        )

    def test_multiple_requests_share_same_protocol(self):
        requests = []
        for _ in range(3):
            requests.append(self.test_secure_request())

        return DeferredList(requests, fireOnOneErrback=True)


class NegotiationHttp2TestCase(NegotiationHttp11TestCase):
    server_acceptable_protocols = [b'h2']
    expected_negotiated_protocol = 'h2'
