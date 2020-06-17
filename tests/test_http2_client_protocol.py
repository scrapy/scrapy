import os
import shutil

from twisted.internet import defer, reactor
from twisted.internet.endpoints import connectProtocol, SSL4ClientEndpoint
from twisted.internet.ssl import optionsForClientTLS
from twisted.protocols.policies import WrappingFactory
from twisted.python.filepath import FilePath
from twisted.trial import unittest
from twisted.web import static, server

from scrapy.core.http2.protocol import H2ClientProtocol
from scrapy.http import Request
from tests.mockserver import ssl_context_factory


class Http2ClientProtocolTestCase(unittest.TestCase):
    scheme = 'https'

    # only used for HTTPS tests
    file_key = 'keys/localhost.key'
    file_certificate = 'keys/localhost.crt'

    def setUp(self):
        # Start server for testing
        self.path_temp = self.mktemp()
        os.mkdir(self.path_temp)
        FilePath(self.path_temp).child('file').setContent(b"0123456789")
        r = static.File(self.path_temp)

        self.site = server.Site(r, timeout=None)
        self.wrapper = WrappingFactory(self.site)
        self.host = 'localhost'
        if self.scheme is 'https':
            self.port = reactor.listenSSL(
                0, self.wrapper,
                ssl_context_factory(self.file_key, self.file_certificate),
                interface=self.host
            )
        else:
            self.port = reactor.listenTCP(0, self.wrapper, interface=self.host)

        self.port_number = self.port.getHost().port

        # Connect to the server using the custom HTTP2ClientProtocol
        options = optionsForClientTLS(
            hostname=self.host,
            acceptableProtocols=[b'h2']
        )

        self.protocol = H2ClientProtocol()

        connectProtocol(
            endpoint=SSL4ClientEndpoint(reactor, self.host, self.port_number, options),
            protocol=self.protocol
        )

    def getURL(self, path):
        return "%s://%s:%d/%s" % (self.scheme, self.host, self.port_number, path)

    @defer.inlineCallbacks
    def tearDown(self):
        yield self.port.stopListening()
        shutil.rmtree(self.path_temp)

    def test_download(self):
        request = Request(self.getURL('file'))
        d = self.protocol.request(request)
        d.addCallback(lambda response: response.body)
        d.addCallback(self.assertEqual, b"0123456789")
        return d
