from urllib.parse import urlparse

from twisted.internet import reactor
from twisted.internet.endpoints import connectProtocol, SSL4ClientEndpoint
from twisted.internet.ssl import CertificateOptions
from twisted.trial import unittest

from scrapy.core.http2.protocol import H2ClientProtocol
from scrapy.http import Request, Response
from tests.mockserver import MockServer


class Http2ClientProtocolTestCase(unittest.TestCase):
    scheme = 'https'

    def setUp(self):
        # Start server for testing
        self.mockserver = MockServer()
        self.mockserver.__enter__()

        if self.scheme == 'https':
            self.url = urlparse(self.mockserver.https_address)
        else:
            self.url = urlparse(self.mockserver.http_address)

        self.protocol = H2ClientProtocol()

        # Connect to the server using the custom HTTP2ClientProtocol
        options = CertificateOptions(acceptableProtocols=[b'h2'])
        endpoint = SSL4ClientEndpoint(reactor, self.url.hostname, self.url.port, options)
        connectProtocol(endpoint, self.protocol)

    def getURL(self, path):
        return "{}://{}:{}/{}".format(self.url.scheme, self.url.hostname, self.url.port, path)

    def tearDown(self):
        self.mockserver.__exit__(None, None, None)

    def test_download(self):
        request = Request(self.getURL(''))

        def assert_response(response: Response):
            self.assertEqual(response.body, b'Scrapy mock HTTP server\n')
            self.assertEqual(response.status, 200)
            self.assertEqual(response.request, request)
            self.assertEqual(response.url, request.url)

        d = self.protocol.request(request)
        d.addCallback(assert_response)
        return d
