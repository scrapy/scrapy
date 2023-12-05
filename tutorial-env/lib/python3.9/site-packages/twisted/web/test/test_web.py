# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for various parts of L{twisted.web}.
"""

import os
import zlib
from io import BytesIO

from zope.interface import implementer
from zope.interface.verify import verifyObject

from twisted.internet import interfaces
from twisted.internet.address import IPv4Address, IPv6Address
from twisted.internet.task import Clock
from twisted.logger import LogLevel, globalLogPublisher
from twisted.python import failure, reflect
from twisted.python.filepath import FilePath
from twisted.test.proto_helpers import EventLoggingObserver
from twisted.trial import unittest
from twisted.web import error, http, iweb, resource, server
from twisted.web.static import Data
from twisted.web.test.requesthelper import DummyChannel, DummyRequest
from ._util import assertIsFilesystemTemporary


class ResourceTests(unittest.TestCase):
    def testListEntities(self):
        r = resource.Resource()
        self.assertEqual([], r.listEntities())


class SimpleResource(resource.Resource):
    """
    @ivar _contentType: L{None} or a C{str} giving the value of the
        I{Content-Type} header in the response this resource will render.  If it
        is L{None}, no I{Content-Type} header will be set in the response.
    """

    def __init__(self, contentType=None):
        resource.Resource.__init__(self)
        self._contentType = contentType

    def render(self, request):
        if self._contentType is not None:
            request.responseHeaders.setRawHeaders(b"content-type", [self._contentType])

        if http.CACHED in (
            request.setLastModified(10),
            request.setETag(b"MatchingTag"),
        ):
            return b""
        else:
            return b"correct"


class ZeroLengthResource(resource.Resource):
    """
    A resource that always returns a zero-length response.
    """

    def render(self, request):
        return b""


class NoContentResource(resource.Resource):
    """
    A resource that always returns a 204 No Content response without setting
    Content-Length.
    """

    def render(self, request):
        request.setResponseCode(http.NO_CONTENT)
        return b""


class SiteTest(unittest.TestCase):
    """
    Unit tests for L{server.Site}.
    """

    def getAutoExpiringSession(self, site):
        """
        Create a new session which auto expires at cleanup.

        @param site: The site on which the session is created.
        @type site: L{server.Site}

        @return: A newly created session.
        @rtype: L{server.Session}
        """
        session = site.makeSession()
        # Clean delayed calls from session expiration.
        self.addCleanup(session.expire)
        return session

    def test_simplestSite(self):
        """
        L{Site.getResourceFor} returns the C{b""} child of the root resource it
        is constructed with when processing a request for I{/}.
        """
        sres1 = SimpleResource()
        sres2 = SimpleResource()
        sres1.putChild(b"", sres2)
        site = server.Site(sres1)
        self.assertIdentical(
            site.getResourceFor(DummyRequest([b""])), sres2, "Got the wrong resource."
        )

    def test_defaultRequestFactory(self):
        """
        L{server.Request} is the default request factory.
        """
        site = server.Site(resource=SimpleResource())

        self.assertIs(server.Request, site.requestFactory)

    def test_constructorRequestFactory(self):
        """
        Can be initialized with a custom requestFactory.
        """
        customFactory = object()

        site = server.Site(resource=SimpleResource(), requestFactory=customFactory)

        self.assertIs(customFactory, site.requestFactory)

    def test_buildProtocol(self):
        """
        Returns a C{Channel} whose C{site} and C{requestFactory} attributes are
        assigned from the C{site} instance.
        """
        site = server.Site(SimpleResource())

        channel = site.buildProtocol(None)

        self.assertIs(site, channel.site)
        self.assertIs(site.requestFactory, channel.requestFactory)

    def test_makeSession(self):
        """
        L{site.getSession} generates a new C{Session} instance with an uid of
        type L{bytes}.
        """
        site = server.Site(resource.Resource())
        session = self.getAutoExpiringSession(site)

        self.assertIsInstance(session, server.Session)
        self.assertIsInstance(session.uid, bytes)

    def test_sessionUIDGeneration(self):
        """
        L{site.getSession} generates L{Session} objects with distinct UIDs from
        a secure source of entropy.
        """
        site = server.Site(resource.Resource())
        # Ensure that we _would_ use the unpredictable random source if the
        # test didn't stub it.
        self.assertIdentical(site._entropy, os.urandom)

        def predictableEntropy(n):
            predictableEntropy.x += 1
            return (chr(predictableEntropy.x) * n).encode("charmap")

        predictableEntropy.x = 0
        self.patch(site, "_entropy", predictableEntropy)
        a = self.getAutoExpiringSession(site)
        b = self.getAutoExpiringSession(site)
        self.assertEqual(a.uid, b"01" * 0x20)
        self.assertEqual(b.uid, b"02" * 0x20)
        # This functionality is silly (the value is no longer used in session
        # generation), but 'counter' was a public attribute since time
        # immemorial so we should make sure if anyone was using it to get site
        # metrics or something it keeps working.
        self.assertEqual(site.counter, 2)

    def test_getSessionExistent(self):
        """
        L{site.getSession} gets a previously generated session, by its unique
        ID.
        """
        site = server.Site(resource.Resource())
        createdSession = self.getAutoExpiringSession(site)

        retrievedSession = site.getSession(createdSession.uid)

        self.assertIs(createdSession, retrievedSession)

    def test_getSessionNonExistent(self):
        """
        L{site.getSession} raises a L{KeyError} if the session is not found.
        """
        site = server.Site(resource.Resource())

        self.assertRaises(KeyError, site.getSession, b"no-such-uid")


class SessionTests(unittest.TestCase):
    """
    Tests for L{server.Session}.
    """

    def setUp(self):
        """
        Create a site with one active session using a deterministic, easily
        controlled clock.
        """
        self.clock = Clock()
        self.uid = b"unique"
        self.site = server.Site(resource.Resource(), reactor=self.clock)
        self.session = server.Session(self.site, self.uid)
        self.site.sessions[self.uid] = self.session

    def test_defaultReactor(self):
        """
        If no value is passed to L{server.Session.__init__}, the reactor
        associated with the site is used.
        """
        site = server.Site(resource.Resource(), reactor=Clock())
        session = server.Session(site, b"123")
        self.assertIdentical(session._reactor, site.reactor)

    def test_explicitReactor(self):
        """
        L{Session} accepts the reactor to use as a parameter.
        """
        site = server.Site(resource.Resource())
        otherReactor = Clock()

        session = server.Session(site, b"123", reactor=otherReactor)

        self.assertIdentical(session._reactor, otherReactor)

    def test_startCheckingExpiration(self):
        """
        L{server.Session.startCheckingExpiration} causes the session to expire
        after L{server.Session.sessionTimeout} seconds without activity.
        """
        self.session.startCheckingExpiration()

        # Advance to almost the timeout - nothing should happen.
        self.clock.advance(self.session.sessionTimeout - 1)
        self.assertIn(self.uid, self.site.sessions)

        # Advance to the timeout, the session should expire.
        self.clock.advance(1)
        self.assertNotIn(self.uid, self.site.sessions)

        # There should be no calls left over, either.
        self.assertFalse(self.clock.calls)

    def test_expire(self):
        """
        L{server.Session.expire} expires the session.
        """
        self.session.expire()
        # It should be gone from the session dictionary.
        self.assertNotIn(self.uid, self.site.sessions)
        # And there should be no pending delayed calls.
        self.assertFalse(self.clock.calls)

    def test_expireWhileChecking(self):
        """
        L{server.Session.expire} expires the session even if the timeout call
        isn't due yet.
        """
        self.session.startCheckingExpiration()
        self.test_expire()

    def test_notifyOnExpire(self):
        """
        A function registered with L{server.Session.notifyOnExpire} is called
        when the session expires.
        """
        callbackRan = [False]

        def expired():
            callbackRan[0] = True

        self.session.notifyOnExpire(expired)
        self.session.expire()
        self.assertTrue(callbackRan[0])

    def test_touch(self):
        """
        L{server.Session.touch} updates L{server.Session.lastModified} and
        delays session timeout.
        """
        # Make sure it works before startCheckingExpiration
        self.clock.advance(3)
        self.session.touch()
        self.assertEqual(self.session.lastModified, 3)

        # And after startCheckingExpiration
        self.session.startCheckingExpiration()
        self.clock.advance(self.session.sessionTimeout - 1)
        self.session.touch()
        self.clock.advance(self.session.sessionTimeout - 1)
        self.assertIn(self.uid, self.site.sessions)

        # It should have advanced it by just sessionTimeout, no more.
        self.clock.advance(1)
        self.assertNotIn(self.uid, self.site.sessions)


# Conditional requests:
# If-None-Match, If-Modified-Since

# make conditional request:
#   normal response if condition succeeds
#   if condition fails:
#      response code
#      no body


def httpBody(whole):
    return whole.split(b"\r\n\r\n", 1)[1]


def httpHeader(whole, key):
    key = key.lower()
    headers = whole.split(b"\r\n\r\n", 1)[0]
    for header in headers.split(b"\r\n"):
        if header.lower().startswith(key):
            return header.split(b":", 1)[1].strip()
    return None


def httpCode(whole):
    l1 = whole.split(b"\r\n", 1)[0]
    return int(l1.split()[1])


class ConditionalTests(unittest.TestCase):
    """
    web.server's handling of conditional requests for cache validation.
    """

    def setUp(self):
        self.resrc = SimpleResource()
        self.resrc.putChild(b"", self.resrc)
        self.resrc.putChild(b"with-content-type", SimpleResource(b"image/jpeg"))
        self.site = server.Site(self.resrc)
        self.site.startFactory()
        self.addCleanup(self.site.stopFactory)

        # HELLLLLLLLLLP!  This harness is Very Ugly.
        self.channel = self.site.buildProtocol(None)
        self.transport = http.StringTransport()
        self.transport.close = lambda *a, **kw: None
        self.transport.disconnecting = lambda *a, **kw: 0
        self.transport.getPeer = lambda *a, **kw: "peer"
        self.transport.getHost = lambda *a, **kw: "host"
        self.channel.makeConnection(self.transport)

    def tearDown(self):
        self.channel.connectionLost(None)

    def _modifiedTest(self, modifiedSince=None, etag=None):
        """
        Given the value C{modifiedSince} for the I{If-Modified-Since} header or
        the value C{etag} for the I{If-Not-Match} header, verify that a response
        with a 200 code, a default Content-Type, and the resource as the body is
        returned.
        """
        if modifiedSince is not None:
            validator = b"If-Modified-Since: " + modifiedSince
        else:
            validator = b"If-Not-Match: " + etag
        for line in [b"GET / HTTP/1.1", validator, b""]:
            self.channel.dataReceived(line + b"\r\n")
        result = self.transport.getvalue()
        self.assertEqual(httpCode(result), http.OK)
        self.assertEqual(httpBody(result), b"correct")
        self.assertEqual(httpHeader(result, b"Content-Type"), b"text/html")

    def test_modified(self):
        """
        If a request is made with an I{If-Modified-Since} header value with
        a timestamp indicating a time before the last modification of the
        requested resource, a 200 response is returned along with a response
        body containing the resource.
        """
        self._modifiedTest(modifiedSince=http.datetimeToString(1))

    def test_unmodified(self):
        """
        If a request is made with an I{If-Modified-Since} header value with a
        timestamp indicating a time after the last modification of the request
        resource, a 304 response is returned along with an empty response body
        and no Content-Type header if the application does not set one.
        """
        for line in [
            b"GET / HTTP/1.1",
            b"If-Modified-Since: " + http.datetimeToString(100),
            b"",
        ]:
            self.channel.dataReceived(line + b"\r\n")
        result = self.transport.getvalue()
        self.assertEqual(httpCode(result), http.NOT_MODIFIED)
        self.assertEqual(httpBody(result), b"")
        # Since there SHOULD NOT (RFC 2616, section 10.3.5) be any
        # entity-headers, the Content-Type is not set if the application does
        # not explicitly set it.
        self.assertEqual(httpHeader(result, b"Content-Type"), None)

    def test_invalidTimestamp(self):
        """
        If a request is made with an I{If-Modified-Since} header value which
        cannot be parsed, the header is treated as not having been present
        and a normal 200 response is returned with a response body
        containing the resource.
        """
        self._modifiedTest(modifiedSince=b"like, maybe a week ago, I guess?")

    def test_invalidTimestampYear(self):
        """
        If a request is made with an I{If-Modified-Since} header value which
        contains a string in the year position which is not an integer, the
        header is treated as not having been present and a normal 200
        response is returned with a response body containing the resource.
        """
        self._modifiedTest(modifiedSince=b"Thu, 01 Jan blah 00:00:10 GMT")

    def test_invalidTimestampTooLongAgo(self):
        """
        If a request is made with an I{If-Modified-Since} header value which
        contains a year before the epoch, the header is treated as not
        having been present and a normal 200 response is returned with a
        response body containing the resource.
        """
        self._modifiedTest(modifiedSince=b"Thu, 01 Jan 1899 00:00:10 GMT")

    def test_invalidTimestampMonth(self):
        """
        If a request is made with an I{If-Modified-Since} header value which
        contains a string in the month position which is not a recognized
        month abbreviation, the header is treated as not having been present
        and a normal 200 response is returned with a response body
        containing the resource.
        """
        self._modifiedTest(modifiedSince=b"Thu, 01 Blah 1970 00:00:10 GMT")

    def test_etagMatchedNot(self):
        """
        If a request is made with an I{If-None-Match} ETag which does not match
        the current ETag of the requested resource, the header is treated as not
        having been present and a normal 200 response is returned with a
        response body containing the resource.
        """
        self._modifiedTest(etag=b"unmatchedTag")

    def test_etagMatched(self):
        """
        If a request is made with an I{If-None-Match} ETag which does match the
        current ETag of the requested resource, a 304 response is returned along
        with an empty response body.
        """
        for line in [b"GET / HTTP/1.1", b"If-None-Match: MatchingTag", b""]:
            self.channel.dataReceived(line + b"\r\n")
        result = self.transport.getvalue()
        self.assertEqual(httpHeader(result, b"ETag"), b"MatchingTag")
        self.assertEqual(httpCode(result), http.NOT_MODIFIED)
        self.assertEqual(httpBody(result), b"")

    def test_unmodifiedWithContentType(self):
        """
        Similar to L{test_etagMatched}, but the response should include a
        I{Content-Type} header if the application explicitly sets one.

        This I{Content-Type} header SHOULD NOT be present according to RFC 2616,
        section 10.3.5.  It will only be present if the application explicitly
        sets it.
        """
        for line in [
            b"GET /with-content-type HTTP/1.1",
            b"If-None-Match: MatchingTag",
            b"",
        ]:
            self.channel.dataReceived(line + b"\r\n")
        result = self.transport.getvalue()
        self.assertEqual(httpCode(result), http.NOT_MODIFIED)
        self.assertEqual(httpBody(result), b"")
        self.assertEqual(httpHeader(result, b"Content-Type"), b"image/jpeg")


class RequestTests(unittest.TestCase):
    """
    Tests for the HTTP request class, L{server.Request}.
    """

    def test_interface(self):
        """
        L{server.Request} instances provide L{iweb.IRequest}.
        """
        self.assertTrue(
            verifyObject(iweb.IRequest, server.Request(DummyChannel(), True))
        )

    def test_hashable(self):
        """
        L{server.Request} instances are hashable, thus can be put in a mapping.
        """
        request = server.Request(DummyChannel(), True)
        hash(request)

    def testChildLink(self):
        request = server.Request(DummyChannel(), 1)
        request.gotLength(0)
        request.requestReceived(b"GET", b"/foo/bar", b"HTTP/1.0")
        self.assertEqual(request.childLink(b"baz"), b"bar/baz")
        request = server.Request(DummyChannel(), 1)
        request.gotLength(0)
        request.requestReceived(b"GET", b"/foo/bar/", b"HTTP/1.0")
        self.assertEqual(request.childLink(b"baz"), b"baz")

    def testPrePathURLSimple(self):
        request = server.Request(DummyChannel(), 1)
        request.gotLength(0)
        request.requestReceived(b"GET", b"/foo/bar", b"HTTP/1.0")
        request.setHost(b"example.com", 80)
        self.assertEqual(request.prePathURL(), b"http://example.com/foo/bar")

    def testPrePathURLNonDefault(self):
        d = DummyChannel()
        d.transport.port = 81
        request = server.Request(d, 1)
        request.setHost(b"example.com", 81)
        request.gotLength(0)
        request.requestReceived(b"GET", b"/foo/bar", b"HTTP/1.0")
        self.assertEqual(request.prePathURL(), b"http://example.com:81/foo/bar")

    def testPrePathURLSSLPort(self):
        d = DummyChannel()
        d.transport.port = 443
        request = server.Request(d, 1)
        request.setHost(b"example.com", 443)
        request.gotLength(0)
        request.requestReceived(b"GET", b"/foo/bar", b"HTTP/1.0")
        self.assertEqual(request.prePathURL(), b"http://example.com:443/foo/bar")

    def testPrePathURLSSLPortAndSSL(self):
        d = DummyChannel()
        d.transport = DummyChannel.SSL()
        d.transport.port = 443
        request = server.Request(d, 1)
        request.setHost(b"example.com", 443)
        request.gotLength(0)
        request.requestReceived(b"GET", b"/foo/bar", b"HTTP/1.0")
        self.assertEqual(request.prePathURL(), b"https://example.com/foo/bar")

    def testPrePathURLHTTPPortAndSSL(self):
        d = DummyChannel()
        d.transport = DummyChannel.SSL()
        d.transport.port = 80
        request = server.Request(d, 1)
        request.setHost(b"example.com", 80)
        request.gotLength(0)
        request.requestReceived(b"GET", b"/foo/bar", b"HTTP/1.0")
        self.assertEqual(request.prePathURL(), b"https://example.com:80/foo/bar")

    def testPrePathURLSSLNonDefault(self):
        d = DummyChannel()
        d.transport = DummyChannel.SSL()
        d.transport.port = 81
        request = server.Request(d, 1)
        request.setHost(b"example.com", 81)
        request.gotLength(0)
        request.requestReceived(b"GET", b"/foo/bar", b"HTTP/1.0")
        self.assertEqual(request.prePathURL(), b"https://example.com:81/foo/bar")

    def testPrePathURLSetSSLHost(self):
        d = DummyChannel()
        d.transport.port = 81
        request = server.Request(d, 1)
        request.setHost(b"foo.com", 81, 1)
        request.gotLength(0)
        request.requestReceived(b"GET", b"/foo/bar", b"HTTP/1.0")
        self.assertEqual(request.prePathURL(), b"https://foo.com:81/foo/bar")

    def test_prePathURLQuoting(self):
        """
        L{Request.prePathURL} quotes special characters in the URL segments to
        preserve the original meaning.
        """
        d = DummyChannel()
        request = server.Request(d, 1)
        request.setHost(b"example.com", 80)
        request.gotLength(0)
        request.requestReceived(b"GET", b"/foo%2Fbar", b"HTTP/1.0")
        self.assertEqual(request.prePathURL(), b"http://example.com/foo%2Fbar")

    def test_processingFailedNoTracebackByDefault(self):
        """
        By default, L{Request.processingFailed} does not write out the failure,
        but give a generic error message, as L{Site.displayTracebacks} is
        disabled by default.
        """
        logObserver = EventLoggingObserver.createWithCleanup(self, globalLogPublisher)

        d = DummyChannel()
        request = server.Request(d, 1)
        request.site = server.Site(resource.Resource())
        fail = failure.Failure(Exception("Oh no!"))
        request.processingFailed(fail)

        self.assertNotIn(b"Oh no!", request.transport.written.getvalue())
        self.assertIn(b"Processing Failed", request.transport.written.getvalue())
        self.assertEquals(1, len(logObserver))

        event = logObserver[0]
        f = event["log_failure"]
        self.assertIsInstance(f.value, Exception)
        self.assertEquals(f.getErrorMessage(), "Oh no!")

        # Since we didn't "handle" the exception, flush it to prevent a test
        # failure
        self.assertEqual(1, len(self.flushLoggedErrors()))

    def test_processingFailedNoTraceback(self):
        """
        L{Request.processingFailed} when the site has C{displayTracebacks} set
        to C{False} does not write out the failure, but give a generic error
        message.
        """
        logObserver = EventLoggingObserver.createWithCleanup(self, globalLogPublisher)

        d = DummyChannel()
        request = server.Request(d, 1)
        request.site = server.Site(resource.Resource())
        request.site.displayTracebacks = False
        fail = failure.Failure(Exception("Oh no!"))
        request.processingFailed(fail)

        self.assertNotIn(b"Oh no!", request.transport.written.getvalue())
        self.assertIn(b"Processing Failed", request.transport.written.getvalue())
        self.assertEquals(1, len(logObserver))

        event = logObserver[0]
        f = event["log_failure"]
        self.assertIsInstance(f.value, Exception)
        self.assertEquals(f.getErrorMessage(), "Oh no!")

        # Since we didn't "handle" the exception, flush it to prevent a test
        # failure
        self.assertEqual(1, len(self.flushLoggedErrors()))

    def test_processingFailedDisplayTraceback(self):
        """
        L{Request.processingFailed} when the site has C{displayTracebacks} set
        to C{True} writes out the failure.
        """
        logObserver = EventLoggingObserver.createWithCleanup(self, globalLogPublisher)

        d = DummyChannel()
        request = server.Request(d, 1)
        request.site = server.Site(resource.Resource())
        request.site.displayTracebacks = True
        fail = failure.Failure(Exception("Oh no!"))
        request.processingFailed(fail)

        self.assertIn(b"Oh no!", request.transport.written.getvalue())

        event = logObserver[0]
        f = event["log_failure"]
        self.assertIsInstance(f.value, Exception)
        self.assertEquals(f.getErrorMessage(), "Oh no!")
        # Since we didn't "handle" the exception, flush it to prevent a test
        # failure
        self.assertEqual(1, len(self.flushLoggedErrors()))

    def test_processingFailedDisplayTracebackHandlesUnicode(self):
        """
        L{Request.processingFailed} when the site has C{displayTracebacks} set
        to C{True} writes out the failure, making UTF-8 items into HTML
        entities.
        """
        logObserver = EventLoggingObserver.createWithCleanup(self, globalLogPublisher)

        d = DummyChannel()
        request = server.Request(d, 1)
        request.site = server.Site(resource.Resource())
        request.site.displayTracebacks = True
        fail = failure.Failure(Exception("\u2603"))
        request.processingFailed(fail)

        self.assertIn(b"&#9731;", request.transport.written.getvalue())

        # On some platforms, we get a UnicodeError when trying to
        # display the Failure with twisted.python.log because
        # the default encoding cannot display u"\u2603".  Windows for example
        # uses a default encodig of cp437 which does not support u"\u2603".
        self.flushLoggedErrors(UnicodeError)

        event = logObserver[0]
        f = event["log_failure"]
        self.assertIsInstance(f.value, Exception)
        # Since we didn't "handle" the exception, flush it to prevent a test
        # failure
        self.assertEqual(1, len(self.flushLoggedErrors()))

    def test_sessionDifferentFromSecureSession(self):
        """
        L{Request.session} and L{Request.secure_session} should be two separate
        sessions with unique ids and different cookies.
        """
        d = DummyChannel()
        d.transport = DummyChannel.SSL()
        request = server.Request(d, 1)
        request.site = server.Site(resource.Resource())
        request.sitepath = []
        secureSession = request.getSession()
        self.assertIsNotNone(secureSession)
        self.addCleanup(secureSession.expire)
        self.assertEqual(request.cookies[0].split(b"=")[0], b"TWISTED_SECURE_SESSION")
        session = request.getSession(forceNotSecure=True)
        self.assertIsNotNone(session)
        self.assertEqual(request.cookies[1].split(b"=")[0], b"TWISTED_SESSION")
        self.addCleanup(session.expire)
        self.assertNotEqual(session.uid, secureSession.uid)

    def test_sessionAttribute(self):
        """
        On a L{Request}, the C{session} attribute retrieves the associated
        L{Session} only if it has been initialized.  If the request is secure,
        it retrieves the secure session.
        """
        site = server.Site(resource.Resource())
        d = DummyChannel()
        d.transport = DummyChannel.SSL()
        request = server.Request(d, 1)
        request.site = site
        request.sitepath = []
        self.assertIs(request.session, None)
        insecureSession = request.getSession(forceNotSecure=True)
        self.addCleanup(insecureSession.expire)
        self.assertIs(request.session, None)
        secureSession = request.getSession()
        self.addCleanup(secureSession.expire)
        self.assertIsNot(secureSession, None)
        self.assertIsNot(secureSession, insecureSession)
        self.assertIs(request.session, secureSession)

    def test_sessionCaching(self):
        """
        L{Request.getSession} creates the session object only once per request;
        if it is called twice it returns the identical result.
        """
        site = server.Site(resource.Resource())
        d = DummyChannel()
        request = server.Request(d, 1)
        request.site = site
        request.sitepath = []
        session1 = request.getSession()
        self.addCleanup(session1.expire)
        session2 = request.getSession()
        self.assertIs(session1, session2)

    def test_retrieveExistingSession(self):
        """
        L{Request.getSession} retrieves an existing session if the relevant
        cookie is set in the incoming request.
        """
        site = server.Site(resource.Resource())
        d = DummyChannel()
        request = server.Request(d, 1)
        request.site = site
        request.sitepath = []
        mySession = server.Session(site, b"special-id")
        site.sessions[mySession.uid] = mySession
        request.received_cookies[b"TWISTED_SESSION"] = mySession.uid
        self.assertIs(request.getSession(), mySession)

    def test_retrieveNonExistentSession(self):
        """
        L{Request.getSession} generates a new session if the session ID
        advertised in the cookie from the incoming request is not found.
        """
        site = server.Site(resource.Resource())
        d = DummyChannel()
        request = server.Request(d, 1)
        request.site = site
        request.sitepath = []
        request.received_cookies[b"TWISTED_SESSION"] = b"does-not-exist"
        session = request.getSession()
        self.assertIsNotNone(session)
        self.addCleanup(session.expire)
        self.assertTrue(request.cookies[0].startswith(b"TWISTED_SESSION="))
        # It should be a new session ID.
        self.assertNotIn(b"does-not-exist", request.cookies[0])

    def test_getSessionExpired(self):
        """
        L{Request.getSession} generates a new session when the previous
        session has expired.
        """
        clock = Clock()
        site = server.Site(resource.Resource())
        d = DummyChannel()
        request = server.Request(d, 1)
        request.site = site
        request.sitepath = []

        def sessionFactoryWithClock(site, uid):
            """
            Forward to normal session factory, but inject the clock.

            @param site: The site on which the session is created.
            @type site: L{server.Site}

            @param uid: A unique identifier for the session.
            @type uid: C{bytes}

            @return: A newly created session.
            @rtype: L{server.Session}
            """
            session = sessionFactory(site, uid)
            session._reactor = clock
            return session

        # The site is patch to allow injecting a clock to the session.
        sessionFactory = site.sessionFactory
        site.sessionFactory = sessionFactoryWithClock

        initialSession = request.getSession()

        # When the session is requested after the session timeout,
        # no error is raised and a new session is returned.
        clock.advance(sessionFactory.sessionTimeout)
        newSession = request.getSession()
        self.addCleanup(newSession.expire)

        self.assertIsNot(initialSession, newSession)
        self.assertNotEqual(initialSession.uid, newSession.uid)

    def test_OPTIONSStar(self):
        """
        L{Request} handles OPTIONS * requests by doing a fast-path return of
        200 OK.
        """
        d = DummyChannel()
        request = server.Request(d, 1)
        request.setHost(b"example.com", 80)
        request.gotLength(0)
        request.requestReceived(b"OPTIONS", b"*", b"HTTP/1.1")

        response = d.transport.written.getvalue()
        self.assertTrue(response.startswith(b"HTTP/1.1 200 OK"))
        self.assertIn(b"Content-Length: 0\r\n", response)

    def test_rejectNonOPTIONSStar(self):
        """
        L{Request} handles any non-OPTIONS verb requesting the * path by doing
        a fast-return 405 Method Not Allowed, indicating only the support for
        OPTIONS.
        """
        d = DummyChannel()
        request = server.Request(d, 1)
        request.setHost(b"example.com", 80)
        request.gotLength(0)
        request.requestReceived(b"GET", b"*", b"HTTP/1.1")

        response = d.transport.written.getvalue()
        self.assertTrue(response.startswith(b"HTTP/1.1 405 Method Not Allowed"))
        self.assertIn(b"Content-Length: 0\r\n", response)
        self.assertIn(b"Allow: OPTIONS\r\n", response)

    def test_noDefaultContentTypeOnZeroLengthResponse(self):
        """
        Responses with no length do not have a default content-type applied.
        """
        resrc = ZeroLengthResource()
        resrc.putChild(b"", resrc)
        site = server.Site(resrc)
        d = DummyChannel()
        d.site = site
        request = server.Request(d, 1)
        request.site = site
        request.setHost(b"example.com", 80)
        request.gotLength(0)
        request.requestReceived(b"GET", b"/", b"HTTP/1.1")

        self.assertNotIn(b"content-type", request.transport.written.getvalue().lower())

    def test_noDefaultContentTypeOn204Response(self):
        """
        Responses with a 204 status code have no default content-type applied.
        """
        resrc = NoContentResource()
        resrc.putChild(b"", resrc)
        site = server.Site(resrc)
        d = DummyChannel()
        d.site = site
        request = server.Request(d, 1)
        request.site = site
        request.setHost(b"example.com", 80)
        request.gotLength(0)
        request.requestReceived(b"GET", b"/", b"HTTP/1.1")

        response = request.transport.written.getvalue()
        self.assertTrue(response.startswith(b"HTTP/1.1 204 No Content\r\n"))
        self.assertNotIn(b"content-type", response.lower())

    def test_defaultSmallContentFile(self):
        """
        L{http.Request} creates a L{BytesIO} if the content length is small and
        the site doesn't offer to create one.
        """
        request = server.Request(DummyChannel())
        request.gotLength(100000 - 1)
        self.assertIsInstance(request.content, BytesIO)

    def test_defaultLargerContentFile(self):
        """
        L{http.Request} creates a temporary file on the filesystem if the
        content length is larger and the site doesn't offer to create one.
        """
        request = server.Request(DummyChannel())
        request.gotLength(100000)
        assertIsFilesystemTemporary(self, request.content)

    def test_defaultUnknownSizeContentFile(self):
        """
        L{http.Request} creates a temporary file on the filesystem if the
        content length is not known and the site doesn't offer to create one.
        """
        request = server.Request(DummyChannel())
        request.gotLength(None)
        assertIsFilesystemTemporary(self, request.content)

    def test_siteSuppliedContentFile(self):
        """
        L{http.Request} uses L{Site.getContentFile}, if it exists, to get a
        file-like object for the request content.
        """
        lengths = []
        contentFile = BytesIO()
        site = server.Site(resource.Resource())

        def getContentFile(length):
            lengths.append(length)
            return contentFile

        site.getContentFile = getContentFile

        channel = DummyChannel()
        channel.site = site

        request = server.Request(channel)
        request.gotLength(12345)
        self.assertEqual([12345], lengths)
        self.assertIs(contentFile, request.content)


class GzipEncoderTests(unittest.TestCase):
    def setUp(self):
        self.channel = DummyChannel()
        staticResource = Data(b"Some data", "text/plain")
        wrapped = resource.EncodingResourceWrapper(
            staticResource, [server.GzipEncoderFactory()]
        )
        self.channel.site.resource.putChild(b"foo", wrapped)

    def test_interfaces(self):
        """
        L{server.GzipEncoderFactory} implements the
        L{iweb._IRequestEncoderFactory} and its C{encoderForRequest} returns an
        instance of L{server._GzipEncoder} which implements
        L{iweb._IRequestEncoder}.
        """
        request = server.Request(self.channel, False)
        request.gotLength(0)
        request.requestHeaders.setRawHeaders(b"Accept-Encoding", [b"gzip,deflate"])
        factory = server.GzipEncoderFactory()
        self.assertTrue(verifyObject(iweb._IRequestEncoderFactory, factory))

        encoder = factory.encoderForRequest(request)
        self.assertTrue(verifyObject(iweb._IRequestEncoder, encoder))

    def test_encoding(self):
        """
        If the client request passes a I{Accept-Encoding} header which mentions
        gzip, L{server._GzipEncoder} automatically compresses the data.
        """
        request = server.Request(self.channel, False)
        request.gotLength(0)
        request.requestHeaders.setRawHeaders(b"Accept-Encoding", [b"gzip,deflate"])
        request.requestReceived(b"GET", b"/foo", b"HTTP/1.0")
        data = self.channel.transport.written.getvalue()
        self.assertNotIn(b"Content-Length", data)
        self.assertIn(b"Content-Encoding: gzip\r\n", data)
        body = data[data.find(b"\r\n\r\n") + 4 :]
        self.assertEqual(b"Some data", zlib.decompress(body, 16 + zlib.MAX_WBITS))

    def test_whitespaceInAcceptEncoding(self):
        """
        If the client request passes a I{Accept-Encoding} header which mentions
        gzip, with whitespace inbetween the encoding name and the commas,
        L{server._GzipEncoder} automatically compresses the data.
        """
        request = server.Request(self.channel, False)
        request.gotLength(0)
        request.requestHeaders.setRawHeaders(b"Accept-Encoding", [b"deflate, gzip"])
        request.requestReceived(b"GET", b"/foo", b"HTTP/1.0")
        data = self.channel.transport.written.getvalue()
        self.assertNotIn(b"Content-Length", data)
        self.assertIn(b"Content-Encoding: gzip\r\n", data)
        body = data[data.find(b"\r\n\r\n") + 4 :]
        self.assertEqual(b"Some data", zlib.decompress(body, 16 + zlib.MAX_WBITS))

    def test_nonEncoding(self):
        """
        L{server.GzipEncoderFactory} doesn't return a L{server._GzipEncoder} if
        the I{Accept-Encoding} header doesn't mention gzip support.
        """
        request = server.Request(self.channel, False)
        request.gotLength(0)
        request.requestHeaders.setRawHeaders(b"Accept-Encoding", [b"foo,bar"])
        request.requestReceived(b"GET", b"/foo", b"HTTP/1.0")
        data = self.channel.transport.written.getvalue()
        self.assertIn(b"Content-Length", data)
        self.assertNotIn(b"Content-Encoding: gzip\r\n", data)
        body = data[data.find(b"\r\n\r\n") + 4 :]
        self.assertEqual(b"Some data", body)

    def test_multipleAccept(self):
        """
        If there are multiple I{Accept-Encoding} header,
        L{server.GzipEncoderFactory} reads them properly to detect if gzip is
        supported.
        """
        request = server.Request(self.channel, False)
        request.gotLength(0)
        request.requestHeaders.setRawHeaders(b"Accept-Encoding", [b"deflate", b"gzip"])
        request.requestReceived(b"GET", b"/foo", b"HTTP/1.0")
        data = self.channel.transport.written.getvalue()
        self.assertNotIn(b"Content-Length", data)
        self.assertIn(b"Content-Encoding: gzip\r\n", data)
        body = data[data.find(b"\r\n\r\n") + 4 :]
        self.assertEqual(b"Some data", zlib.decompress(body, 16 + zlib.MAX_WBITS))

    def test_alreadyEncoded(self):
        """
        If the content is already encoded and the I{Content-Encoding} header is
        set, L{server.GzipEncoderFactory} properly appends gzip to it.
        """
        request = server.Request(self.channel, False)
        request.gotLength(0)
        request.requestHeaders.setRawHeaders(b"Accept-Encoding", [b"deflate", b"gzip"])
        request.responseHeaders.setRawHeaders(b"Content-Encoding", [b"deflate"])
        request.requestReceived(b"GET", b"/foo", b"HTTP/1.0")
        data = self.channel.transport.written.getvalue()
        self.assertNotIn(b"Content-Length", data)
        self.assertIn(b"Content-Encoding: deflate,gzip\r\n", data)
        body = data[data.find(b"\r\n\r\n") + 4 :]
        self.assertEqual(b"Some data", zlib.decompress(body, 16 + zlib.MAX_WBITS))

    def test_multipleEncodingLines(self):
        """
        If there are several I{Content-Encoding} headers,
        L{server.GzipEncoderFactory} normalizes it and appends gzip to the
        field value.
        """
        request = server.Request(self.channel, False)
        request.gotLength(0)
        request.requestHeaders.setRawHeaders(b"Accept-Encoding", [b"deflate", b"gzip"])
        request.responseHeaders.setRawHeaders(b"Content-Encoding", [b"foo", b"bar"])
        request.requestReceived(b"GET", b"/foo", b"HTTP/1.0")
        data = self.channel.transport.written.getvalue()
        self.assertNotIn(b"Content-Length", data)
        self.assertIn(b"Content-Encoding: foo,bar,gzip\r\n", data)
        body = data[data.find(b"\r\n\r\n") + 4 :]
        self.assertEqual(b"Some data", zlib.decompress(body, 16 + zlib.MAX_WBITS))


class RootResource(resource.Resource):
    isLeaf = 0

    def getChildWithDefault(self, name, request):
        request.rememberRootURL()
        return resource.Resource.getChildWithDefault(self, name, request)

    def render(self, request):
        return ""


class RememberURLTests(unittest.TestCase):
    """
    Tests for L{server.Site}'s root request URL calculation.
    """

    def createServer(self, r):
        """
        Create a L{server.Site} bound to a L{DummyChannel} and the
        given resource as its root.

        @param r: The root resource.
        @type r: L{resource.Resource}

        @return: The channel to which the site is bound.
        @rtype: L{DummyChannel}
        """
        chan = DummyChannel()
        chan.site = server.Site(r)
        return chan

    def testSimple(self):
        """
        The path component of the root URL of a L{server.Site} whose
        root resource is below C{/} is that resource's path, and the
        netloc component is the L{site.Server}'s own host and port.
        """
        r = resource.Resource()
        r.isLeaf = 0
        rr = RootResource()
        r.putChild(b"foo", rr)
        rr.putChild(b"", rr)
        rr.putChild(b"bar", resource.Resource())
        chan = self.createServer(r)
        for url in [b"/foo/", b"/foo/bar", b"/foo/bar/baz", b"/foo/bar/"]:
            request = server.Request(chan, 1)
            request.setHost(b"example.com", 81)
            request.gotLength(0)
            request.requestReceived(b"GET", url, b"HTTP/1.0")
            self.assertEqual(request.getRootURL(), b"http://example.com:81/foo")

    def testRoot(self):
        """
        The path component of the root URL of a L{server.Site} whose
        root resource is at C{/} is C{/}, and the netloc component is
        the L{site.Server}'s own host and port.
        """
        rr = RootResource()
        rr.putChild(b"", rr)
        rr.putChild(b"bar", resource.Resource())
        chan = self.createServer(rr)
        for url in [b"/", b"/bar", b"/bar/baz", b"/bar/"]:
            request = server.Request(chan, 1)
            request.setHost(b"example.com", 81)
            request.gotLength(0)
            request.requestReceived(b"GET", url, b"HTTP/1.0")
            self.assertEqual(request.getRootURL(), b"http://example.com:81/")


class NewRenderResource(resource.Resource):
    def render_GET(self, request):
        return b"hi hi"

    def render_HEH(self, request):
        return b"ho ho"


@implementer(resource.IResource)
class HeadlessResource:
    """
    A resource that implements GET but not HEAD.
    """

    allowedMethods = [b"GET"]

    def render(self, request):
        """
        Leave the request open for future writes.
        """
        self.request = request
        if request.method not in self.allowedMethods:
            raise error.UnsupportedMethod(self.allowedMethods)
        self.request.write(b"some data")
        return server.NOT_DONE_YET

    def isLeaf(self):
        """
        # IResource.isLeaf
        """
        raise NotImplementedError()

    def getChildWithDefault(self, name, request):
        """
        # IResource.getChildWithDefault
        """
        raise NotImplementedError()

    def putChild(self, path, child):
        """
        # IResource.putChild
        """
        raise NotImplementedError()


class NewRenderTests(unittest.TestCase):
    """
    Tests for L{server.Request.render}.
    """

    def _getReq(self, resource=None):
        """
        Create a request object with a stub channel and install the
        passed resource at /newrender. If no resource is passed,
        create one.
        """
        d = DummyChannel()
        if resource is None:
            resource = NewRenderResource()
        d.site.resource.putChild(b"newrender", resource)
        d.transport.port = 81
        request = server.Request(d, 1)
        request.setHost(b"example.com", 81)
        request.gotLength(0)
        return request

    def testGoodMethods(self):
        req = self._getReq()
        req.requestReceived(b"GET", b"/newrender", b"HTTP/1.0")
        self.assertEqual(req.transport.written.getvalue().splitlines()[-1], b"hi hi")

        req = self._getReq()
        req.requestReceived(b"HEH", b"/newrender", b"HTTP/1.0")
        self.assertEqual(req.transport.written.getvalue().splitlines()[-1], b"ho ho")

    def testBadMethods(self):
        req = self._getReq()
        req.requestReceived(b"CONNECT", b"/newrender", b"HTTP/1.0")
        self.assertEqual(req.code, 501)

        req = self._getReq()
        req.requestReceived(b"hlalauguG", b"/newrender", b"HTTP/1.0")
        self.assertEqual(req.code, 501)

    def test_notAllowedMethod(self):
        """
        When trying to invoke a method not in the allowed method list, we get
        a response saying it is not allowed.
        """
        req = self._getReq()
        req.requestReceived(b"POST", b"/newrender", b"HTTP/1.0")
        self.assertEqual(req.code, 405)
        self.assertTrue(req.responseHeaders.hasHeader(b"allow"))
        raw_header = req.responseHeaders.getRawHeaders(b"allow")[0]
        allowed = sorted(h.strip() for h in raw_header.split(b","))
        self.assertEqual([b"GET", b"HEAD", b"HEH"], allowed)

    def testImplicitHead(self):
        logObserver = EventLoggingObserver.createWithCleanup(self, globalLogPublisher)

        req = self._getReq()
        req.requestReceived(b"HEAD", b"/newrender", b"HTTP/1.0")
        self.assertEqual(req.code, 200)
        self.assertEqual(-1, req.transport.written.getvalue().find(b"hi hi"))

        self.assertEquals(1, len(logObserver))
        event = logObserver[0]
        self.assertEquals(event["log_level"], LogLevel.info)

    def test_unsupportedHead(self):
        """
        HEAD requests against resource that only claim support for GET
        should not include a body in the response.
        """
        logObserver = EventLoggingObserver.createWithCleanup(self, globalLogPublisher)

        resource = HeadlessResource()
        req = self._getReq(resource)
        req.requestReceived(b"HEAD", b"/newrender", b"HTTP/1.0")
        headers, body = req.transport.written.getvalue().split(b"\r\n\r\n")
        self.assertEqual(req.code, 200)
        self.assertEqual(body, b"")

        self.assertEquals(2, len(logObserver))

    def test_noBytesResult(self):
        """
        When implemented C{render} method does not return bytes an internal
        server error is returned.
        """

        class RiggedRepr:
            def __repr__(self) -> str:
                return "my>repr"

        result = RiggedRepr()
        no_bytes_resource = resource.Resource()
        no_bytes_resource.render = lambda request: result
        request = self._getReq(no_bytes_resource)

        request.requestReceived(b"GET", b"/newrender", b"HTTP/1.0")

        headers, body = request.transport.written.getvalue().split(b"\r\n\r\n")
        self.assertEqual(request.code, 500)
        expected = [
            "",
            "<html>",
            "  <head><title>500 - Request did not return bytes</title></head>",
            "  <body>",
            "    <h1>Request did not return bytes</h1>",
            "    <p>Request: <pre>&lt;%s&gt;</pre><br />"
            "Resource: <pre>&lt;%s&gt;</pre><br />"
            "Value: <pre>my&gt;repr</pre></p>"
            % (
                reflect.safe_repr(request)[1:-1],
                reflect.safe_repr(no_bytes_resource)[1:-1],
            ),
            "  </body>",
            "</html>",
            "",
        ]
        self.assertEqual("\n".join(expected).encode("ascii"), body)


class GettableResource(resource.Resource):
    """
    Used by AllowedMethodsTests to simulate an allowed method.
    """

    def render_GET(self):
        pass

    def render_fred_render_ethel(self):
        """
        The unusual method name is designed to test the culling method
        in C{twisted.web.resource._computeAllowedMethods}.
        """
        pass


class AllowedMethodsTests(unittest.TestCase):
    """
    'C{twisted.web.resource._computeAllowedMethods} is provided by a
    default should the subclass not provide the method.
    """

    def _getReq(self):
        """
        Generate a dummy request for use by C{_computeAllowedMethod} tests.
        """
        d = DummyChannel()
        d.site.resource.putChild(b"gettableresource", GettableResource())
        d.transport.port = 81
        request = server.Request(d, 1)
        request.setHost(b"example.com", 81)
        request.gotLength(0)
        return request

    def test_computeAllowedMethods(self):
        """
        C{_computeAllowedMethods} will search through the
        'gettableresource' for all attributes/methods of the form
        'render_{method}' ('render_GET', for example) and return a list of
        the methods. 'HEAD' will always be included from the
        resource.Resource superclass.
        """
        res = GettableResource()
        allowedMethods = resource._computeAllowedMethods(res)
        self.assertEqual(set(allowedMethods), {b"GET", b"HEAD", b"fred_render_ethel"})

    def test_notAllowed(self):
        """
        When an unsupported method is requested, the default
        L{_computeAllowedMethods} method will be called to determine the
        allowed methods, and the HTTP 405 'Method Not Allowed' status will
        be returned with the allowed methods will be returned in the
        'Allow' header.
        """
        req = self._getReq()
        req.requestReceived(b"POST", b"/gettableresource", b"HTTP/1.0")
        self.assertEqual(req.code, 405)
        self.assertEqual(
            set(req.responseHeaders.getRawHeaders(b"allow")[0].split(b", ")),
            {b"GET", b"HEAD", b"fred_render_ethel"},
        )

    def test_notAllowedQuoting(self):
        """
        When an unsupported method response is generated, an HTML message will
        be displayed.  That message should include a quoted form of the URI and,
        since that value come from a browser and shouldn't necessarily be
        trusted.
        """
        req = self._getReq()
        req.requestReceived(
            b"POST", b"/gettableresource?" b"value=<script>bad", b"HTTP/1.0"
        )
        self.assertEqual(req.code, 405)
        renderedPage = req.transport.written.getvalue()
        self.assertNotIn(b"<script>bad", renderedPage)
        self.assertIn(b"&lt;script&gt;bad", renderedPage)

    def test_notImplementedQuoting(self):
        """
        When an not-implemented method response is generated, an HTML message
        will be displayed.  That message should include a quoted form of the
        requested method, since that value come from a browser and shouldn't
        necessarily be trusted.
        """
        req = self._getReq()
        req.requestReceived(b"<style>bad", b"/gettableresource", b"HTTP/1.0")
        self.assertEqual(req.code, 501)
        renderedPage = req.transport.written.getvalue()
        self.assertNotIn(b"<style>bad", renderedPage)
        self.assertIn(b"&lt;style&gt;bad", renderedPage)


class DummyRequestForLogTest(DummyRequest):
    uri = b"/dummy"  # parent class uri has "http://", which doesn't really happen
    code = 123

    clientproto = b"HTTP/1.0"
    sentLength = None
    client = IPv4Address("TCP", "1.2.3.4", 12345)

    def getClientIP(self):
        """
        As L{getClientIP} is deprecated, no log formatter should call it.
        """
        raise NotImplementedError(
            "Call to deprecated getClientIP method" " (use getClientAddress instead)"
        )


class AccessLogTestsMixin:
    """
    A mixin for L{TestCase} subclasses defining tests that apply to
    L{HTTPFactory} and its subclasses.
    """

    def factory(self, *args, **kwargs):
        """
        Get the factory class to apply logging tests to.

        Subclasses must override this method.
        """
        raise NotImplementedError("Subclass failed to override factory")

    def test_combinedLogFormat(self):
        """
        The factory's C{log} method writes a I{combined log format} line to the
        factory's log file.
        """
        reactor = Clock()
        # Set the clock to an arbitrary point in time.  It doesn't matter when
        # as long as it corresponds to the timestamp in the string literal in
        # the assertion below.
        reactor.advance(1234567890)

        logPath = self.mktemp()
        factory = self.factory(logPath=logPath, reactor=reactor)
        factory.startFactory()

        try:
            factory.log(DummyRequestForLogTest(factory))
        finally:
            factory.stopFactory()

        self.assertEqual(
            # Client IP
            b'"1.2.3.4" '
            # Some blanks we never fill in
            b"- - "
            # The current time (circa 1234567890)
            b"[13/Feb/2009:23:31:30 +0000] "
            # Method, URI, version
            b'"GET /dummy HTTP/1.0" '
            # Response code
            b"123 "
            # Response length
            b"- "
            # Value of the "Referer" header.  Probably incorrectly quoted.
            b'"-" '
            # Value pf the "User-Agent" header.  Probably incorrectly quoted.
            b'"-"\n',
            FilePath(logPath).getContent(),
        )

    def test_logFormatOverride(self):
        """
        If the factory is initialized with a custom log formatter then that
        formatter is used to generate lines for the log file.
        """

        def notVeryGoodFormatter(timestamp, request):
            return "this is a bad log format"

        reactor = Clock()
        reactor.advance(1234567890)

        logPath = self.mktemp()
        factory = self.factory(logPath=logPath, logFormatter=notVeryGoodFormatter)
        factory._reactor = reactor
        factory.startFactory()
        try:
            factory.log(DummyRequestForLogTest(factory))
        finally:
            factory.stopFactory()

        self.assertEqual(b"this is a bad log format\n", FilePath(logPath).getContent())


class HTTPFactoryAccessLogTests(AccessLogTestsMixin, unittest.TestCase):
    """
    Tests for L{http.HTTPFactory.log}.
    """

    factory = http.HTTPFactory


class SiteAccessLogTests(AccessLogTestsMixin, unittest.TestCase):
    """
    Tests for L{server.Site.log}.
    """

    def factory(self, *args, **kwargs):
        return server.Site(resource.Resource(), *args, **kwargs)


class CombinedLogFormatterTests(unittest.TestCase):
    """
    Tests for L{twisted.web.http.combinedLogFormatter}.
    """

    def test_interface(self):
        """
        L{combinedLogFormatter} provides L{IAccessLogFormatter}.
        """
        self.assertTrue(
            verifyObject(iweb.IAccessLogFormatter, http.combinedLogFormatter)
        )

    def test_nonASCII(self):
        """
        Bytes in fields of the request which are not part of ASCII are escaped
        in the result.
        """
        reactor = Clock()
        reactor.advance(1234567890)

        timestamp = http.datetimeToLogString(reactor.seconds())
        request = DummyRequestForLogTest(http.HTTPFactory(reactor=reactor))
        request.client = IPv4Address("TCP", b"evil x-forwarded-for \x80", 12345)
        request.method = b"POS\x81"
        request.protocol = b"HTTP/1.\x82"
        request.requestHeaders.addRawHeader(b"referer", b"evil \x83")
        request.requestHeaders.addRawHeader(b"user-agent", b"evil \x84")

        line = http.combinedLogFormatter(timestamp, request)
        self.assertEqual(
            '"evil x-forwarded-for \\x80" - - [13/Feb/2009:23:31:30 +0000] '
            '"POS\\x81 /dummy HTTP/1.0" 123 - "evil \\x83" "evil \\x84"',
            line,
        )

    def test_clientAddrIPv6(self):
        """
        A request from an IPv6 client is logged with that IP address.
        """
        reactor = Clock()
        reactor.advance(1234567890)

        timestamp = http.datetimeToLogString(reactor.seconds())
        request = DummyRequestForLogTest(http.HTTPFactory(reactor=reactor))
        request.client = IPv6Address("TCP", b"::1", 12345)

        line = http.combinedLogFormatter(timestamp, request)
        self.assertEqual(
            '"::1" - - [13/Feb/2009:23:31:30 +0000] '
            '"GET /dummy HTTP/1.0" 123 - "-" "-"',
            line,
        )

    def test_clientAddrUnknown(self):
        """
        A request made from an unknown address type is logged as C{"-"}.
        """

        @implementer(interfaces.IAddress)
        class UnknowableAddress:
            """
            An L{IAddress} which L{combinedLogFormatter} cannot have
            foreknowledge of.
            """

        reactor = Clock()
        reactor.advance(1234567890)

        timestamp = http.datetimeToLogString(reactor.seconds())
        request = DummyRequestForLogTest(http.HTTPFactory(reactor=reactor))
        request.client = UnknowableAddress()

        line = http.combinedLogFormatter(timestamp, request)
        self.assertTrue(line.startswith('"-" '))


class ProxiedLogFormatterTests(unittest.TestCase):
    """
    Tests for L{twisted.web.http.proxiedLogFormatter}.
    """

    def test_interface(self):
        """
        L{proxiedLogFormatter} provides L{IAccessLogFormatter}.
        """
        self.assertTrue(
            verifyObject(iweb.IAccessLogFormatter, http.proxiedLogFormatter)
        )

    def _xforwardedforTest(self, header):
        """
        Assert that a request with the given value in its I{X-Forwarded-For}
        header is logged by L{proxiedLogFormatter} the same way it would have
        been logged by L{combinedLogFormatter} but with 172.16.1.2 as the
        client address instead of the normal value.

        @param header: An I{X-Forwarded-For} header with left-most address of
            172.16.1.2.
        """
        reactor = Clock()
        reactor.advance(1234567890)

        timestamp = http.datetimeToLogString(reactor.seconds())
        request = DummyRequestForLogTest(http.HTTPFactory(reactor=reactor))
        expected = http.combinedLogFormatter(timestamp, request).replace(
            "1.2.3.4", "172.16.1.2"
        )
        request.requestHeaders.setRawHeaders(b"x-forwarded-for", [header])
        line = http.proxiedLogFormatter(timestamp, request)

        self.assertEqual(expected, line)

    def test_xforwardedfor(self):
        """
        L{proxiedLogFormatter} logs the value of the I{X-Forwarded-For} header
        in place of the client address field.
        """
        self._xforwardedforTest(b"172.16.1.2, 10.0.0.3, 192.168.1.4")

    def test_extraForwardedSpaces(self):
        """
        Any extra spaces around the address in the I{X-Forwarded-For} header
        are stripped and not included in the log string.
        """
        self._xforwardedforTest(b" 172.16.1.2 , 10.0.0.3, 192.168.1.4")


class LogEscapingTests(unittest.TestCase):
    def setUp(self):
        self.logPath = self.mktemp()
        self.site = http.HTTPFactory(self.logPath)
        self.site.startFactory()
        self.request = DummyRequestForLogTest(self.site, False)

    def assertLogs(self, line):
        """
        Assert that if C{self.request} is logged using C{self.site} then
        C{line} is written to the site's access log file.

        @param line: The expected line.
        @type line: L{bytes}

        @raise self.failureException: If the log file contains something other
            than the expected line.
        """
        try:
            self.site.log(self.request)
        finally:
            self.site.stopFactory()
        logged = FilePath(self.logPath).getContent()
        self.assertEqual(line, logged)

    def test_simple(self):
        """
        A I{GET} request is logged with no extra escapes.
        """
        self.site._logDateTime = "[%02d/%3s/%4d:%02d:%02d:%02d +0000]" % (
            25,
            "Oct",
            2004,
            12,
            31,
            59,
        )
        self.assertLogs(
            b'"1.2.3.4" - - [25/Oct/2004:12:31:59 +0000] '
            b'"GET /dummy HTTP/1.0" 123 - "-" "-"\n'
        )

    def test_methodQuote(self):
        """
        If the HTTP request method includes a quote, the quote is escaped.
        """
        self.site._logDateTime = "[%02d/%3s/%4d:%02d:%02d:%02d +0000]" % (
            25,
            "Oct",
            2004,
            12,
            31,
            59,
        )
        self.request.method = b'G"T'
        self.assertLogs(
            b'"1.2.3.4" - - [25/Oct/2004:12:31:59 +0000] '
            b'"G\\"T /dummy HTTP/1.0" 123 - "-" "-"\n'
        )

    def test_requestQuote(self):
        """
        If the HTTP request path includes a quote, the quote is escaped.
        """
        self.site._logDateTime = "[%02d/%3s/%4d:%02d:%02d:%02d +0000]" % (
            25,
            "Oct",
            2004,
            12,
            31,
            59,
        )
        self.request.uri = b'/dummy"withquote'
        self.assertLogs(
            b'"1.2.3.4" - - [25/Oct/2004:12:31:59 +0000] '
            b'"GET /dummy\\"withquote HTTP/1.0" 123 - "-" "-"\n'
        )

    def test_protoQuote(self):
        """
        If the HTTP request version includes a quote, the quote is escaped.
        """
        self.site._logDateTime = "[%02d/%3s/%4d:%02d:%02d:%02d +0000]" % (
            25,
            "Oct",
            2004,
            12,
            31,
            59,
        )
        self.request.clientproto = b'HT"P/1.0'
        self.assertLogs(
            b'"1.2.3.4" - - [25/Oct/2004:12:31:59 +0000] '
            b'"GET /dummy HT\\"P/1.0" 123 - "-" "-"\n'
        )

    def test_refererQuote(self):
        """
        If the value of the I{Referer} header contains a quote, the quote is
        escaped.
        """
        self.site._logDateTime = "[%02d/%3s/%4d:%02d:%02d:%02d +0000]" % (
            25,
            "Oct",
            2004,
            12,
            31,
            59,
        )
        self.request.requestHeaders.addRawHeader(
            b"referer", b'http://malicious" ".website.invalid'
        )
        self.assertLogs(
            b'"1.2.3.4" - - [25/Oct/2004:12:31:59 +0000] '
            b'"GET /dummy HTTP/1.0" 123 - '
            b'"http://malicious\\" \\".website.invalid" "-"\n'
        )

    def test_userAgentQuote(self):
        """
        If the value of the I{User-Agent} header contains a quote, the quote is
        escaped.
        """
        self.site._logDateTime = "[%02d/%3s/%4d:%02d:%02d:%02d +0000]" % (
            25,
            "Oct",
            2004,
            12,
            31,
            59,
        )
        self.request.requestHeaders.addRawHeader(b"user-agent", b'Malicious Web" Evil')
        self.assertLogs(
            b'"1.2.3.4" - - [25/Oct/2004:12:31:59 +0000] '
            b'"GET /dummy HTTP/1.0" 123 - "-" "Malicious Web\\" Evil"\n'
        )


class ServerAttributesTests(unittest.TestCase):
    """
    Tests that deprecated twisted.web.server attributes raise the appropriate
    deprecation warnings when used.
    """

    def test_deprecatedAttributeDateTimeString(self):
        """
        twisted.web.server.date_time_string should not be used; instead use
        twisted.web.http.datetimeToString directly
        """
        server.date_time_string
        warnings = self.flushWarnings(
            offendingFunctions=[self.test_deprecatedAttributeDateTimeString]
        )

        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0]["category"], DeprecationWarning)
        self.assertEqual(
            warnings[0]["message"],
            (
                "twisted.web.server.date_time_string was deprecated in Twisted "
                "12.1.0: Please use twisted.web.http.datetimeToString instead"
            ),
        )

    def test_deprecatedAttributeStringDateTime(self):
        """
        twisted.web.server.string_date_time should not be used; instead use
        twisted.web.http.stringToDatetime directly
        """
        server.string_date_time
        warnings = self.flushWarnings(
            offendingFunctions=[self.test_deprecatedAttributeStringDateTime]
        )

        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0]["category"], DeprecationWarning)
        self.assertEqual(
            warnings[0]["message"],
            (
                "twisted.web.server.string_date_time was deprecated in Twisted "
                "12.1.0: Please use twisted.web.http.stringToDatetime instead"
            ),
        )


class ExplicitHTTPFactoryReactor(unittest.TestCase):
    """
    L{http.HTTPFactory} accepts explicit reactor selection.
    """

    def test_explicitReactor(self):
        """
        L{http.HTTPFactory.__init__} accepts a reactor argument which is set on
        L{http.HTTPFactory.reactor}.
        """
        reactor = "I am a reactor!"
        factory = http.HTTPFactory(reactor=reactor)
        self.assertIs(factory.reactor, reactor)

    def test_defaultReactor(self):
        """
        Giving no reactor argument to L{http.HTTPFactory.__init__} means it
        will select the global reactor.
        """
        from twisted.internet import reactor

        factory = http.HTTPFactory()
        self.assertIs(factory.reactor, reactor)
