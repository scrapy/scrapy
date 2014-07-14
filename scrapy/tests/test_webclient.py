"""
from twisted.internet import defer
Tests borrowed from the twisted.web.client tests.
"""
import os
from six.moves.urllib.parse import urlparse

from twisted.trial import unittest
from twisted.web import server, static, error, util
from twisted.internet import reactor, defer
from twisted.test.proto_helpers import StringTransport
from twisted.python.filepath import FilePath
from twisted.protocols.policies import WrappingFactory

from scrapy.core.downloader import webclient as client
from scrapy.http import Request, Headers


def getPage(url, contextFactory=None, *args, **kwargs):
    """Adapted version of twisted.web.client.getPage"""
    def _clientfactory(*args, **kwargs):
        timeout = kwargs.pop('timeout', 0)
        f = client.ScrapyHTTPClientFactory(Request(*args, **kwargs), timeout=timeout)
        f.deferred.addCallback(lambda r: r.body)
        return f

    from twisted.web.client import _makeGetterFactory
    return _makeGetterFactory(url, _clientfactory,
        contextFactory=contextFactory, *args, **kwargs).deferred


class ParseUrlTestCase(unittest.TestCase):
    """Test URL parsing facility and defaults values."""

    def _parse(self, url):
        f = client.ScrapyHTTPClientFactory(Request(url))
        return (f.scheme, f.netloc, f.host, f.port, f.path)

    def testParse(self):
        lip = '127.0.0.1'
        tests = (
    ("http://127.0.0.1?c=v&c2=v2#fragment",     ('http', lip, lip, 80, '/?c=v&c2=v2')),
    ("http://127.0.0.1/?c=v&c2=v2#fragment",    ('http', lip, lip, 80, '/?c=v&c2=v2')),
    ("http://127.0.0.1/foo?c=v&c2=v2#frag",     ('http', lip, lip, 80, '/foo?c=v&c2=v2')),
    ("http://127.0.0.1:100?c=v&c2=v2#fragment", ('http', lip+':100', lip, 100, '/?c=v&c2=v2')),
    ("http://127.0.0.1:100/?c=v&c2=v2#frag",    ('http', lip+':100', lip, 100, '/?c=v&c2=v2')),
    ("http://127.0.0.1:100/foo?c=v&c2=v2#frag", ('http', lip+':100', lip, 100, '/foo?c=v&c2=v2')),

    ("http://127.0.0.1",              ('http', lip, lip, 80, '/')),
    ("http://127.0.0.1/",             ('http', lip, lip, 80, '/')),
    ("http://127.0.0.1/foo",          ('http', lip, lip, 80, '/foo')),
    ("http://127.0.0.1?param=value",  ('http', lip, lip, 80, '/?param=value')),
    ("http://127.0.0.1/?param=value", ('http', lip, lip, 80, '/?param=value')),
    ("http://127.0.0.1:12345/foo",    ('http', lip+':12345', lip, 12345, '/foo')),
    ("http://spam:12345/foo",         ('http', 'spam:12345', 'spam', 12345, '/foo')),
    ("http://spam.test.org/foo",      ('http', 'spam.test.org', 'spam.test.org', 80, '/foo')),

    ("https://127.0.0.1/foo",         ('https', lip, lip, 443, '/foo')),
    ("https://127.0.0.1/?param=value", ('https', lip, lip, 443, '/?param=value')),
    ("https://127.0.0.1:12345/",      ('https', lip+':12345', lip, 12345, '/')),

    ("http://scrapytest.org/foo ",    ('http', 'scrapytest.org', 'scrapytest.org', 80, '/foo')),
    ("http://egg:7890 ",              ('http', 'egg:7890', 'egg', 7890, '/')),
    )

        for url, test in tests:
            self.assertEquals(client._parse(url), test, url)

    def test_externalUnicodeInterference(self):
        """
        L{client._parse} should return C{str} for the scheme, host, and path
        elements of its return tuple, even when passed an URL which has
        previously been passed to L{urlparse} as a C{unicode} string.
        """
        badInput = u'http://example.com/path'
        goodInput = badInput.encode('ascii')
        urlparse(badInput)
        scheme, netloc, host, port, path = self._parse(goodInput)
        self.assertTrue(isinstance(scheme, str))
        self.assertTrue(isinstance(netloc, str))
        self.assertTrue(isinstance(host, str))
        self.assertTrue(isinstance(path, str))
        self.assertTrue(isinstance(port, int))



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

        self._test(factory,
            "GET /bar HTTP/1.0\r\n"
            "Content-Length: 9\r\n"
            "Useful: value\r\n"
            "Connection: close\r\n"
            "User-Agent: fooble\r\n"
            "Host: example.net\r\n"
            "Cookie: blah blah\r\n"
            "\r\n"
            "some data")

        # test minimal sent headers
        factory = client.ScrapyHTTPClientFactory(Request('http://foo/bar'))
        self._test(factory,
            "GET /bar HTTP/1.0\r\n"
            "Host: foo\r\n"
            "\r\n")

        # test a simple POST with body and content-type
        factory = client.ScrapyHTTPClientFactory(Request(
            method='POST',
            url='http://foo/bar',
            body='name=value',
            headers={'Content-Type': 'application/x-www-form-urlencoded'}))

        self._test(factory,
            "POST /bar HTTP/1.0\r\n"
            "Host: foo\r\n"
            "Connection: close\r\n"
            "Content-Type: application/x-www-form-urlencoded\r\n"
            "Content-Length: 10\r\n"
            "\r\n"
            "name=value")

        # test with single and multivalued headers
        factory = client.ScrapyHTTPClientFactory(Request(
            url='http://foo/bar',
            headers={
                'X-Meta-Single': 'single',
                'X-Meta-Multivalued': ['value1', 'value2'],
                }))

        self._test(factory,
            "GET /bar HTTP/1.0\r\n"
            "Host: foo\r\n"
            "X-Meta-Multivalued: value1\r\n"
            "X-Meta-Multivalued: value2\r\n"
            "X-Meta-Single: single\r\n"
            "\r\n")

        # same test with single and multivalued headers but using Headers class
        factory = client.ScrapyHTTPClientFactory(Request(
            url='http://foo/bar',
            headers=Headers({
                'X-Meta-Single': 'single',
                'X-Meta-Multivalued': ['value1', 'value2'],
                })))

        self._test(factory,
            "GET /bar HTTP/1.0\r\n"
            "Host: foo\r\n"
            "X-Meta-Multivalued: value1\r\n"
            "X-Meta-Multivalued: value2\r\n"
            "X-Meta-Single: single\r\n"
            "\r\n")

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
        protocol.dataReceived("HTTP/1.0 200 OK\n")
        protocol.dataReceived("Hello: World\n")
        protocol.dataReceived("Foo: Bar\n")
        protocol.dataReceived("\n")
        self.assertEqual(protocol.headers,
            Headers({'Hello': ['World'], 'Foo': ['Bar']}))


from twisted.web.test.test_webclient import ForeverTakingResource, \
        ErrorResource, NoLengthResource, HostHeaderResource, \
        PayloadResource, BrokenDownloadResource

class WebClientTestCase(unittest.TestCase):
    def _listen(self, site):
        return reactor.listenTCP(0, site, interface="127.0.0.1")

    def setUp(self):
        name = self.mktemp()
        os.mkdir(name)
        FilePath(name).child("file").setContent("0123456789")
        r = static.File(name)
        r.putChild("redirect", util.Redirect("/file"))
        r.putChild("wait", ForeverTakingResource())
        r.putChild("error", ErrorResource())
        r.putChild("nolength", NoLengthResource())
        r.putChild("host", HostHeaderResource())
        r.putChild("payload", PayloadResource())
        r.putChild("broken", BrokenDownloadResource())
        self.site = server.Site(r, timeout=None)
        self.wrapper = WrappingFactory(self.site)
        self.port = self._listen(self.wrapper)
        self.portno = self.port.getHost().port

    def tearDown(self):
        return self.port.stopListening()

    def getURL(self, path):
        return "http://127.0.0.1:%d/%s" % (self.portno, path)

    def testPayload(self):
        s = "0123456789" * 10
        return getPage(self.getURL("payload"), body=s).addCallback(self.assertEquals, s)

    def testHostHeader(self):
        # if we pass Host header explicitly, it should be used, otherwise
        # it should extract from url
        return defer.gatherResults([
            getPage(self.getURL("host")).addCallback(self.assertEquals, "127.0.0.1:%d" % self.portno),
            getPage(self.getURL("host"), headers={"Host": "www.example.com"}).addCallback(self.assertEquals, "www.example.com")])


    def test_getPage(self):
        """
        L{client.getPage} returns a L{Deferred} which is called back with
        the body of the response if the default method B{GET} is used.
        """
        d = getPage(self.getURL("file"))
        d.addCallback(self.assertEquals, "0123456789")
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
            _getPage("head").addCallback(self.assertEqual, ""),
            _getPage("HEAD").addCallback(self.assertEqual, "")])


    def test_timeoutNotTriggering(self):
        """
        When a non-zero timeout is passed to L{getPage} and the page is
        retrieved before the timeout period elapses, the L{Deferred} is
        called back with the contents of the page.
        """
        d = getPage(self.getURL("host"), timeout=100)
        d.addCallback(self.assertEquals, "127.0.0.1:%d" % self.portno)
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
            connected = self.wrapper.protocols.keys()
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
        self.assert_('404 - No Such Resource' in pageData)

    def testFactoryInfo(self):
        url = self.getURL('file')
        scheme, netloc, host, port, path = client._parse(url)
        factory = client.ScrapyHTTPClientFactory(Request(url))
        reactor.connectTCP(host, port, factory)
        return factory.deferred.addCallback(self._cbFactoryInfo, factory)

    def _cbFactoryInfo(self, ignoredResult, factory):
        self.assertEquals(factory.status, '200')
        self.assert_(factory.version.startswith('HTTP/'))
        self.assertEquals(factory.message, 'OK')
        self.assertEquals(factory.response_headers['content-length'], '10')

    def testRedirect(self):
        return getPage(self.getURL("redirect")).addCallback(self._cbRedirect)

    def _cbRedirect(self, pageData):
        self.assertEquals(pageData,
                '\n<html>\n    <head>\n        <meta http-equiv="refresh" content="0;URL=/file">\n'
                '    </head>\n    <body bgcolor="#FFFFFF" text="#000000">\n    '
                '<a href="/file">click here</a>\n    </body>\n</html>\n')
