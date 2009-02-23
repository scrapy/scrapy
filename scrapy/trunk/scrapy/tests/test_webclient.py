"""
Tests borrowed from the twisted.web.client tests.
"""
from urlparse import urlparse

from twisted.trial import unittest
from twisted.web import server, static
from twisted.internet import reactor, defer

from scrapy.core.downloader.webclient import ScrapyHTTPClientFactory
from scrapy.http import Url

class ParseUrlTestCase(unittest.TestCase):
    """Test URL parsing facility and defaults values."""

    def _parse(self, url):
        f = ScrapyHTTPClientFactory(Url(url))
        return (f.scheme, f.host, f.port, f.path)

    def testParse(self):
        scheme, host, port, path = self._parse("http://127.0.0.1/?param=value")
        self.assertEquals(path, "/?param=value")
        self.assertEquals(port, 80)
        scheme, host, port, path = self._parse("http://127.0.0.1/")
        self.assertEquals(path, "/")
        self.assertEquals(port, 80)
        scheme, host, port, path = self._parse("https://127.0.0.1/")
        self.assertEquals(path, "/")
        self.assertEquals(port, 443)
        scheme, host, port, path = self._parse("http://spam:12345/")
        self.assertEquals(port, 12345)
        scheme, host, port, path = self._parse("http://foo ")
        self.assertEquals(host, "foo")
        self.assertEquals(path, "/")
        scheme, host, port, path = self._parse("http://egg:7890")
        self.assertEquals(port, 7890)
        self.assertEquals(host, "egg")
        self.assertEquals(path, "/")

    def test_externalUnicodeInterference(self):
        """
        L{client._parse} should return C{str} for the scheme, host, and path
        elements of its return tuple, even when passed an URL which has
        previously been passed to L{urlparse} as a C{unicode} string.
        """
        badInput = u'http://example.com/path'
        goodInput = badInput.encode('ascii')
        urlparse(badInput)
        scheme, host, port, path = self._parse(goodInput)
        self.assertTrue(isinstance(scheme, str))
        self.assertTrue(isinstance(host, str))
        self.assertTrue(isinstance(path, str))


class FakeTransport:
    disconnecting = False

    def __init__(self):
        self.data = []

    def write(self, stuff):
        self.data.append(stuff)


class CookieTestCase(unittest.TestCase):

    def _listen(self, site):
        return reactor.listenTCP(0, site, interface="127.0.0.1")

    def setUp(self):
        root = static.Data('El toro!', 'text/plain')
        site = server.Site(root, timeout=None)
        self.port = self._listen(site)
        self.portno = self.port.getHost().port

    def tearDown(self):
        return self.port.stopListening()

    def testMalformedCookieHeaderParsing(self):
        d = defer.Deferred()
        factory = ScrapyHTTPClientFactory('http://foo.example.com/')
        proto = factory.buildProtocol('127.42.42.42')
        proto.transport = FakeTransport()
        proto.connectionMade()
        for line in [
            '200 Ok',
            'Squash: yes',
            'Hands: stolen',
            'Set-Cookie: CUSTOMER=WILE_E_COYOTE; path=/; expires=Wednesday, 09-Nov-99 23:12:40 GMT',
            'Set-Cookie: PART_NUMBER=ROCKET_LAUNCHER_0001; path=/',
            'Set-Cookie: SHIPPING=FEDEX; path=/foo',
            'Set-Cookie: COUNTRY=UY; path=/foo',
            'Set-Cookie: GOOD_CUSTOMER;',
            'Set-Cookie: NO_A_BOT;',
            '',
            'body',
            'more body',
            ]:
            proto.dataReceived(line + '\r\n')
        self.assertEquals(proto.transport.data,
                          ['GET / HTTP/1.0\r\n',
                           'Host: foo.example.com\r\n',
                           'User-Agent: Twisted PageGetter\r\n',
                           '\r\n'])
        self.assertEquals(factory.cookies,
                          {
            'CUSTOMER': 'WILE_E_COYOTE',
            'PART_NUMBER': 'ROCKET_LAUNCHER_0001',
            'SHIPPING': 'FEDEX',
            'COUNTRY': 'UY',
            })

