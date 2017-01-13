# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for the old L{twisted.web.client} APIs, C{getPage} and friends.
"""

from __future__ import division, absolute_import

import os
from errno import ENOSPC

try:
    from urlparse import urlparse, urljoin
except ImportError:
    from urllib.parse import urlparse, urljoin

from twisted.python.compat import networkString, nativeString, intToBytes
from twisted.trial import unittest
from twisted.web import server, client, error, resource
from twisted.web.static import Data
from twisted.web.util import Redirect
from twisted.internet import reactor, defer, interfaces
from twisted.python.filepath import FilePath
from twisted.python.log import msg
from twisted.protocols.policies import WrappingFactory
from twisted.test.proto_helpers import StringTransport

try:
    from twisted.internet import ssl
except:
    ssl = None

from twisted import test
serverPEM = FilePath(test.__file__).sibling('server.pem')
serverPEMPath = serverPEM.asBytesMode().path


class ExtendedRedirect(resource.Resource):
    """
    Redirection resource.

    The HTTP status code is set according to the C{code} query parameter.

    @type lastMethod: C{bytes}
    @ivar lastMethod: Last handled HTTP request method
    """
    isLeaf = True
    lastMethod = None


    def __init__(self, url):
        resource.Resource.__init__(self)
        self.url = url


    def render(self, request):
        if self.lastMethod:
            self.lastMethod = request.method
            return b"OK Thnx!"
        else:
            self.lastMethod = request.method
            code = int(request.args[b'code'][0])
            return self.redirectTo(self.url, request, code)


    def getChild(self, name, request):
        return self


    def redirectTo(self, url, request, code):
        request.setResponseCode(code)
        request.setHeader(b"location", url)
        return b"OK Bye!"



class ForeverTakingResource(resource.Resource):
    """
    L{ForeverTakingResource} is a resource which never finishes responding
    to requests.
    """
    def __init__(self, write=False):
        resource.Resource.__init__(self)
        self._write = write

    def render(self, request):
        if self._write:
            request.write(b'some bytes')
        return server.NOT_DONE_YET


class ForeverTakingNoReadingResource(resource.Resource):
    """
    L{ForeverTakingNoReadingResource} is a resource that never finishes
    responding and that removes itself from the read loop.
    """
    def __init__(self):
        resource.Resource.__init__(self)

    def render(self, request):
        # Stop the producing.
        request.transport.pauseProducing()
        return server.NOT_DONE_YET


class CookieMirrorResource(resource.Resource):
    def render(self, request):
        l = []
        for k,v in sorted(list(request.received_cookies.items())):
            l.append((nativeString(k), nativeString(v)))
        l.sort()
        return networkString(repr(l))

class RawCookieMirrorResource(resource.Resource):
    def render(self, request):
        header = request.getHeader(b'cookie')
        if header is None:
            return b'None'
        return networkString(repr(nativeString(header)))

class ErrorResource(resource.Resource):

    def render(self, request):
        request.setResponseCode(401)
        if request.args.get(b"showlength"):
            request.setHeader(b"content-length", b"0")
        return b""

class NoLengthResource(resource.Resource):

    def render(self, request):
        return b"nolength"



class HostHeaderResource(resource.Resource):
    """
    A testing resource which renders itself as the value of the host header
    from the request.
    """
    def render(self, request):
        return request.requestHeaders.getRawHeaders(b"host")[0]



class PayloadResource(resource.Resource):
    """
    A testing resource which renders itself as the contents of the request body
    as long as the request body is 100 bytes long, otherwise which renders
    itself as C{"ERROR"}.
    """
    def render(self, request):
        data = request.content.read()
        contentLength = request.requestHeaders.getRawHeaders(b"content-length")[0]
        if len(data) != 100 or int(contentLength) != 100:
            return b"ERROR"
        return data


class DelayResource(resource.Resource):

    def __init__(self, seconds):
        self.seconds = seconds

    def render(self, request):
        def response():
            request.write(b'some bytes')
            request.finish()
        reactor.callLater(self.seconds, response)
        return server.NOT_DONE_YET


class BrokenDownloadResource(resource.Resource):

    def render(self, request):
        # only sends 3 bytes even though it claims to send 5
        request.setHeader(b"content-length", b"5")
        request.write(b'abc')
        return b''

class CountingRedirect(Redirect):
    """
    A L{Redirect} resource that keeps track of the number of times the
    resource has been accessed.
    """
    def __init__(self, *a, **kw):
        Redirect.__init__(self, *a, **kw)
        self.count = 0

    def render(self, request):
        self.count += 1
        return Redirect.render(self, request)


class CountingResource(resource.Resource):
    """
    A resource that keeps track of the number of times it has been accessed.
    """
    def __init__(self):
        resource.Resource.__init__(self)
        self.count = 0

    def render(self, request):
        self.count += 1
        return b"Success"



class URLJoinTests(unittest.TestCase):
    """
    Tests for L{client._urljoin}.
    """
    def test_noFragments(self):
        """
        L{client._urljoin} does not include a fragment identifier in the
        resulting URL if neither the base nor the new path include a fragment
        identifier.
        """
        self.assertEqual(
            client._urljoin(b'http://foo.com/bar', b'/quux'),
            b'http://foo.com/quux')
        self.assertEqual(
            client._urljoin(b'http://foo.com/bar#', b'/quux'),
            b'http://foo.com/quux')
        self.assertEqual(
            client._urljoin(b'http://foo.com/bar', b'/quux#'),
            b'http://foo.com/quux')


    def test_preserveFragments(self):
        """
        L{client._urljoin} preserves the fragment identifier from either the
        new path or the base URL respectively, as specified in the HTTP 1.1 bis
        draft.

        @see: U{https://tools.ietf.org/html/draft-ietf-httpbis-p2-semantics-22#section-7.1.2}
        """
        self.assertEqual(
            client._urljoin(b'http://foo.com/bar#frag', b'/quux'),
            b'http://foo.com/quux#frag')
        self.assertEqual(
            client._urljoin(b'http://foo.com/bar', b'/quux#frag2'),
            b'http://foo.com/quux#frag2')
        self.assertEqual(
            client._urljoin(b'http://foo.com/bar#frag', b'/quux#frag2'),
            b'http://foo.com/quux#frag2')



class HTTPPageGetterTests(unittest.TestCase):
    """
    Tests for L{HTTPPagerGetter}, the HTTP client protocol implementation
    used to implement L{getPage}.
    """
    def test_earlyHeaders(self):
        """
        When a connection is made, L{HTTPPagerGetter} sends the headers from
        its factory's C{headers} dict.  If I{Host} or I{Content-Length} is
        present in this dict, the values are not sent, since they are sent with
        special values before the C{headers} dict is processed.  If
        I{User-Agent} is present in the dict, it overrides the value of the
        C{agent} attribute of the factory.  If I{Cookie} is present in the
        dict, its value is added to the values from the factory's C{cookies}
        attribute.
        """
        factory = client.HTTPClientFactory(
            b'http://foo/bar',
            agent=b"foobar",
            cookies={b'baz': b'quux'},
            postdata=b"some data",
            headers={
                b'Host': b'example.net',
                b'User-Agent': b'fooble',
                b'Cookie': b'blah blah',
                b'Content-Length': b'12981',
                b'Useful': b'value'})
        transport = StringTransport()
        protocol = client.HTTPPageGetter()
        protocol.factory = factory
        protocol.makeConnection(transport)
        result = transport.value()
        for expectedHeader in [
            b"Host: example.net\r\n",
            b"User-Agent: foobar\r\n",
            b"Content-Length: 9\r\n",
            b"Useful: value\r\n",
            b"connection: close\r\n",
            b"Cookie: blah blah; baz=quux\r\n"]:
            self.assertIn(expectedHeader, result)



class WebClientTests(unittest.TestCase):
    def _listen(self, site):
        return reactor.listenTCP(0, site, interface="127.0.0.1")

    def setUp(self):
        self.agent = None # for twisted.web.client.Agent test
        self.cleanupServerConnections = 0
        r = resource.Resource()
        r.putChild(b"file", Data(b"0123456789", "text/html"))
        r.putChild(b"redirect", Redirect(b"/file"))
        self.infiniteRedirectResource = CountingRedirect(b"/infiniteRedirect")
        r.putChild(b"infiniteRedirect", self.infiniteRedirectResource)
        r.putChild(b"wait", ForeverTakingResource())
        r.putChild(b"write-then-wait", ForeverTakingResource(write=True))
        r.putChild(b"never-read", ForeverTakingNoReadingResource())
        r.putChild(b"error", ErrorResource())
        r.putChild(b"nolength", NoLengthResource())
        r.putChild(b"host", HostHeaderResource())
        r.putChild(b"payload", PayloadResource())
        r.putChild(b"broken", BrokenDownloadResource())
        r.putChild(b"cookiemirror", CookieMirrorResource())
        r.putChild(b'delay1', DelayResource(1))
        r.putChild(b'delay2', DelayResource(2))

        self.afterFoundGetCounter = CountingResource()
        r.putChild(b"afterFoundGetCounter", self.afterFoundGetCounter)
        r.putChild(b"afterFoundGetRedirect", Redirect(b"/afterFoundGetCounter"))

        miscasedHead = Data(b"miscased-head GET response content", "major/minor")
        miscasedHead.render_Head = lambda request: b"miscased-head content"
        r.putChild(b"miscased-head", miscasedHead)

        self.extendedRedirect = ExtendedRedirect(b'/extendedRedirect')
        r.putChild(b"extendedRedirect", self.extendedRedirect)
        self.site = server.Site(r, timeout=None)
        self.wrapper = WrappingFactory(self.site)
        self.port = self._listen(self.wrapper)
        self.portno = self.port.getHost().port

    def tearDown(self):
        if self.agent:
            # clean up connections for twisted.web.client.Agent test.
            self.agent.closeCachedConnections()
            self.agent = None

        # If the test indicated it might leave some server-side connections
        # around, clean them up.
        connections = list(self.wrapper.protocols.keys())
        # If there are fewer server-side connections than requested,
        # that's okay.  Some might have noticed that the client closed
        # the connection and cleaned up after themselves.
        for n in range(min(len(connections), self.cleanupServerConnections)):
            proto = connections.pop()
            msg("Closing %r" % (proto,))
            proto.transport.loseConnection()
        if connections:
            msg("Some left-over connections; this test is probably buggy.")
        return self.port.stopListening()

    def getURL(self, path):
        host = "http://127.0.0.1:%d/" % self.portno
        return networkString(urljoin(host, nativeString(path)))

    def testPayload(self):
        s = b"0123456789" * 10
        return client.getPage(self.getURL("payload"), postdata=s
                              ).addCallback(self.assertEqual, s
            )


    def test_getPageBrokenDownload(self):
        """
        If the connection is closed before the number of bytes indicated by
        I{Content-Length} have been received, the L{Deferred} returned by
        L{getPage} fails with L{PartialDownloadError}.
        """
        d = client.getPage(self.getURL("broken"))
        d = self.assertFailure(d, client.PartialDownloadError)
        d.addCallback(lambda exc: self.assertEqual(exc.response, b"abc"))
        return d


    def test_downloadPageBrokenDownload(self):
        """
        If the connection is closed before the number of bytes indicated by
        I{Content-Length} have been received, the L{Deferred} returned by
        L{downloadPage} fails with L{PartialDownloadError}.
        """
        # test what happens when download gets disconnected in the middle
        path = FilePath(self.mktemp())
        d = client.downloadPage(self.getURL("broken"), path.path)
        d = self.assertFailure(d, client.PartialDownloadError)

        def checkResponse(response):
            """
            The HTTP status code from the server is propagated through the
            C{PartialDownloadError}.
            """
            self.assertEqual(response.status, b"200")
            self.assertEqual(response.message, b"OK")
            return response
        d.addCallback(checkResponse)

        def cbFailed(ignored):
            self.assertEqual(path.getContent(), b"abc")
        d.addCallback(cbFailed)
        return d

    def test_downloadPageLogsFileCloseError(self):
        """
        If there is an exception closing the file being written to after the
        connection is prematurely closed, that exception is logged.
        """
        class BrokenFile:
            def write(self, bytes):
                pass

            def close(self):
                raise IOError(ENOSPC, "No file left on device")

        d = client.downloadPage(self.getURL("broken"), BrokenFile())
        d = self.assertFailure(d, client.PartialDownloadError)
        def cbFailed(ignored):
            self.assertEqual(len(self.flushLoggedErrors(IOError)), 1)
        d.addCallback(cbFailed)
        return d


    def testHostHeader(self):
        # if we pass Host header explicitly, it should be used, otherwise
        # it should extract from url
        return defer.gatherResults([
            client.getPage(self.getURL("host")).addCallback(
                    self.assertEqual, b"127.0.0.1:" + intToBytes(self.portno)),
            client.getPage(self.getURL("host"),
                           headers={b"Host": b"www.example.com"}).addCallback(
                    self.assertEqual, b"www.example.com")])


    def test_getPage(self):
        """
        L{client.getPage} returns a L{Deferred} which is called back with
        the body of the response if the default method B{GET} is used.
        """
        d = client.getPage(self.getURL("file"))
        d.addCallback(self.assertEqual, b"0123456789")
        return d


    def test_getPageHEAD(self):
        """
        L{client.getPage} returns a L{Deferred} which is called back with
        the empty string if the method is I{HEAD} and there is a successful
        response code.
        """
        d = client.getPage(self.getURL("file"), method=b"HEAD")
        d.addCallback(self.assertEqual, b"")
        return d


    def test_getPageNotQuiteHEAD(self):
        """
        If the request method is a different casing of I{HEAD} (ie, not all
        capitalized) then it is not a I{HEAD} request and the response body
        is returned.
        """
        d = client.getPage(self.getURL("miscased-head"), method=b'Head')
        d.addCallback(self.assertEqual, b"miscased-head content")
        return d


    def test_timeoutNotTriggering(self):
        """
        When a non-zero timeout is passed to L{getPage} and the page is
        retrieved before the timeout period elapses, the L{Deferred} is
        called back with the contents of the page.
        """
        d = client.getPage(self.getURL("host"), timeout=100)
        d.addCallback(self.assertEqual,
                      networkString("127.0.0.1:%s" % (self.portno,)))
        return d


    def test_timeoutTriggering(self):
        """
        When a non-zero timeout is passed to L{getPage} and that many
        seconds elapse before the server responds to the request. the
        L{Deferred} is errbacked with a L{error.TimeoutError}.
        """
        # This will probably leave some connections around.
        self.cleanupServerConnections = 1
        return self.assertFailure(
            client.getPage(self.getURL("wait"), timeout=0.000001),
            defer.TimeoutError)


    def testDownloadPage(self):
        downloads = []
        downloadData = [("file", self.mktemp(), b"0123456789"),
                        ("nolength", self.mktemp(), b"nolength")]

        for (url, name, data) in downloadData:
            d = client.downloadPage(self.getURL(url), name)
            d.addCallback(self._cbDownloadPageTest, data, name)
            downloads.append(d)
        return defer.gatherResults(downloads)

    def _cbDownloadPageTest(self, ignored, data, name):
        with open(name, "rb") as f:
            bytes = f.read()
        self.assertEqual(bytes, data)

    def testDownloadPageError1(self):
        class errorfile:
            def write(self, data):
                raise IOError("badness happened during write")
            def close(self):
                pass
        ef = errorfile()
        return self.assertFailure(
            client.downloadPage(self.getURL("file"), ef),
            IOError)

    def testDownloadPageError2(self):
        class errorfile:
            def write(self, data):
                pass
            def close(self):
                raise IOError("badness happened during close")
        ef = errorfile()
        return self.assertFailure(
            client.downloadPage(self.getURL("file"), ef),
            IOError)

    def testDownloadPageError3(self):
        # make sure failures in open() are caught too. This is tricky.
        # Might only work on posix.
        open("unwritable", "wb").close()
        os.chmod("unwritable", 0) # make it unwritable (to us)
        d = self.assertFailure(
            client.downloadPage(self.getURL("file"), "unwritable"),
            IOError)
        d.addBoth(self._cleanupDownloadPageError3)
        return d

    def _cleanupDownloadPageError3(self, ignored):
        os.chmod("unwritable", 0o700)
        os.unlink("unwritable")
        return ignored

    def _downloadTest(self, method):
        dl = []
        for (url, code) in [("nosuchfile", b"404"), ("error", b"401"),
                            ("error?showlength=1", b"401")]:
            d = method(url)
            d = self.assertFailure(d, error.Error)
            d.addCallback(lambda exc, code=code: self.assertEqual(exc.args[0], code))
            dl.append(d)
        return defer.DeferredList(dl, fireOnOneErrback=True)

    def testServerError(self):
        return self._downloadTest(lambda url: client.getPage(self.getURL(url)))

    def testDownloadServerError(self):
        return self._downloadTest(lambda url: client.downloadPage(self.getURL(url), url.split('?')[0]))

    def testFactoryInfo(self):
        url = self.getURL('file')
        uri = client.URI.fromBytes(url)
        factory = client.HTTPClientFactory(url)
        reactor.connectTCP(nativeString(uri.host), uri.port, factory)
        return factory.deferred.addCallback(self._cbFactoryInfo, factory)

    def _cbFactoryInfo(self, ignoredResult, factory):
        self.assertEqual(factory.status, b'200')
        self.assertTrue(factory.version.startswith(b'HTTP/'))
        self.assertEqual(factory.message, b'OK')
        self.assertEqual(factory.response_headers[b'content-length'][0], b'10')


    def test_followRedirect(self):
        """
        By default, L{client.getPage} follows redirects and returns the content
        of the target resource.
        """
        d = client.getPage(self.getURL("redirect"))
        d.addCallback(self.assertEqual, b"0123456789")
        return d


    def test_noFollowRedirect(self):
        """
        If C{followRedirect} is passed a false value, L{client.getPage} does not
        follow redirects and returns a L{Deferred} which fails with
        L{error.PageRedirect} when it encounters one.
        """
        d = self.assertFailure(
            client.getPage(self.getURL("redirect"), followRedirect=False),
            error.PageRedirect)
        d.addCallback(self._cbCheckLocation)
        return d


    def _cbCheckLocation(self, exc):
        self.assertEqual(exc.location, b"/file")


    def test_infiniteRedirection(self):
        """
        When more than C{redirectLimit} HTTP redirects are encountered, the
        page request fails with L{InfiniteRedirection}.
        """
        def checkRedirectCount(*a):
            self.assertEqual(f._redirectCount, 13)
            self.assertEqual(self.infiniteRedirectResource.count, 13)

        f = client._makeGetterFactory(
            self.getURL('infiniteRedirect'),
            client.HTTPClientFactory,
            redirectLimit=13)
        d = self.assertFailure(f.deferred, error.InfiniteRedirection)
        d.addCallback(checkRedirectCount)
        return d


    def test_isolatedFollowRedirect(self):
        """
        C{client.HTTPPagerGetter} instances each obey the C{followRedirect}
        value passed to the L{client.getPage} call which created them.
        """
        d1 = client.getPage(self.getURL('redirect'), followRedirect=True)
        d2 = client.getPage(self.getURL('redirect'), followRedirect=False)

        d = self.assertFailure(d2, error.PageRedirect
            ).addCallback(lambda dummy: d1)
        return d


    def test_afterFoundGet(self):
        """
        Enabling unsafe redirection behaviour overwrites the method of
        redirected C{POST} requests with C{GET}.
        """
        url = self.getURL('extendedRedirect?code=302')
        f = client.HTTPClientFactory(url, followRedirect=True, method=b"POST")
        self.assertFalse(
            f.afterFoundGet,
            "By default, afterFoundGet must be disabled")

        def gotPage(page):
            self.assertEqual(
                self.extendedRedirect.lastMethod,
                b"GET",
                "With afterFoundGet, the HTTP method must change to GET")

        d = client.getPage(
            url, followRedirect=True, afterFoundGet=True, method=b"POST")
        d.addCallback(gotPage)
        return d


    def test_downloadAfterFoundGet(self):
        """
        Passing C{True} for C{afterFoundGet} to L{client.downloadPage} invokes
        the same kind of redirect handling as passing that argument to
        L{client.getPage} invokes.
        """
        url = self.getURL('extendedRedirect?code=302')

        def gotPage(page):
            self.assertEqual(
                self.extendedRedirect.lastMethod,
                b"GET",
                "With afterFoundGet, the HTTP method must change to GET")

        d = client.downloadPage(url, "downloadTemp",
            followRedirect=True, afterFoundGet=True, method=b"POST")
        d.addCallback(gotPage)
        return d


    def test_afterFoundGetMakesOneRequest(self):
        """
        When C{afterFoundGet} is C{True}, L{client.getPage} only issues one
        request to the server when following the redirect.  This is a regression
        test, see #4760.
        """
        def checkRedirectCount(*a):
            self.assertEqual(self.afterFoundGetCounter.count, 1)

        url = self.getURL('afterFoundGetRedirect')
        d = client.getPage(
            url, followRedirect=True, afterFoundGet=True, method=b"POST")
        d.addCallback(checkRedirectCount)
        return d


    def test_downloadTimeout(self):
        """
        If the timeout indicated by the C{timeout} parameter to
        L{client.HTTPDownloader.__init__} elapses without the complete response
        being received, the L{defer.Deferred} returned by
        L{client.downloadPage} fires with a L{Failure} wrapping a
        L{defer.TimeoutError}.
        """
        self.cleanupServerConnections = 2
        # Verify the behavior if no bytes are ever written.
        first = client.downloadPage(
            self.getURL("wait"),
            self.mktemp(), timeout=0.01)

        # Verify the behavior if some bytes are written but then the request
        # never completes.
        second = client.downloadPage(
            self.getURL("write-then-wait"),
            self.mktemp(), timeout=0.01)

        return defer.gatherResults([
            self.assertFailure(first, defer.TimeoutError),
            self.assertFailure(second, defer.TimeoutError)])


    def test_downloadTimeoutsWorkWithoutReading(self):
        """
        If the timeout indicated by the C{timeout} parameter to
        L{client.HTTPDownloader.__init__} elapses without the complete response
        being received, the L{defer.Deferred} returned by
        L{client.downloadPage} fires with a L{Failure} wrapping a
        L{defer.TimeoutError}, even if the remote peer isn't reading data from
        the socket.
        """
        self.cleanupServerConnections = 1

        # The timeout here needs to be slightly longer to give the resource a
        # change to stop the reading.
        d = client.downloadPage(
            self.getURL("never-read"),
            self.mktemp(), timeout=0.05)
        return self.assertFailure(d, defer.TimeoutError)


    def test_downloadHeaders(self):
        """
        After L{client.HTTPDownloader.deferred} fires, the
        L{client.HTTPDownloader} instance's C{status} and C{response_headers}
        attributes are populated with the values from the response.
        """
        def checkHeaders(factory):
            self.assertEqual(factory.status, b'200')
            self.assertEqual(factory.response_headers[b'content-type'][0], b'text/html')
            self.assertEqual(factory.response_headers[b'content-length'][0], b'10')
            os.unlink(factory.fileName)
        factory = client._makeGetterFactory(
            self.getURL('file'),
            client.HTTPDownloader,
            fileOrName=self.mktemp())
        return factory.deferred.addCallback(lambda _: checkHeaders(factory))


    def test_downloadCookies(self):
        """
        The C{cookies} dict passed to the L{client.HTTPDownloader}
        initializer is used to populate the I{Cookie} header included in the
        request sent to the server.
        """
        output = self.mktemp()
        factory = client._makeGetterFactory(
            self.getURL('cookiemirror'),
            client.HTTPDownloader,
            fileOrName=output,
            cookies={b'foo': b'bar'})
        def cbFinished(ignored):
            self.assertEqual(
                FilePath(output).getContent(),
                b"[('foo', 'bar')]")
        factory.deferred.addCallback(cbFinished)
        return factory.deferred


    def test_downloadRedirectLimit(self):
        """
        When more than C{redirectLimit} HTTP redirects are encountered, the
        page request fails with L{InfiniteRedirection}.
        """
        def checkRedirectCount(*a):
            self.assertEqual(f._redirectCount, 7)
            self.assertEqual(self.infiniteRedirectResource.count, 7)

        f = client._makeGetterFactory(
            self.getURL('infiniteRedirect'),
            client.HTTPDownloader,
            fileOrName=self.mktemp(),
            redirectLimit=7)
        d = self.assertFailure(f.deferred, error.InfiniteRedirection)
        d.addCallback(checkRedirectCount)
        return d


    def test_setURL(self):
        """
        L{client.HTTPClientFactory.setURL} alters the scheme, host, port and
        path for absolute URLs.
        """
        url = b'http://example.com'
        f = client.HTTPClientFactory(url)
        self.assertEqual(
            (url, b'http', b'example.com', 80, b'/'),
            (f.url, f.scheme, f.host, f.port, f.path))


    def test_setURLRemovesFragment(self):
        """
        L{client.HTTPClientFactory.setURL} removes the fragment identifier from
        the path component.
        """
        f = client.HTTPClientFactory(b'http://example.com')
        url = b'https://foo.com:8443/bar;123?a#frag'
        f.setURL(url)
        self.assertEqual(
            (url, b'https', b'foo.com', 8443, b'/bar;123?a'),
            (f.url, f.scheme, f.host, f.port, f.path))


    def test_setURLRelativePath(self):
        """
        L{client.HTTPClientFactory.setURL} alters the path in a relative URL.
        """
        f = client.HTTPClientFactory(b'http://example.com')
        url = b'/hello'
        f.setURL(url)
        self.assertEqual(
            (url, b'http', b'example.com', 80, b'/hello'),
            (f.url, f.scheme, f.host, f.port, f.path))



class WebClientSSLTests(WebClientTests):
    def _listen(self, site):
        return reactor.listenSSL(
            0, site,
            contextFactory=ssl.DefaultOpenSSLContextFactory(
                serverPEMPath, serverPEMPath),
            interface="127.0.0.1")

    def getURL(self, path):
        return networkString("https://127.0.0.1:%d/%s" % (self.portno, path))

    def testFactoryInfo(self):
        url = self.getURL('file')
        uri = client.URI.fromBytes(url)
        factory = client.HTTPClientFactory(url)
        reactor.connectSSL(nativeString(uri.host), uri.port, factory,
                           ssl.ClientContextFactory())
        # The base class defines _cbFactoryInfo correctly for this
        return factory.deferred.addCallback(self._cbFactoryInfo, factory)



class WebClientRedirectBetweenSSLandPlainTextTests(unittest.TestCase):
    def getHTTPS(self, path):
        return networkString("https://127.0.0.1:%d/%s" % (self.tlsPortno, path))

    def getHTTP(self, path):
        return networkString("http://127.0.0.1:%d/%s" % (self.plainPortno, path))

    def setUp(self):
        plainRoot = Data(b'not me', 'text/plain')
        tlsRoot = Data(b'me neither', 'text/plain')

        plainSite = server.Site(plainRoot, timeout=None)
        tlsSite = server.Site(tlsRoot, timeout=None)

        self.tlsPort = reactor.listenSSL(
            0, tlsSite,
            contextFactory=ssl.DefaultOpenSSLContextFactory(
                serverPEMPath, serverPEMPath),
            interface="127.0.0.1")
        self.plainPort = reactor.listenTCP(0, plainSite, interface="127.0.0.1")

        self.plainPortno = self.plainPort.getHost().port
        self.tlsPortno = self.tlsPort.getHost().port

        plainRoot.putChild(b'one', Redirect(self.getHTTPS('two')))
        tlsRoot.putChild(b'two', Redirect(self.getHTTP('three')))
        plainRoot.putChild(b'three', Redirect(self.getHTTPS('four')))
        tlsRoot.putChild(b'four', Data(b'FOUND IT!', 'text/plain'))

    def tearDown(self):
        ds = list(
            map(defer.maybeDeferred,
                [self.plainPort.stopListening, self.tlsPort.stopListening]))
        return defer.gatherResults(ds)

    def testHoppingAround(self):
        return client.getPage(self.getHTTP("one")
            ).addCallback(self.assertEqual, b"FOUND IT!"
            )


class CookieTests(unittest.TestCase):
    def _listen(self, site):
        return reactor.listenTCP(0, site, interface="127.0.0.1")

    def setUp(self):
        root = Data(b'El toro!', 'text/plain')
        root.putChild(b"cookiemirror", CookieMirrorResource())
        root.putChild(b"rawcookiemirror", RawCookieMirrorResource())
        site = server.Site(root, timeout=None)
        self.port = self._listen(site)
        self.portno = self.port.getHost().port

    def tearDown(self):
        return self.port.stopListening()

    def getHTTP(self, path):
        return networkString("http://127.0.0.1:%d/%s" % (self.portno, path))

    def testNoCookies(self):
        return client.getPage(self.getHTTP("cookiemirror")
            ).addCallback(self.assertEqual, b"[]"
            )

    def testSomeCookies(self):
        cookies = {b'foo': b'bar', b'baz': b'quux'}
        return client.getPage(self.getHTTP("cookiemirror"), cookies=cookies
            ).addCallback(self.assertEqual, b"[('baz', 'quux'), ('foo', 'bar')]"
            )

    def testRawNoCookies(self):
        return client.getPage(self.getHTTP("rawcookiemirror")
            ).addCallback(self.assertEqual, b"None"
            )

    def testRawSomeCookies(self):
        cookies = {b'foo': b'bar', b'baz': b'quux'}
        return client.getPage(self.getHTTP("rawcookiemirror"), cookies=cookies
            ).addCallback(self.assertIn,
                          (b"'foo=bar; baz=quux'", b"'baz=quux; foo=bar'")
            )

    def testCookieHeaderParsing(self):
        factory = client.HTTPClientFactory(b'http://foo.example.com/')
        proto = factory.buildProtocol('127.42.42.42')
        transport = StringTransport()
        proto.makeConnection(transport)
        for line in [
            b'200 Ok',
            b'Squash: yes',
            b'Hands: stolen',
            b'Set-Cookie: CUSTOMER=WILE_E_COYOTE; path=/; expires=Wednesday, 09-Nov-99 23:12:40 GMT',
            b'Set-Cookie: PART_NUMBER=ROCKET_LAUNCHER_0001; path=/',
            b'Set-Cookie: SHIPPING=FEDEX; path=/foo',
            b'',
            b'body',
            b'more body',
            ]:
            proto.dataReceived(line + b'\r\n')
        self.assertEqual(transport.value(),
                         b'GET / HTTP/1.0\r\n'
                         b'Host: foo.example.com\r\n'
                         b'User-Agent: Twisted PageGetter\r\n'
                         b'\r\n')
        self.assertEqual(factory.cookies,
                          {
            b'CUSTOMER': b'WILE_E_COYOTE',
            b'PART_NUMBER': b'ROCKET_LAUNCHER_0001',
            b'SHIPPING': b'FEDEX',
            })



class HostHeaderTests(unittest.TestCase):
    """
    Test that L{HTTPClientFactory} includes the port in the host header
    if needed.
    """

    def _getHost(self, bytes):
        """
        Retrieve the value of the I{Host} header from the serialized
        request given by C{bytes}.
        """
        for line in bytes.split(b'\r\n'):
            try:
                name, value = line.split(b':', 1)
                if name.strip().lower() == b'host':
                    return value.strip()
            except ValueError:
                pass


    def test_HTTPDefaultPort(self):
        """
        No port should be included in the host header when connecting to the
        default HTTP port.
        """
        factory = client.HTTPClientFactory(b'http://foo.example.com/')
        proto = factory.buildProtocol(b'127.42.42.42')
        proto.makeConnection(StringTransport())
        self.assertEqual(self._getHost(proto.transport.value()),
                          b'foo.example.com')


    def test_HTTPPort80(self):
        """
        No port should be included in the host header when connecting to the
        default HTTP port even if it is in the URL.
        """
        factory = client.HTTPClientFactory(b'http://foo.example.com:80/')
        proto = factory.buildProtocol('127.42.42.42')
        proto.makeConnection(StringTransport())
        self.assertEqual(self._getHost(proto.transport.value()),
                          b'foo.example.com')


    def test_HTTPNotPort80(self):
        """
        The port should be included in the host header when connecting to the
        a non default HTTP port.
        """
        factory = client.HTTPClientFactory(b'http://foo.example.com:8080/')
        proto = factory.buildProtocol('127.42.42.42')
        proto.makeConnection(StringTransport())
        self.assertEqual(self._getHost(proto.transport.value()),
                          b'foo.example.com:8080')


    def test_HTTPSDefaultPort(self):
        """
        No port should be included in the host header when connecting to the
        default HTTPS port.
        """
        factory = client.HTTPClientFactory(b'https://foo.example.com/')
        proto = factory.buildProtocol('127.42.42.42')
        proto.makeConnection(StringTransport())
        self.assertEqual(self._getHost(proto.transport.value()),
                          b'foo.example.com')


    def test_HTTPSPort443(self):
        """
        No port should be included in the host header when connecting to the
        default HTTPS port even if it is in the URL.
        """
        factory = client.HTTPClientFactory(b'https://foo.example.com:443/')
        proto = factory.buildProtocol('127.42.42.42')
        proto.makeConnection(StringTransport())
        self.assertEqual(self._getHost(proto.transport.value()),
                          b'foo.example.com')


    def test_HTTPSNotPort443(self):
        """
        The port should be included in the host header when connecting to the
        a non default HTTPS port.
        """
        factory = client.HTTPClientFactory(b'http://foo.example.com:8080/')
        proto = factory.buildProtocol('127.42.42.42')
        proto.makeConnection(StringTransport())
        self.assertEqual(self._getHost(proto.transport.value()),
                          b'foo.example.com:8080')


if ssl is None or not hasattr(ssl, 'DefaultOpenSSLContextFactory'):
    for case in [WebClientSSLTests, WebClientRedirectBetweenSSLandPlainTextTests]:
        case.skip = "OpenSSL not present"

if not interfaces.IReactorSSL(reactor, None):
    for case in [WebClientSSLTests, WebClientRedirectBetweenSSLandPlainTextTests]:
        case.skip = "Reactor doesn't support SSL"



class URITests:
    """
    Abstract tests for L{twisted.web.client.URI}.

    Subclass this and L{unittest.TestCase}. Then provide a value for
    C{host} and C{uriHost}.

    @ivar host: A host specification for use in tests, must be L{bytes}.

    @ivar uriHost: The host specification in URI form, must be a L{bytes}. In
        most cases this is identical with C{host}. IPv6 address literals are an
        exception, according to RFC 3986 section 3.2.2, as they need to be
        enclosed in brackets. In this case this variable is different.
    """

    def makeURIString(self, template):
        """
        Replace the string "HOST" in C{template} with this test's host.

        Byte strings Python between (and including) versions 3.0 and 3.4
        cannot be formatted using C{%} or C{format} so this does a simple
        replace.

        @type template: L{bytes}
        @param template: A string containing "HOST".

        @rtype: L{bytes}
        @return: A string where "HOST" has been replaced by C{self.host}.
        """
        self.assertIsInstance(self.host, bytes)
        self.assertIsInstance(self.uriHost, bytes)
        self.assertIsInstance(template, bytes)
        self.assertIn(b"HOST", template)
        return template.replace(b"HOST", self.uriHost)

    def assertURIEquals(self, uri, scheme, netloc, host, port, path,
                        params=b'', query=b'', fragment=b''):
        """
        Assert that all of a L{client.URI}'s components match the expected
        values.

        @param uri: U{client.URI} instance whose attributes will be checked
            for equality.

        @type scheme: L{bytes}
        @param scheme: URI scheme specifier.

        @type netloc: L{bytes}
        @param netloc: Network location component.

        @type host: L{bytes}
        @param host: Host name.

        @type port: L{int}
        @param port: Port number.

        @type path: L{bytes}
        @param path: Hierarchical path.

        @type params: L{bytes}
        @param params: Parameters for last path segment, defaults to C{b''}.

        @type query: L{bytes}
        @param query: Query string, defaults to C{b''}.

        @type fragment: L{bytes}
        @param fragment: Fragment identifier, defaults to C{b''}.
        """
        self.assertEqual(
            (scheme, netloc, host, port, path, params, query, fragment),
            (uri.scheme, uri.netloc, uri.host, uri.port, uri.path, uri.params,
             uri.query, uri.fragment))


    def test_parseDefaultPort(self):
        """
        L{client.URI.fromBytes} by default assumes port 80 for the I{http}
        scheme and 443 for the I{https} scheme.
        """
        uri = client.URI.fromBytes(self.makeURIString(b'http://HOST'))
        self.assertEqual(80, uri.port)
        # Weird (but commonly accepted) structure uses default port.
        uri = client.URI.fromBytes(self.makeURIString(b'http://HOST:'))
        self.assertEqual(80, uri.port)
        uri = client.URI.fromBytes(self.makeURIString(b'https://HOST'))
        self.assertEqual(443, uri.port)


    def test_parseCustomDefaultPort(self):
        """
        L{client.URI.fromBytes} accepts a C{defaultPort} parameter that
        overrides the normal default port logic.
        """
        uri = client.URI.fromBytes(
            self.makeURIString(b'http://HOST'), defaultPort=5144)
        self.assertEqual(5144, uri.port)
        uri = client.URI.fromBytes(
            self.makeURIString(b'https://HOST'), defaultPort=5144)
        self.assertEqual(5144, uri.port)


    def test_netlocHostPort(self):
        """
        Parsing a I{URI} splits the network location component into I{host} and
        I{port}.
        """
        uri = client.URI.fromBytes(
            self.makeURIString(b'http://HOST:5144'))
        self.assertEqual(5144, uri.port)
        self.assertEqual(self.host, uri.host)
        self.assertEqual(self.uriHost + b':5144', uri.netloc)

        # Spaces in the hostname are trimmed, the default path is /.
        uri = client.URI.fromBytes(self.makeURIString(b'http://HOST '))
        self.assertEqual(self.uriHost, uri.netloc)


    def test_path(self):
        """
        Parse the path from a I{URI}.
        """
        uri = self.makeURIString(b'http://HOST/foo/bar')
        parsed = client.URI.fromBytes(uri)
        self.assertURIEquals(
            parsed,
            scheme=b'http',
            netloc=self.uriHost,
            host=self.host,
            port=80,
            path=b'/foo/bar')
        self.assertEqual(uri, parsed.toBytes())


    def test_noPath(self):
        """
        The path of a I{URI} that has no path is the empty string.
        """
        uri = self.makeURIString(b'http://HOST')
        parsed = client.URI.fromBytes(uri)
        self.assertURIEquals(
            parsed,
            scheme=b'http',
            netloc=self.uriHost,
            host=self.host,
            port=80,
            path=b'')
        self.assertEqual(uri, parsed.toBytes())


    def test_emptyPath(self):
        """
        The path of a I{URI} with an empty path is C{b'/'}.
        """
        uri = self.makeURIString(b'http://HOST/')
        self.assertURIEquals(
            client.URI.fromBytes(uri),
            scheme=b'http',
            netloc=self.uriHost,
            host=self.host,
            port=80,
            path=b'/')


    def test_param(self):
        """
        Parse I{URI} parameters from a I{URI}.
        """
        uri = self.makeURIString(b'http://HOST/foo/bar;param')
        parsed = client.URI.fromBytes(uri)
        self.assertURIEquals(
            parsed,
            scheme=b'http',
            netloc=self.uriHost,
            host=self.host,
            port=80,
            path=b'/foo/bar',
            params=b'param')
        self.assertEqual(uri, parsed.toBytes())


    def test_query(self):
        """
        Parse the query string from a I{URI}.
        """
        uri = self.makeURIString(b'http://HOST/foo/bar;param?a=1&b=2')
        parsed = client.URI.fromBytes(uri)
        self.assertURIEquals(
            parsed,
            scheme=b'http',
            netloc=self.uriHost,
            host=self.host,
            port=80,
            path=b'/foo/bar',
            params=b'param',
            query=b'a=1&b=2')
        self.assertEqual(uri, parsed.toBytes())


    def test_fragment(self):
        """
        Parse the fragment identifier from a I{URI}.
        """
        uri = self.makeURIString(b'http://HOST/foo/bar;param?a=1&b=2#frag')
        parsed = client.URI.fromBytes(uri)
        self.assertURIEquals(
            parsed,
            scheme=b'http',
            netloc=self.uriHost,
            host=self.host,
            port=80,
            path=b'/foo/bar',
            params=b'param',
            query=b'a=1&b=2',
            fragment=b'frag')
        self.assertEqual(uri, parsed.toBytes())


    def test_originForm(self):
        """
        L{client.URI.originForm} produces an absolute I{URI} path including
        the I{URI} path.
        """
        uri = client.URI.fromBytes(
            self.makeURIString(b'http://HOST/foo'))
        self.assertEqual(b'/foo', uri.originForm)


    def test_originFormComplex(self):
        """
        L{client.URI.originForm} produces an absolute I{URI} path including
        the I{URI} path, parameters and query string but excludes the fragment
        identifier.
        """
        uri = client.URI.fromBytes(
            self.makeURIString(b'http://HOST/foo;param?a=1#frag'))
        self.assertEqual(b'/foo;param?a=1', uri.originForm)


    def test_originFormNoPath(self):
        """
        L{client.URI.originForm} produces a path of C{b'/'} when the I{URI}
        specifies no path.
        """
        uri = client.URI.fromBytes(self.makeURIString(b'http://HOST'))
        self.assertEqual(b'/', uri.originForm)


    def test_originFormEmptyPath(self):
        """
        L{client.URI.originForm} produces a path of C{b'/'} when the I{URI}
        specifies an empty path.
        """
        uri = client.URI.fromBytes(
            self.makeURIString(b'http://HOST/'))
        self.assertEqual(b'/', uri.originForm)


    def test_externalUnicodeInterference(self):
        """
        L{client.URI.fromBytes} parses the scheme, host, and path elements
        into L{bytes}, even when passed an URL which has previously been passed
        to L{urlparse} as a L{unicode} string.
        """
        goodInput = self.makeURIString(b'http://HOST/path')
        badInput = goodInput.decode('ascii')
        urlparse(badInput)
        uri = client.URI.fromBytes(goodInput)
        self.assertIsInstance(uri.scheme, bytes)
        self.assertIsInstance(uri.host, bytes)
        self.assertIsInstance(uri.path, bytes)



class URITestsForHostname(URITests, unittest.TestCase):
    """
    Tests for L{twisted.web.client.URI} with host names.
    """

    uriHost = host = b"example.com"



class URITestsForIPv4(URITests, unittest.TestCase):
    """
    Tests for L{twisted.web.client.URI} with IPv4 host addresses.
    """

    uriHost = host = b"192.168.1.67"



class URITestsForIPv6(URITests, unittest.TestCase):
    """
    Tests for L{twisted.web.client.URI} with IPv6 host addresses.

    IPv6 addresses must always be surrounded by square braces in URIs. No
    attempt is made to test without.
    """

    host = b"fe80::20c:29ff:fea4:c60"
    uriHost = b"[fe80::20c:29ff:fea4:c60]"


    def test_hostBracketIPv6AddressLiteral(self):
        """
        Brackets around IPv6 addresses are stripped in the host field. The host
        field is then exported with brackets in the output of
        L{client.URI.toBytes}.
        """
        uri = client.URI.fromBytes(b"http://[::1]:80/index.html")

        self.assertEqual(uri.host, b"::1")
        self.assertEqual(uri.netloc, b"[::1]:80")
        self.assertEqual(uri.toBytes(), b'http://[::1]:80/index.html')
