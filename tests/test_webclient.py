"""
from twisted.internet import defer
Tests borrowed from the twisted.web.client tests.
"""
import os
import shutil

import OpenSSL.SSL
from twisted.trial import unittest
from twisted.web import server, static, util, resource
from twisted.internet import reactor, defer
try:
    from twisted.internet.testing import StringTransport
except ImportError:
    # deprecated in Twisted 19.7.0
    # (remove once we bump our requirement past that version)
    from twisted.test.proto_helpers import StringTransport
from twisted.python.filepath import FilePath
from twisted.protocols.policies import WrappingFactory
from twisted.internet.defer import inlineCallbacks
from twisted.web.test.test_webclient import (
    ForeverTakingResource,
    ErrorResource,
    NoLengthResource,
    HostHeaderResource,
    PayloadResource,
    BrokenDownloadResource,
)

from scrapy.core.downloader import webclient as client
from scrapy.core.downloader.contextfactory import ScrapyClientContextFactory
from scrapy.http import Request, Headers
from scrapy.settings import Settings
from scrapy.utils.misc import create_instance
from scrapy.utils.python import to_bytes, to_unicode
from tests.mockserver import ssl_context_factory


def getPage(url, contextFactory=None, response_transform=None, *args, **kwargs):
    """Adapted version of twisted.web.client.getPage"""
    def _clientfactory(url, *args, **kwargs):
        url = to_unicode(url)
        timeout = kwargs.pop('timeout', 0)
        f = client.ScrapyHTTPClientFactory(
            Request(url, *args, **kwargs), timeout=timeout)
        f.deferred.addCallback(response_transform or (lambda r: r.body))
        return f

    from twisted.web.client import _makeGetterFactory
    return _makeGetterFactory(
        to_bytes(url), _clientfactory, contextFactory=contextFactory, *args, **kwargs
    ).deferred


class ParseUrlTestCase(unittest.TestCase):
    """Test URL parsing facility and defaults values."""

    def _parse(self, url):
        f = client.ScrapyHTTPClientFactory(Request(url))
        return (f.scheme, f.netloc, f.host, f.port, f.path)

    def testParse(self):
        lip = '127.0.0.1'
        tests = (
            ("http://127.0.0.1?c=v&c2=v2#fragment", ('http', lip, lip, 80, '/?c=v&c2=v2')),
            ("http://127.0.0.1/?c=v&c2=v2#fragment", ('http', lip, lip, 80, '/?c=v&c2=v2')),
            ("http://127.0.0.1/foo?c=v&c2=v2#frag", ('http', lip, lip, 80, '/foo?c=v&c2=v2')),
            ("http://127.0.0.1:100?c=v&c2=v2#fragment", ('http', lip + ':100', lip, 100, '/?c=v&c2=v2')),
            ("http://127.0.0.1:100/?c=v&c2=v2#frag", ('http', lip + ':100', lip, 100, '/?c=v&c2=v2')),
            ("http://127.0.0.1:100/foo?c=v&c2=v2#frag", ('http', lip + ':100', lip, 100, '/foo?c=v&c2=v2')),

            ("http://127.0.0.1", ('http', lip, lip, 80, '/')),
            ("http://127.0.0.1/", ('http', lip, lip, 80, '/')),
            ("http://127.0.0.1/foo", ('http', lip, lip, 80, '/foo')),
            ("http://127.0.0.1?param=value", ('http', lip, lip, 80, '/?param=value')),
            ("http://127.0.0.1/?param=value", ('http', lip, lip, 80, '/?param=value')),
            ("http://127.0.0.1:12345/foo", ('http', lip + ':12345', lip, 12345, '/foo')),
            ("http://spam:12345/foo", ('http', 'spam:12345', 'spam', 12345, '/foo')),
            ("http://spam.test.org/foo", ('http', 'spam.test.org', 'spam.test.org', 80, '/foo')),

            ("https://127.0.0.1/foo", ('https', lip, lip, 443, '/foo')),
            ("https://127.0.0.1/?param=value", ('https', lip, lip, 443, '/?param=value')),
            ("https://127.0.0.1:12345/", ('https', lip + ':12345', lip, 12345, '/')),

            ("http://scrapytest.org/foo ", ('http', 'scrapytest.org', 'scrapytest.org', 80, '/foo')),
            ("http://egg:7890 ", ('http', 'egg:7890', 'egg', 7890, '/')),
        )

        for url, test in tests:
            test = tuple(
                to_bytes(x) if not isinstance(x, int) else x for x in test)
            self.assertEqual(client._parse(url), test, url)


class ScrapyHTTPPageGetterTests(unittest.TestCase):

    def test_earlyHeaders(self):
        # basic test stolen from twisted HTTPageGetter
        factory = client.ScrapyHTTPClientFactory(Request(
            url='http://foo/bar',
            body="some data",
            headers={
                'Host': 'example.net',
                'User-Agent': 'fooble',
                'Cookie': 'blah blah',
                'Content-Length': '12981',
                'Useful': 'value'}))

        self._test(
            factory,
            b"GET /bar HTTP/1.0\r\n"
            b"Content-Length: 9\r\n"
            b"Useful: value\r\n"
            b"Connection: close\r\n"
            b"User-Agent: fooble\r\n"
            b"Host: example.net\r\n"
            b"Cookie: blah blah\r\n"
            b"\r\n"
            b"some data")

        # test minimal sent headers
        factory = client.ScrapyHTTPClientFactory(Request('http://foo/bar'))
        self._test(
            factory,
            b"GET /bar HTTP/1.0\r\n"
            b"Host: foo\r\n"
            b"\r\n")

        # test a simple POST with body and content-type
        factory = client.ScrapyHTTPClientFactory(Request(
            method='POST',
            url='http://foo/bar',
            body='name=value',
            headers={'Content-Type': 'application/x-www-form-urlencoded'}))

        self._test(
            factory,
            b"POST /bar HTTP/1.0\r\n"
            b"Host: foo\r\n"
            b"Connection: close\r\n"
            b"Content-Type: application/x-www-form-urlencoded\r\n"
            b"Content-Length: 10\r\n"
            b"\r\n"
            b"name=value")

        # test a POST method with no body provided
        factory = client.ScrapyHTTPClientFactory(Request(
            method='POST',
            url='http://foo/bar'
        ))

        self._test(
            factory,
            b"POST /bar HTTP/1.0\r\n"
            b"Host: foo\r\n"
            b"Content-Length: 0\r\n"
            b"\r\n")

        # test with single and multivalued headers
        factory = client.ScrapyHTTPClientFactory(Request(
            url='http://foo/bar',
            headers={
                'X-Meta-Single': 'single',
                'X-Meta-Multivalued': ['value1', 'value2'],
            },
        ))

        self._test(
            factory,
            b"GET /bar HTTP/1.0\r\n"
            b"Host: foo\r\n"
            b"X-Meta-Multivalued: value1\r\n"
            b"X-Meta-Multivalued: value2\r\n"
            b"X-Meta-Single: single\r\n"
            b"\r\n")

        # same test with single and multivalued headers but using Headers class
        factory = client.ScrapyHTTPClientFactory(Request(
            url='http://foo/bar',
            headers=Headers({
                'X-Meta-Single': 'single',
                'X-Meta-Multivalued': ['value1', 'value2'],
            }),
        ))

        self._test(
            factory,
            b"GET /bar HTTP/1.0\r\n"
            b"Host: foo\r\n"
            b"X-Meta-Multivalued: value1\r\n"
            b"X-Meta-Multivalued: value2\r\n"
            b"X-Meta-Single: single\r\n"
            b"\r\n")

    def _test(self, factory, testvalue):
        transport = StringTransport()
        protocol = client.ScrapyHTTPPageGetter()
        protocol.factory = factory
        protocol.makeConnection(transport)
        self.assertEqual(
            set(transport.value().splitlines()),
            set(testvalue.splitlines()))
        return testvalue

    def test_non_standard_line_endings(self):
        # regression test for: http://dev.scrapy.org/ticket/258
        factory = client.ScrapyHTTPClientFactory(Request(
            url='http://foo/bar'))
        protocol = client.ScrapyHTTPPageGetter()
        protocol.factory = factory
        protocol.headers = Headers()
        protocol.dataReceived(b"HTTP/1.0 200 OK\n")
        protocol.dataReceived(b"Hello: World\n")
        protocol.dataReceived(b"Foo: Bar\n")
        protocol.dataReceived(b"\n")
        self.assertEqual(protocol.headers, Headers({'Hello': ['World'], 'Foo': ['Bar']}))


class EncodingResource(resource.Resource):
    out_encoding = 'cp1251'

    def render(self, request):
        body = to_unicode(request.content.read())
        request.setHeader(b'content-encoding', self.out_encoding)
        return body.encode(self.out_encoding)


class WebClientTestCase(unittest.TestCase):
    def _listen(self, site):
        return reactor.listenTCP(0, site, interface="127.0.0.1")

    def setUp(self):
        self.tmpname = self.mktemp()
        os.mkdir(self.tmpname)
        FilePath(self.tmpname).child("file").setContent(b"0123456789")
        r = static.File(self.tmpname)
        r.putChild(b"redirect", util.Redirect(b"/file"))
        r.putChild(b"wait", ForeverTakingResource())
        r.putChild(b"error", ErrorResource())
        r.putChild(b"nolength", NoLengthResource())
        r.putChild(b"host", HostHeaderResource())
        r.putChild(b"payload", PayloadResource())
        r.putChild(b"broken", BrokenDownloadResource())
        r.putChild(b"encoding", EncodingResource())
        self.site = server.Site(r, timeout=None)
        self.wrapper = WrappingFactory(self.site)
        self.port = self._listen(self.wrapper)
        self.portno = self.port.getHost().port

    @inlineCallbacks
    def tearDown(self):
        yield self.port.stopListening()
        shutil.rmtree(self.tmpname)

    def getURL(self, path):
        return f"http://127.0.0.1:{self.portno}/{path}"

    def testPayload(self):
        s = "0123456789" * 10
        return getPage(self.getURL("payload"), body=s).addCallback(
            self.assertEqual, to_bytes(s))

    def testHostHeader(self):
        # if we pass Host header explicitly, it should be used, otherwise
        # it should extract from url
        return defer.gatherResults([
            getPage(self.getURL("host")).addCallback(
                self.assertEqual, to_bytes(f"127.0.0.1:{self.portno}")),
            getPage(self.getURL("host"), headers={"Host": "www.example.com"}).addCallback(
                self.assertEqual, to_bytes("www.example.com"))])

    def test_getPage(self):
        """
        L{client.getPage} returns a L{Deferred} which is called back with
        the body of the response if the default method B{GET} is used.
        """
        d = getPage(self.getURL("file"))
        d.addCallback(self.assertEqual, b"0123456789")
        return d

    def test_getPageHead(self):
        """
        L{client.getPage} returns a L{Deferred} which is called back with
        the empty string if the method is C{HEAD} and there is a successful
        response code.
        """
        def _getPage(method):
            return getPage(self.getURL("file"), method=method)
        return defer.gatherResults([
            _getPage("head").addCallback(self.assertEqual, b""),
            _getPage("HEAD").addCallback(self.assertEqual, b"")])

    def test_timeoutNotTriggering(self):
        """
        When a non-zero timeout is passed to L{getPage} and the page is
        retrieved before the timeout period elapses, the L{Deferred} is
        called back with the contents of the page.
        """
        d = getPage(self.getURL("host"), timeout=100)
        d.addCallback(
            self.assertEqual, to_bytes(f"127.0.0.1:{self.portno}"))
        return d

    def test_timeoutTriggering(self):
        """
        When a non-zero timeout is passed to L{getPage} and that many
        seconds elapse before the server responds to the request. the
        L{Deferred} is errbacked with a L{error.TimeoutError}.
        """
        finished = self.assertFailure(
            getPage(self.getURL("wait"), timeout=0.000001),
            defer.TimeoutError)

        def cleanup(passthrough):
            # Clean up the server which is hanging around not doing
            # anything.
            connected = list(self.wrapper.protocols.keys())
            # There might be nothing here if the server managed to already see
            # that the connection was lost.
            if connected:
                connected[0].transport.loseConnection()
            return passthrough
        finished.addBoth(cleanup)
        return finished

    def testNotFound(self):
        return getPage(self.getURL('notsuchfile')).addCallback(self._cbNoSuchFile)

    def _cbNoSuchFile(self, pageData):
        self.assertIn(b'404 - No Such Resource', pageData)

    def testFactoryInfo(self):
        url = self.getURL('file')
        _, _, host, port, _ = client._parse(url)
        factory = client.ScrapyHTTPClientFactory(Request(url))
        reactor.connectTCP(to_unicode(host), port, factory)
        return factory.deferred.addCallback(self._cbFactoryInfo, factory)

    def _cbFactoryInfo(self, ignoredResult, factory):
        self.assertEqual(factory.status, b'200')
        self.assertTrue(factory.version.startswith(b'HTTP/'))
        self.assertEqual(factory.message, b'OK')
        self.assertEqual(factory.response_headers[b'content-length'], b'10')

    def testRedirect(self):
        return getPage(self.getURL("redirect")).addCallback(self._cbRedirect)

    def _cbRedirect(self, pageData):
        self.assertEqual(
            pageData,
            b'\n<html>\n    <head>\n        <meta http-equiv="refresh" content="0;URL=/file">\n'
            b'    </head>\n    <body bgcolor="#FFFFFF" text="#000000">\n    '
            b'<a href="/file">click here</a>\n    </body>\n</html>\n')

    def test_encoding(self):
        """ Test that non-standart body encoding matches
        Content-Encoding header """
        body = b'\xd0\x81\xd1\x8e\xd0\xaf'
        dfd = getPage(self.getURL('encoding'), body=body, response_transform=lambda r: r)
        return dfd.addCallback(self._check_Encoding, body)

    def _check_Encoding(self, response, original_body):
        content_encoding = to_unicode(response.headers[b'Content-Encoding'])
        self.assertEqual(content_encoding, EncodingResource.out_encoding)
        self.assertEqual(
            response.body.decode(content_encoding), to_unicode(original_body))


class WebClientSSLTestCase(unittest.TestCase):
    context_factory = None

    def _listen(self, site):
        return reactor.listenSSL(
            0, site,
            contextFactory=self.context_factory or ssl_context_factory(),
            interface="127.0.0.1")

    def getURL(self, path):
        return f"https://127.0.0.1:{self.portno}/{path}"

    def setUp(self):
        self.tmpname = self.mktemp()
        os.mkdir(self.tmpname)
        FilePath(self.tmpname).child("file").setContent(b"0123456789")
        r = static.File(self.tmpname)
        r.putChild(b"payload", PayloadResource())
        self.site = server.Site(r, timeout=None)
        self.wrapper = WrappingFactory(self.site)
        self.port = self._listen(self.wrapper)
        self.portno = self.port.getHost().port

    @inlineCallbacks
    def tearDown(self):
        yield self.port.stopListening()
        shutil.rmtree(self.tmpname)

    def testPayload(self):
        s = "0123456789" * 10
        return getPage(self.getURL("payload"), body=s).addCallback(
            self.assertEqual, to_bytes(s))


class WebClientCustomCiphersSSLTestCase(WebClientSSLTestCase):
    # we try to use a cipher that is not enabled by default in OpenSSL
    custom_ciphers = 'CAMELLIA256-SHA'
    context_factory = ssl_context_factory(cipher_string=custom_ciphers)

    def testPayload(self):
        s = "0123456789" * 10
        settings = Settings({'DOWNLOADER_CLIENT_TLS_CIPHERS': self.custom_ciphers})
        client_context_factory = create_instance(ScrapyClientContextFactory, settings=settings, crawler=None)
        return getPage(
            self.getURL("payload"), body=s, contextFactory=client_context_factory
        ).addCallback(self.assertEqual, to_bytes(s))

    def testPayloadDisabledCipher(self):
        s = "0123456789" * 10
        settings = Settings({'DOWNLOADER_CLIENT_TLS_CIPHERS': 'ECDHE-RSA-AES256-GCM-SHA384'})
        client_context_factory = create_instance(ScrapyClientContextFactory, settings=settings, crawler=None)
        d = getPage(self.getURL("payload"), body=s, contextFactory=client_context_factory)
        return self.assertFailure(d, OpenSSL.SSL.Error)
