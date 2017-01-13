# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.web.wsgi}.
"""

__metaclass__ = type

from sys import exc_info
import tempfile
import traceback
import warnings

from zope.interface.verify import verifyObject

from twisted.python.compat import intToBytes, urlquote, _PY3
from twisted.python.log import addObserver, removeObserver, err
from twisted.python.failure import Failure
from twisted.python.threadable import getThreadID
from twisted.python.threadpool import ThreadPool
from twisted.internet.defer import Deferred, gatherResults
from twisted.internet import reactor
from twisted.internet.error import ConnectionLost
from twisted.trial.unittest import TestCase, SkipTest
from twisted.web import http
from twisted.web.resource import IResource, Resource
from twisted.web.server import Request, Site, version
from twisted.web.wsgi import WSGIResource
from twisted.web.test.test_web import DummyChannel



class SynchronousThreadPool:
    """
    A single-threaded implementation of part of the L{ThreadPool} interface.
    This implementation calls functions synchronously rather than running
    them in a thread pool.  It is used to make the tests which are not
    directly for thread-related behavior deterministic.
    """
    def callInThread(self, f, *a, **kw):
        """
        Call C{f(*a, **kw)} in this thread rather than scheduling it to be
        called in a thread.
        """
        try:
            f(*a, **kw)
        except:
            # callInThread doesn't let exceptions propagate to the caller.
            # None is always returned and any exception raised gets logged
            # later on.
            err(None, "Callable passed to SynchronousThreadPool.callInThread failed")



class SynchronousReactorThreads:
    """
    A single-threaded implementation of part of the L{IReactorThreads}
    interface.  This implementation assumes that it will only be invoked
    from the reactor thread, so it calls functions synchronously rather than
    trying to schedule them to run in the reactor thread.  It is used in
    conjunction with L{SynchronousThreadPool} to make the tests which are
    not directly for thread-related behavior deterministic.
    """
    def callFromThread(self, f, *a, **kw):
        """
        Call C{f(*a, **kw)} in this thread which should also be the reactor
        thread.
        """
        f(*a, **kw)



class WSGIResourceTests(TestCase):
    def setUp(self):
        """
        Create a L{WSGIResource} with synchronous threading objects and a no-op
        application object.  This is useful for testing certain things about
        the resource implementation which are unrelated to WSGI.
        """
        self.resource = WSGIResource(
            SynchronousReactorThreads(), SynchronousThreadPool(),
            lambda environ, startResponse: None)


    def test_interfaces(self):
        """
        L{WSGIResource} implements L{IResource} and stops resource traversal.
        """
        verifyObject(IResource, self.resource)
        self.assertTrue(self.resource.isLeaf)


    def test_unsupported(self):
        """
        A L{WSGIResource} cannot have L{IResource} children.  Its
        C{getChildWithDefault} and C{putChild} methods raise L{RuntimeError}.
        """
        self.assertRaises(
            RuntimeError,
            self.resource.getChildWithDefault,
            b"foo", Request(DummyChannel(), False))
        self.assertRaises(
            RuntimeError,
            self.resource.putChild,
            b"foo", Resource())


class WSGITestsMixin:
    """
    @ivar channelFactory: A no-argument callable which will be invoked to
        create a new HTTP channel to associate with request objects.
    """
    channelFactory = DummyChannel

    def setUp(self):
        self.threadpool = SynchronousThreadPool()
        self.reactor = SynchronousReactorThreads()


    def lowLevelRender(
        self, requestFactory, applicationFactory, channelFactory, method,
        version, resourceSegments, requestSegments, query=None, headers=[],
        body=None, safe=''):
        """
        @param method: A C{str} giving the request method to use.

        @param version: A C{str} like C{'1.1'} giving the request version.

        @param resourceSegments: A C{list} of unencoded path segments which
            specifies the location in the resource hierarchy at which the
            L{WSGIResource} will be placed, eg C{['']} for I{/}, C{['foo',
            'bar', '']} for I{/foo/bar/}, etc.

        @param requestSegments: A C{list} of unencoded path segments giving the
            request URI.

        @param query: A C{list} of two-tuples of C{str} giving unencoded query
            argument keys and values.

        @param headers: A C{list} of two-tuples of C{str} giving request header
            names and corresponding values.

        @param safe: A C{str} giving the bytes which are to be considered
            I{safe} for inclusion in the request URI and not quoted.

        @return: A L{Deferred} which will be called back with a two-tuple of
            the arguments passed which would be passed to the WSGI application
            object for this configuration and request (ie, the environment and
            start_response callable).
        """
        def _toByteString(string):
            # Twisted's HTTP implementation prefers byte strings. As a
            # convenience for tests, string arguments are encoded to an
            # ISO-8859-1 byte string (if not already) before being passed on.
            if isinstance(string, bytes):
                return string
            else:
                return string.encode('iso-8859-1')

        root = WSGIResource(
            self.reactor, self.threadpool, applicationFactory())
        resourceSegments.reverse()
        for seg in resourceSegments:
            tmp = Resource()
            tmp.putChild(_toByteString(seg), root)
            root = tmp

        channel = channelFactory()
        channel.site = Site(root)
        request = requestFactory(channel, False)
        for k, v in headers:
            request.requestHeaders.addRawHeader(
                _toByteString(k), _toByteString(v))
        request.gotLength(0)
        if body:
            request.content.write(body)
            request.content.seek(0)
        uri = '/' + '/'.join([urlquote(seg, safe) for seg in requestSegments])
        if query is not None:
            uri += '?' + '&'.join(['='.join([urlquote(k, safe), urlquote(v, safe)])
                                   for (k, v) in query])
        request.requestReceived(
            _toByteString(method), _toByteString(uri),
            b'HTTP/' + _toByteString(version))
        return request


    def render(self, *a, **kw):
        result = Deferred()
        def applicationFactory():
            def application(*args):
                environ, startResponse = args
                result.callback(args)
                startResponse('200 OK', [])
                return iter(())
            return application
        self.lowLevelRender(
            Request, applicationFactory, self.channelFactory, *a, **kw)
        return result


    def requestFactoryFactory(self, requestClass=Request):
        d = Deferred()
        def requestFactory(*a, **kw):
            request = requestClass(*a, **kw)
            # If notifyFinish is called after lowLevelRender returns, it won't
            # do the right thing, because the request will have already
            # finished.  One might argue that this is a bug in
            # Request.notifyFinish.
            request.notifyFinish().chainDeferred(d)
            return request
        return d, requestFactory


    def getContentFromResponse(self, response):
        return response.split(b'\r\n\r\n', 1)[1]


    def prepareRequest(self, application=None):
        """
        Prepare a L{Request} which, when a request is received, captures the
        C{environ} and C{start_response} callable passed to a WSGI app.

        @param application: An optional WSGI application callable that accepts
            the familiar C{environ} and C{start_response} args and returns an
            iterable of body content. If not supplied, C{start_response} will
            be called with a "200 OK" status and no headers, and no content
            will be yielded.

        @return: A two-tuple of (C{request}, C{deferred}). The former is a
            Twisted L{Request}. The latter is a L{Deferred} which will be
            called back with a two-tuple of the arguments passed to a WSGI
            application (i.e. the C{environ} and C{start_response} callable),
            or will errback with any error arising within the WSGI app.
        """
        result = Deferred()

        def outerApplication(environ, startResponse):
            try:
                if application is None:
                    startResponse('200 OK', [])
                    content = iter(())  # No content.
                else:
                    content = application(environ, startResponse)
            except:
                result.errback()
                startResponse('500 Error', [])
                return iter(())
            else:
                result.callback((environ, startResponse))
                return content

        resource = WSGIResource(
            self.reactor, self.threadpool, outerApplication)

        root = Resource()
        root.putChild(b"res", resource)

        channel = self.channelFactory()
        channel.site = Site(root)

        class CannedRequest(Request):
            """
            Convenient L{Request} derivative which has canned values for all
            of C{requestReceived}'s arguments.
            """
            def requestReceived(
                    self, command=b"GET", path=b"/res", version=b"1.1"):
                return Request.requestReceived(
                    self, command=command, path=path, version=version)

        request = CannedRequest(channel, queued=False)
        request.gotLength(0)  # Initialize buffer for request body.

        return request, result



class EnvironTests(WSGITestsMixin, TestCase):
    """
    Tests for the values in the C{environ} C{dict} passed to the application
    object by L{twisted.web.wsgi.WSGIResource}.
    """
    def environKeyEqual(self, key, value):
        def assertEnvironKeyEqual(result):
            environ, startResponse = result
            self.assertEqual(environ[key], value)
            return value
        return assertEnvironKeyEqual


    def test_environIsDict(self):
        """
        L{WSGIResource} calls the application object with an C{environ}
        parameter which is exactly of type C{dict}.
        """
        d = self.render('GET', '1.1', [], [''])
        def cbRendered(result):
            environ, startResponse = result
            self.assertIdentical(type(environ), dict)
            # Environment keys are always native strings.
            for name in environ:
                self.assertIsInstance(name, str)
        d.addCallback(cbRendered)
        return d


    def test_requestMethod(self):
        """
        The C{'REQUEST_METHOD'} key of the C{environ} C{dict} passed to the
        application contains the HTTP method in the request (RFC 3875, section
        4.1.12).
        """
        get = self.render('GET', '1.1', [], [''])
        get.addCallback(self.environKeyEqual('REQUEST_METHOD', 'GET'))

        # Also make sure a different request method shows up as a different
        # value in the environ dict.
        post = self.render('POST', '1.1', [], [''])
        post.addCallback(self.environKeyEqual('REQUEST_METHOD', 'POST'))

        return gatherResults([get, post])


    def test_requestMethodIsNativeString(self):
        """
        The C{'REQUEST_METHOD'} key of the C{environ} C{dict} passed to the
        application is always a native string.
        """
        for method in b"GET", u"GET":
            request, result = self.prepareRequest()
            request.requestReceived(method)
            result.addCallback(self.environKeyEqual('REQUEST_METHOD', 'GET'))
            self.assertIsInstance(self.successResultOf(result), str)


    def test_scriptName(self):
        """
        The C{'SCRIPT_NAME'} key of the C{environ} C{dict} passed to the
        application contains the I{abs_path} (RFC 2396, section 3) to this
        resource (RFC 3875, section 4.1.13).
        """
        root = self.render('GET', '1.1', [], [''])
        root.addCallback(self.environKeyEqual('SCRIPT_NAME', ''))

        emptyChild = self.render('GET', '1.1', [''], [''])
        emptyChild.addCallback(self.environKeyEqual('SCRIPT_NAME', '/'))

        leaf = self.render('GET', '1.1', ['foo'], ['foo'])
        leaf.addCallback(self.environKeyEqual('SCRIPT_NAME', '/foo'))

        container = self.render('GET', '1.1', ['foo', ''], ['foo', ''])
        container.addCallback(self.environKeyEqual('SCRIPT_NAME', '/foo/'))

        internal = self.render('GET', '1.1', ['foo'], ['foo', 'bar'])
        internal.addCallback(self.environKeyEqual('SCRIPT_NAME', '/foo'))

        unencoded = self.render(
            'GET', '1.1', ['foo', '/', b'bar\xff'], ['foo', '/', b'bar\xff'])
        # The RFC says "(not URL-encoded)", even though that makes
        # interpretation of SCRIPT_NAME ambiguous.
        unencoded.addCallback(
            self.environKeyEqual('SCRIPT_NAME', '/foo///bar\xff'))

        return gatherResults([
                root, emptyChild, leaf, container, internal, unencoded])


    def test_scriptNameIsNativeString(self):
        """
        The C{'SCRIPT_NAME'} key of the C{environ} C{dict} passed to the
        application is always a native string.
        """
        request, result = self.prepareRequest()
        request.requestReceived(path=b"/res")
        result.addCallback(self.environKeyEqual('SCRIPT_NAME', '/res'))
        self.assertIsInstance(self.successResultOf(result), str)

        if _PY3:
            # Native strings are rejected by Request.requestReceived() before
            # t.w.wsgi has any say in the matter.
            request, result = self.prepareRequest()
            self.assertRaises(TypeError, request.requestReceived, path=u"/res")
        else:
            request, result = self.prepareRequest()
            request.requestReceived(path=u"/res")
            result.addCallback(self.environKeyEqual('SCRIPT_NAME', '/res'))
            self.assertIsInstance(self.successResultOf(result), str)


    def test_pathInfo(self):
        """
        The C{'PATH_INFO'} key of the C{environ} C{dict} passed to the
        application contains the suffix of the request URI path which is not
        included in the value for the C{'SCRIPT_NAME'} key (RFC 3875, section
        4.1.5).
        """
        assertKeyEmpty = self.environKeyEqual('PATH_INFO', '')

        root = self.render('GET', '1.1', [], [''])
        root.addCallback(self.environKeyEqual('PATH_INFO', '/'))

        emptyChild = self.render('GET', '1.1', [''], [''])
        emptyChild.addCallback(assertKeyEmpty)

        leaf = self.render('GET', '1.1', ['foo'], ['foo'])
        leaf.addCallback(assertKeyEmpty)

        container = self.render('GET', '1.1', ['foo', ''], ['foo', ''])
        container.addCallback(assertKeyEmpty)

        internalLeaf = self.render('GET', '1.1', ['foo'], ['foo', 'bar'])
        internalLeaf.addCallback(self.environKeyEqual('PATH_INFO', '/bar'))

        internalContainer = self.render('GET', '1.1', ['foo'], ['foo', ''])
        internalContainer.addCallback(self.environKeyEqual('PATH_INFO', '/'))

        unencoded = self.render('GET', '1.1', [], ['foo', '/', b'bar\xff'])
        unencoded.addCallback(
            self.environKeyEqual('PATH_INFO', '/foo///bar\xff'))

        return gatherResults([
                root, leaf, container, internalLeaf,
                internalContainer, unencoded])


    def test_pathInfoIsNativeString(self):
        """
        The C{'PATH_INFO'} key of the C{environ} C{dict} passed to the
        application is always a native string.
        """
        request, result = self.prepareRequest()
        request.requestReceived(path=b"/res/foo/bar")
        result.addCallback(self.environKeyEqual('PATH_INFO', '/foo/bar'))
        self.assertIsInstance(self.successResultOf(result), str)

        if _PY3:
            # Native strings are rejected by Request.requestReceived() before
            # t.w.wsgi has any say in the matter.
            request, result = self.prepareRequest()
            self.assertRaises(
                TypeError, request.requestReceived, path=u"/res/foo/bar")
        else:
            request, result = self.prepareRequest()
            request.requestReceived(path=u"/res/foo/bar")
            result.addCallback(self.environKeyEqual('PATH_INFO', '/foo/bar'))
            self.assertIsInstance(self.successResultOf(result), str)


    def test_queryString(self):
        """
        The C{'QUERY_STRING'} key of the C{environ} C{dict} passed to the
        application contains the portion of the request URI after the first
        I{?} (RFC 3875, section 4.1.7).
        """
        missing = self.render('GET', '1.1', [], [''], None)
        missing.addCallback(self.environKeyEqual('QUERY_STRING', ''))

        empty = self.render('GET', '1.1', [], [''], [])
        empty.addCallback(self.environKeyEqual('QUERY_STRING', ''))

        present = self.render('GET', '1.1', [], [''], [('foo', 'bar')])
        present.addCallback(self.environKeyEqual('QUERY_STRING', 'foo=bar'))

        unencoded = self.render('GET', '1.1', [], [''], [('/', '/')])
        unencoded.addCallback(self.environKeyEqual('QUERY_STRING', '%2F=%2F'))

        # "?" is reserved in the <searchpart> portion of a URL.  However, it
        # seems to be a common mistake of clients to forget to quote it.  So,
        # make sure we handle that invalid case.
        doubleQuestion = self.render(
            'GET', '1.1', [], [''], [('foo', '?bar')], safe='?')
        doubleQuestion.addCallback(
            self.environKeyEqual('QUERY_STRING', 'foo=?bar'))

        return gatherResults([
            missing, empty, present, unencoded, doubleQuestion])


    def test_queryStringIsNativeString(self):
        """
        The C{'QUERY_STRING'} key of the C{environ} C{dict} passed to the
        application is always a native string.
        """
        request, result = self.prepareRequest()
        request.requestReceived(path=b"/res?foo=bar")
        result.addCallback(self.environKeyEqual('QUERY_STRING', 'foo=bar'))
        self.assertIsInstance(self.successResultOf(result), str)

        if _PY3:
            # Native strings are rejected by Request.requestReceived() before
            # t.w.wsgi has any say in the matter.
            request, result = self.prepareRequest()
            self.assertRaises(
                TypeError, request.requestReceived, path=u"/res?foo=bar")
        else:
            request, result = self.prepareRequest()
            request.requestReceived(path=u"/res?foo=bar")
            result.addCallback(self.environKeyEqual('QUERY_STRING', 'foo=bar'))
            self.assertIsInstance(self.successResultOf(result), str)


    def test_contentType(self):
        """
        The C{'CONTENT_TYPE'} key of the C{environ} C{dict} passed to the
        application contains the value of the I{Content-Type} request header
        (RFC 3875, section 4.1.3).
        """
        missing = self.render('GET', '1.1', [], [''])
        missing.addCallback(self.environKeyEqual('CONTENT_TYPE', ''))

        present = self.render(
            'GET', '1.1', [], [''], None, [('content-type', 'x-foo/bar')])
        present.addCallback(self.environKeyEqual('CONTENT_TYPE', 'x-foo/bar'))

        return gatherResults([missing, present])


    def test_contentTypeIsNativeString(self):
        """
        The C{'CONTENT_TYPE'} key of the C{environ} C{dict} passed to the
        application is always a native string.
        """
        for contentType in b"x-foo/bar", u"x-foo/bar":
            request, result = self.prepareRequest()
            request.requestHeaders.addRawHeader(b"Content-Type", contentType)
            request.requestReceived()
            result.addCallback(self.environKeyEqual('CONTENT_TYPE', 'x-foo/bar'))
            self.assertIsInstance(self.successResultOf(result), str)


    def test_contentLength(self):
        """
        The C{'CONTENT_LENGTH'} key of the C{environ} C{dict} passed to the
        application contains the value of the I{Content-Length} request header
        (RFC 3875, section 4.1.2).
        """
        missing = self.render('GET', '1.1', [], [''])
        missing.addCallback(self.environKeyEqual('CONTENT_LENGTH', ''))

        present = self.render(
            'GET', '1.1', [], [''], None, [('content-length', '1234')])
        present.addCallback(self.environKeyEqual('CONTENT_LENGTH', '1234'))

        return gatherResults([missing, present])


    def test_contentLengthIsNativeString(self):
        """
        The C{'CONTENT_LENGTH'} key of the C{environ} C{dict} passed to the
        application is always a native string.
        """
        for contentLength in b"1234", u"1234":
            request, result = self.prepareRequest()
            request.requestHeaders.addRawHeader(b"Content-Length", contentLength)
            request.requestReceived()
            result.addCallback(self.environKeyEqual('CONTENT_LENGTH', '1234'))
            self.assertIsInstance(self.successResultOf(result), str)


    def test_serverName(self):
        """
        The C{'SERVER_NAME'} key of the C{environ} C{dict} passed to the
        application contains the best determination of the server hostname
        possible, using either the value of the I{Host} header in the request
        or the address the server is listening on if that header is not
        present (RFC 3875, section 4.1.14).
        """
        missing = self.render('GET', '1.1', [], [''])
        # 10.0.0.1 value comes from a bit far away -
        # twisted.test.test_web.DummyChannel.transport.getHost().host
        missing.addCallback(self.environKeyEqual('SERVER_NAME', '10.0.0.1'))

        present = self.render(
            'GET', '1.1', [], [''], None, [('host', 'example.org')])
        present.addCallback(self.environKeyEqual('SERVER_NAME', 'example.org'))

        return gatherResults([missing, present])


    def test_serverNameIsNativeString(self):
        """
        The C{'SERVER_NAME'} key of the C{environ} C{dict} passed to the
        application is always a native string.
        """
        for serverName in b"host.example.com", u"host.example.com":
            request, result = self.prepareRequest()
            # This is kind of a cheat; getRequestHostname() breaks in Python 3
            # when the "Host" request header is set to a native string because
            # it tries to split around b":", so we patch the method.
            request.getRequestHostname = lambda: serverName
            request.requestReceived()
            result.addCallback(self.environKeyEqual('SERVER_NAME', 'host.example.com'))
            self.assertIsInstance(self.successResultOf(result), str)


    def test_serverPort(self):
        """
        The C{'SERVER_PORT'} key of the C{environ} C{dict} passed to the
        application contains the port number of the server which received the
        request (RFC 3875, section 4.1.15).
        """
        portNumber = 12354
        def makeChannel():
            channel = DummyChannel()
            channel.transport = DummyChannel.TCP()
            channel.transport.port = portNumber
            return channel
        self.channelFactory = makeChannel

        d = self.render('GET', '1.1', [], [''])
        d.addCallback(self.environKeyEqual('SERVER_PORT', str(portNumber)))
        return d


    def test_serverPortIsNativeString(self):
        """
        The C{'SERVER_PORT'} key of the C{environ} C{dict} passed to the
        application is always a native string.
        """
        request, result = self.prepareRequest()
        request.requestReceived()
        result.addCallback(self.environKeyEqual('SERVER_PORT', '80'))
        self.assertIsInstance(self.successResultOf(result), str)


    def test_serverProtocol(self):
        """
        The C{'SERVER_PROTOCOL'} key of the C{environ} C{dict} passed to the
        application contains the HTTP version number received in the request
        (RFC 3875, section 4.1.16).
        """
        old = self.render('GET', '1.0', [], [''])
        old.addCallback(self.environKeyEqual('SERVER_PROTOCOL', 'HTTP/1.0'))

        new = self.render('GET', '1.1', [], [''])
        new.addCallback(self.environKeyEqual('SERVER_PROTOCOL', 'HTTP/1.1'))

        return gatherResults([old, new])


    def test_serverProtocolIsNativeString(self):
        """
        The C{'SERVER_PROTOCOL'} key of the C{environ} C{dict} passed to the
        application is always a native string.
        """
        for serverProtocol in b"1.1", u"1.1":
            request, result = self.prepareRequest()
            # In Python 3, native strings can be rejected by Request.write()
            # which will cause a crash after the bit we're trying to test, so
            # we patch write() out here to do nothing.
            request.write = lambda data: None
            request.requestReceived(version=b"1.1")
            result.addCallback(self.environKeyEqual('SERVER_PROTOCOL', '1.1'))
            self.assertIsInstance(self.successResultOf(result), str)


    def test_remoteAddr(self):
        """
        The C{'REMOTE_ADDR'} key of the C{environ} C{dict} passed to the
        application contains the address of the client making the request.
        """
        d = self.render('GET', '1.1', [], [''])
        d.addCallback(self.environKeyEqual('REMOTE_ADDR', '192.168.1.1'))

        return d

    def test_headers(self):
        """
        HTTP request headers are copied into the C{environ} C{dict} passed to
        the application with a C{HTTP_} prefix added to their names.
        """
        singleValue = self.render(
            'GET', '1.1', [], [''], None, [('foo', 'bar'), ('baz', 'quux')])
        def cbRendered(result):
            environ, startResponse = result
            self.assertEqual(environ['HTTP_FOO'], 'bar')
            self.assertEqual(environ['HTTP_BAZ'], 'quux')
        singleValue.addCallback(cbRendered)

        multiValue = self.render(
            'GET', '1.1', [], [''], None, [('foo', 'bar'), ('foo', 'baz')])
        multiValue.addCallback(self.environKeyEqual('HTTP_FOO', 'bar,baz'))

        withHyphen = self.render(
            'GET', '1.1', [], [''], None, [('foo-bar', 'baz')])
        withHyphen.addCallback(self.environKeyEqual('HTTP_FOO_BAR', 'baz'))

        multiLine = self.render(
            'GET', '1.1', [], [''], None, [('foo', 'bar\n\tbaz')])
        multiLine.addCallback(self.environKeyEqual('HTTP_FOO', 'bar \tbaz'))

        return gatherResults([singleValue, multiValue, withHyphen, multiLine])


    def test_wsgiVersion(self):
        """
        The C{'wsgi.version'} key of the C{environ} C{dict} passed to the
        application has the value C{(1, 0)} indicating that this is a WSGI 1.0
        container.
        """
        versionDeferred = self.render('GET', '1.1', [], [''])
        versionDeferred.addCallback(self.environKeyEqual('wsgi.version', (1, 0)))
        return versionDeferred


    def test_wsgiRunOnce(self):
        """
        The C{'wsgi.run_once'} key of the C{environ} C{dict} passed to the
        application is set to C{False}.
        """
        once = self.render('GET', '1.1', [], [''])
        once.addCallback(self.environKeyEqual('wsgi.run_once', False))
        return once


    def test_wsgiMultithread(self):
        """
        The C{'wsgi.multithread'} key of the C{environ} C{dict} passed to the
        application is set to C{True}.
        """
        thread = self.render('GET', '1.1', [], [''])
        thread.addCallback(self.environKeyEqual('wsgi.multithread', True))
        return thread


    def test_wsgiMultiprocess(self):
        """
        The C{'wsgi.multiprocess'} key of the C{environ} C{dict} passed to the
        application is set to C{False}.
        """
        process = self.render('GET', '1.1', [], [''])
        process.addCallback(self.environKeyEqual('wsgi.multiprocess', False))
        return process


    def test_wsgiURLScheme(self):
        """
        The C{'wsgi.url_scheme'} key of the C{environ} C{dict} passed to the
        application has the request URL scheme.
        """
        # XXX Does this need to be different if the request is for an absolute
        # URL?
        def channelFactory():
            channel = DummyChannel()
            channel.transport = DummyChannel.SSL()
            return channel

        self.channelFactory = DummyChannel
        httpDeferred = self.render('GET', '1.1', [], [''])
        httpDeferred.addCallback(self.environKeyEqual('wsgi.url_scheme', 'http'))

        self.channelFactory = channelFactory
        httpsDeferred = self.render('GET', '1.1', [], [''])
        httpsDeferred.addCallback(self.environKeyEqual('wsgi.url_scheme', 'https'))

        return gatherResults([httpDeferred, httpsDeferred])


    def test_wsgiErrors(self):
        """
        The C{'wsgi.errors'} key of the C{environ} C{dict} passed to the
        application is a file-like object (as defined in the U{Input and Errors
        Streams<http://www.python.org/dev/peps/pep-0333/#input-and-error-streams>}
        section of PEP 333) which converts bytes written to it into events for
        the logging system.
        """
        events = []
        addObserver(events.append)
        self.addCleanup(removeObserver, events.append)

        errors = self.render('GET', '1.1', [], [''])
        def cbErrors(result):
            environ, startApplication = result
            errors = environ['wsgi.errors']
            errors.write('some message\n')
            errors.writelines(['another\nmessage\n'])
            errors.flush()
            self.assertEqual(events[0]['message'], ('some message\n',))
            self.assertEqual(events[0]['system'], 'wsgi')
            self.assertTrue(events[0]['isError'])
            self.assertEqual(events[1]['message'], ('another\nmessage\n',))
            self.assertEqual(events[1]['system'], 'wsgi')
            self.assertTrue(events[1]['isError'])
            self.assertEqual(len(events), 2)
        errors.addCallback(cbErrors)
        return errors


    def test_wsgiErrorsExpectsOnlyNativeStringsInPython2(self):
        """
        The C{'wsgi.errors'} file-like object from the C{environ} C{dict}
        expects writes of only native strings in Python 2. Some existing WSGI
        applications may write non-native (i.e. C{unicode}) strings so, for
        compatibility, these elicit only a warning in Python 2.
        """
        if _PY3:
            raise SkipTest("Not relevant in Python 3")

        request, result = self.prepareRequest()
        request.requestReceived()
        environ, _ = self.successResultOf(result)
        errors = environ["wsgi.errors"]

        with warnings.catch_warnings(record=True) as caught:
            errors.write(u"fred")
        self.assertEqual(1, len(caught))
        self.assertEqual(UnicodeWarning, caught[0].category)
        self.assertEqual(
            "write() argument should be str, not u'fred' (unicode)",
            str(caught[0].message))


    def test_wsgiErrorsAcceptsOnlyNativeStringsInPython3(self):
        """
        The C{'wsgi.errors'} file-like object from the C{environ} C{dict}
        permits writes of only native strings in Python 3, and raises
        C{TypeError} for writes of non-native strings.
        """
        if not _PY3:
            raise SkipTest("Relevant only in Python 3")

        request, result = self.prepareRequest()
        request.requestReceived()
        environ, _ = self.successResultOf(result)
        errors = environ["wsgi.errors"]

        error = self.assertRaises(TypeError, errors.write, b"fred")
        self.assertEqual(
            "write() argument must be str, not b'fred' (bytes)",
            str(error))



class InputStreamTestMixin(WSGITestsMixin):
    """
    A mixin for L{TestCase} subclasses which defines a number of tests against
    L{_InputStream}.  The subclass is expected to create a file-like object to
    be wrapped by an L{_InputStream} under test.
    """
    def getFileType(self):
        raise NotImplementedError(
            "%s.getFile must be implemented" % (self.__class__.__name__,))


    def _renderAndReturnReaderResult(self, reader, content):
        contentType = self.getFileType()
        class CustomizedRequest(Request):
            def gotLength(self, length):
                # Always allocate a file of the specified type, instead of
                # using the base behavior of selecting one depending on the
                # length.
                self.content = contentType()

        def appFactoryFactory(reader):
            result = Deferred()
            def applicationFactory():
                def application(*args):
                    environ, startResponse = args
                    result.callback(reader(environ['wsgi.input']))
                    startResponse('200 OK', [])
                    return iter(())
                return application
            return result, applicationFactory
        d, appFactory = appFactoryFactory(reader)
        self.lowLevelRender(
            CustomizedRequest, appFactory, DummyChannel,
            'PUT', '1.1', [], [''], None, [],
            content)
        return d


    def test_readAll(self):
        """
        Calling L{_InputStream.read} with no arguments returns the entire input
        stream.
        """
        bytes = b"some bytes are here"
        d = self._renderAndReturnReaderResult(lambda input: input.read(), bytes)
        d.addCallback(self.assertEqual, bytes)
        return d


    def test_readSome(self):
        """
        Calling L{_InputStream.read} with an integer returns that many bytes
        from the input stream, as long as it is less than or equal to the total
        number of bytes available.
        """
        bytes = b"hello, world."
        d = self._renderAndReturnReaderResult(lambda input: input.read(3), bytes)
        d.addCallback(self.assertEqual, b"hel")
        return d


    def test_readMoreThan(self):
        """
        Calling L{_InputStream.read} with an integer that is greater than the
        total number of bytes in the input stream returns all bytes in the
        input stream.
        """
        bytes = b"some bytes are here"
        d = self._renderAndReturnReaderResult(
            lambda input: input.read(len(bytes) + 3), bytes)
        d.addCallback(self.assertEqual, bytes)
        return d


    def test_readTwice(self):
        """
        Calling L{_InputStream.read} a second time returns bytes starting from
        the position after the last byte returned by the previous read.
        """
        bytes = b"some bytes, hello"
        def read(input):
            input.read(3)
            return input.read()
        d = self._renderAndReturnReaderResult(read, bytes)
        d.addCallback(self.assertEqual, bytes[3:])
        return d


    def test_readNone(self):
        """
        Calling L{_InputStream.read} with L{None} as an argument returns all
        bytes in the input stream.
        """
        bytes = b"the entire stream"
        d = self._renderAndReturnReaderResult(
            lambda input: input.read(None), bytes)
        d.addCallback(self.assertEqual, bytes)
        return d


    def test_readNegative(self):
        """
        Calling L{_InputStream.read} with a negative integer as an argument
        returns all bytes in the input stream.
        """
        bytes = b"all of the input"
        d = self._renderAndReturnReaderResult(
            lambda input: input.read(-1), bytes)
        d.addCallback(self.assertEqual, bytes)
        return d


    def test_readline(self):
        """
        Calling L{_InputStream.readline} with no argument returns one line from
        the input stream.
        """
        bytes = b"hello\nworld"
        d = self._renderAndReturnReaderResult(
            lambda input: input.readline(), bytes)
        d.addCallback(self.assertEqual, b"hello\n")
        return d


    def test_readlineSome(self):
        """
        Calling L{_InputStream.readline} with an integer returns at most that
        many bytes, even if it is not enough to make up a complete line.

        COMPATIBILITY NOTE: the size argument is excluded from the WSGI
        specification, but is provided here anyhow, because useful libraries
        such as python stdlib's cgi.py assume their input file-like-object
        supports readline with a size argument. If you use it, be aware your
        application may not be portable to other conformant WSGI servers.
        """
        bytes = b"goodbye\nworld"
        d = self._renderAndReturnReaderResult(
            lambda input: input.readline(3), bytes)
        d.addCallback(self.assertEqual, b"goo")
        return d


    def test_readlineMoreThan(self):
        """
        Calling L{_InputStream.readline} with an integer which is greater than
        the number of bytes in the next line returns only the next line.
        """
        bytes = b"some lines\nof text"
        d = self._renderAndReturnReaderResult(
            lambda input: input.readline(20), bytes)
        d.addCallback(self.assertEqual, b"some lines\n")
        return d


    def test_readlineTwice(self):
        """
        Calling L{_InputStream.readline} a second time returns the line
        following the line returned by the first call.
        """
        bytes = b"first line\nsecond line\nlast line"
        def readline(input):
            input.readline()
            return input.readline()
        d = self._renderAndReturnReaderResult(readline, bytes)
        d.addCallback(self.assertEqual, b"second line\n")
        return d


    def test_readlineNone(self):
        """
        Calling L{_InputStream.readline} with L{None} as an argument returns
        one line from the input stream.
        """
        bytes = b"this is one line\nthis is another line"
        d = self._renderAndReturnReaderResult(
            lambda input: input.readline(None), bytes)
        d.addCallback(self.assertEqual, b"this is one line\n")
        return d


    def test_readlineNegative(self):
        """
        Calling L{_InputStream.readline} with a negative integer as an argument
        returns one line from the input stream.
        """
        bytes = b"input stream line one\nline two"
        d = self._renderAndReturnReaderResult(
            lambda input: input.readline(-1), bytes)
        d.addCallback(self.assertEqual, b"input stream line one\n")
        return d


    def test_readlines(self):
        """
        Calling L{_InputStream.readlines} with no arguments returns a list of
        all lines from the input stream.
        """
        bytes = b"alice\nbob\ncarol"
        d = self._renderAndReturnReaderResult(
            lambda input: input.readlines(), bytes)
        d.addCallback(self.assertEqual, [b"alice\n", b"bob\n", b"carol"])
        return d


    def test_readlinesSome(self):
        """
        Calling L{_InputStream.readlines} with an integer as an argument
        returns a list of lines from the input stream with the argument serving
        as an approximate bound on the total number of bytes to read.
        """
        bytes = b"123\n456\n789\n0"
        d = self._renderAndReturnReaderResult(
            lambda input: input.readlines(5), bytes)
        def cbLines(lines):
            # Make sure we got enough lines to make 5 bytes.  Anything beyond
            # that is fine too.
            self.assertEqual(lines[:2], [b"123\n", b"456\n"])
        d.addCallback(cbLines)
        return d


    def test_readlinesMoreThan(self):
        """
        Calling L{_InputStream.readlines} with an integer which is greater than
        the total number of bytes in the input stream returns a list of all
        lines from the input.
        """
        bytes = b"one potato\ntwo potato\nthree potato"
        d = self._renderAndReturnReaderResult(
            lambda input: input.readlines(100), bytes)
        d.addCallback(
            self.assertEqual,
            [b"one potato\n", b"two potato\n", b"three potato"])
        return d


    def test_readlinesAfterRead(self):
        """
        Calling L{_InputStream.readlines} after a call to L{_InputStream.read}
        returns lines starting at the byte after the last byte returned by the
        C{read} call.
        """
        bytes = b"hello\nworld\nfoo"
        def readlines(input):
            input.read(7)
            return input.readlines()
        d = self._renderAndReturnReaderResult(readlines, bytes)
        d.addCallback(self.assertEqual, [b"orld\n", b"foo"])
        return d


    def test_readlinesNone(self):
        """
        Calling L{_InputStream.readlines} with L{None} as an argument returns
        all lines from the input.
        """
        bytes = b"one fish\ntwo fish\n"
        d = self._renderAndReturnReaderResult(
            lambda input: input.readlines(None), bytes)
        d.addCallback(self.assertEqual, [b"one fish\n", b"two fish\n"])
        return d


    def test_readlinesNegative(self):
        """
        Calling L{_InputStream.readlines} with a negative integer as an
        argument returns a list of all lines from the input.
        """
        bytes = b"red fish\nblue fish\n"
        d = self._renderAndReturnReaderResult(
            lambda input: input.readlines(-1), bytes)
        d.addCallback(self.assertEqual, [b"red fish\n", b"blue fish\n"])
        return d


    def test_iterable(self):
        """
        Iterating over L{_InputStream} produces lines from the input stream.
        """
        bytes = b"green eggs\nand ham\n"
        d = self._renderAndReturnReaderResult(lambda input: list(input), bytes)
        d.addCallback(self.assertEqual, [b"green eggs\n", b"and ham\n"])
        return d


    def test_iterableAfterRead(self):
        """
        Iterating over L{_InputStream} after calling L{_InputStream.read}
        produces lines from the input stream starting from the first byte after
        the last byte returned by the C{read} call.
        """
        bytes = b"green eggs\nand ham\n"
        def iterate(input):
            input.read(3)
            return list(input)
        d = self._renderAndReturnReaderResult(iterate, bytes)
        d.addCallback(self.assertEqual, [b"en eggs\n", b"and ham\n"])
        return d



class InputStreamStringIOTests(InputStreamTestMixin, TestCase):
    """
    Tests for L{_InputStream} when it is wrapped around a
    L{StringIO.StringIO}.

    This is only available in Python 2.
    """
    def getFileType(self):
        try:
            from StringIO import StringIO
        except ImportError:
            raise SkipTest("StringIO.StringIO is not available.")
        else:
            return StringIO



class InputStreamCStringIOTests(InputStreamTestMixin, TestCase):
    """
    Tests for L{_InputStream} when it is wrapped around a
    L{cStringIO.StringIO}.

    This is only available in Python 2.
    """
    def getFileType(self):
        try:
            from cStringIO import StringIO
        except ImportError:
            raise SkipTest("cStringIO.StringIO is not available.")
        else:
            return StringIO



class InputStreamBytesIOTests(InputStreamTestMixin, TestCase):
    """
    Tests for L{_InputStream} when it is wrapped around an L{io.BytesIO}.
    """
    def getFileType(self):
        from io import BytesIO
        return BytesIO



class InputStreamTemporaryFileTests(InputStreamTestMixin, TestCase):
    """
    Tests for L{_InputStream} when it is wrapped around a L{tempfile.TemporaryFile}.
    """
    def getFileType(self):
        return tempfile.TemporaryFile



class StartResponseTests(WSGITestsMixin, TestCase):
    """
    Tests for the I{start_response} parameter passed to the application object
    by L{WSGIResource}.
    """
    def test_status(self):
        """
        The response status passed to the I{start_response} callable is written
        as the status of the response to the request.
        """
        channel = DummyChannel()

        def applicationFactory():
            def application(environ, startResponse):
                startResponse('107 Strange message', [])
                return iter(())
            return application

        d, requestFactory = self.requestFactoryFactory()
        def cbRendered(ignored):
            self.assertTrue(
                channel.transport.written.getvalue().startswith(
                    b'HTTP/1.1 107 Strange message'))
        d.addCallback(cbRendered)

        self.lowLevelRender(
            requestFactory, applicationFactory,
            lambda: channel, 'GET', '1.1', [], [''], None, [])

        return d


    def test_statusMustBeNativeString(self):
        """
        The response status passed to the I{start_response} callable MUST be a
        native string in Python 2 and Python 3.
        """
        status = b"200 OK" if _PY3 else u"200 OK"

        def application(environ, startResponse):
            startResponse(status, [])
            return iter(())

        request, result = self.prepareRequest(application)
        request.requestReceived()

        def checkMessage(error):
            if _PY3:
                self.assertEqual(
                    "status must be str, not b'200 OK' (bytes)", str(error))
            else:
                self.assertEqual(
                    "status must be str, not u'200 OK' (unicode)", str(error))

        return self.assertFailure(result, TypeError).addCallback(checkMessage)


    def _headersTest(self, appHeaders, expectedHeaders):
        """
        Verify that if the response headers given by C{appHeaders} are passed
        to the I{start_response} callable, then the response header lines given
        by C{expectedHeaders} plus I{Server} and I{Date} header lines are
        included in the response.
        """
        # Make the Date header value deterministic
        self.patch(http, 'datetimeToString', lambda: 'Tuesday')

        channel = DummyChannel()

        def applicationFactory():
            def application(environ, startResponse):
                startResponse('200 OK', appHeaders)
                return iter(())
            return application

        d, requestFactory = self.requestFactoryFactory()
        def cbRendered(ignored):
            response = channel.transport.written.getvalue()
            headers, rest = response.split(b'\r\n\r\n', 1)
            headerLines = headers.split(b'\r\n')[1:]
            headerLines.sort()
            allExpectedHeaders = expectedHeaders + [
                b'Date: Tuesday',
                b'Server: ' + version,
                b'Transfer-Encoding: chunked']
            allExpectedHeaders.sort()
            self.assertEqual(headerLines, allExpectedHeaders)

        d.addCallback(cbRendered)

        self.lowLevelRender(
            requestFactory, applicationFactory,
            lambda: channel, 'GET', '1.1', [], [''], None, [])
        return d


    def test_headers(self):
        """
        The headers passed to the I{start_response} callable are included in
        the response as are the required I{Date} and I{Server} headers and the
        necessary connection (hop to hop) header I{Transfer-Encoding}.
        """
        return self._headersTest(
            [('foo', 'bar'), ('baz', 'quux')],
            [b'Baz: quux', b'Foo: bar'])


    def test_headersMustBeSequence(self):
        """
        The headers passed to the I{start_response} callable MUST be a
        sequence.
        """
        headers = [("key", "value")]

        def application(environ, startResponse):
            startResponse("200 OK", iter(headers))
            return iter(())

        request, result = self.prepareRequest(application)
        request.requestReceived()

        def checkMessage(error):
            self.assertRegex(
                str(error), "headers must be a list, not "
                r"<(list_?|sequence)iterator .+> [(]\1iterator[)]")

        return self.assertFailure(result, TypeError).addCallback(checkMessage)


    def test_headersShouldBePlainList(self):
        """
        According to PEP-3333, the headers passed to the I{start_response}
        callable MUST be a plain list:

          The response_headers argument ... must be a Python list; i.e.
          type(response_headers) is ListType

        However, for bug-compatibility, any sequence is accepted. In both
        Python 2 and Python 3, only a warning is issued when a sequence other
        than a list is encountered.
        """
        def application(environ, startResponse):
            startResponse("200 OK", (("not", "list"),))
            return iter(())

        request, result = self.prepareRequest(application)

        with warnings.catch_warnings(record=True) as caught:
            request.requestReceived()
            result = self.successResultOf(result)
        self.assertEqual(1, len(caught))
        self.assertEqual(RuntimeWarning, caught[0].category)
        self.assertEqual(
            "headers should be a list, not (('not', 'list'),) (tuple)",
            str(caught[0].message))


    def test_headersMustEachBeSequence(self):
        """
        Each header passed to the I{start_response} callable MUST be a
        sequence.
        """
        header = ("key", "value")

        def application(environ, startResponse):
            startResponse("200 OK", [iter(header)])
            return iter(())

        request, result = self.prepareRequest(application)
        request.requestReceived()

        def checkMessage(error):
            self.assertRegex(
                str(error), "header must be a [(]str, str[)] tuple, not "
                r"<(tuple_?|sequence)iterator .+> [(]\1iterator[)]")

        return self.assertFailure(result, TypeError).addCallback(checkMessage)


    def test_headersShouldEachBeTuple(self):
        """
        According to PEP-3333, each header passed to the I{start_response}
        callable should be a tuple:

          The response_headers argument is a list of (header_name,
          header_value) tuples

        However, for bug-compatibility, any 2 element sequence is also
        accepted. In both Python 2 and Python 3, only a warning is issued when
        a sequence other than a tuple is encountered.
        """
        def application(environ, startResponse):
            startResponse("200 OK", [["not", "tuple"]])
            return iter(())

        request, result = self.prepareRequest(application)

        with warnings.catch_warnings(record=True) as caught:
            request.requestReceived()
            result = self.successResultOf(result)
        self.assertEqual(1, len(caught))
        self.assertEqual(RuntimeWarning, caught[0].category)
        self.assertEqual(
            "header should be a (str, str) tuple, not ['not', 'tuple'] (list)",
            str(caught[0].message))


    def test_headersShouldEachHaveKeyAndValue(self):
        """
        Each header passed to the I{start_response} callable MUST hold a key
        and a value, and ONLY a key and a value.
        """
        def application(environ, startResponse):
            startResponse("200 OK", [("too", "many", "cooks")])
            return iter(())

        request, result = self.prepareRequest(application)
        request.requestReceived()

        def checkMessage(error):
            self.assertEqual(
                "header must be a (str, str) tuple, not "
                "('too', 'many', 'cooks')", str(error))

        return self.assertFailure(result, TypeError).addCallback(checkMessage)


    def test_headerKeyMustBeNativeString(self):
        """
        Each header key passed to the I{start_response} callable MUST be at
        native string in Python 2 and Python 3.
        """
        key = b"key" if _PY3 else u"key"

        def application(environ, startResponse):
            startResponse("200 OK", [(key, "value")])
            return iter(())

        request, result = self.prepareRequest(application)
        request.requestReceived()

        def checkMessage(error):
            self.assertEqual(
                "header must be (str, str) tuple, not (%r, 'value')" % (key,),
                str(error))

        return self.assertFailure(result, TypeError).addCallback(checkMessage)


    def test_headerValueMustBeNativeString(self):
        """
        Each header value passed to the I{start_response} callable MUST be at
        native string in Python 2 and Python 3.
        """
        value = b"value" if _PY3 else u"value"

        def application(environ, startResponse):
            startResponse("200 OK", [("key", value)])
            return iter(())

        request, result = self.prepareRequest(application)
        request.requestReceived()

        def checkMessage(error):
            self.assertEqual(
                "header must be (str, str) tuple, not ('key', %r)" % (value,),
                str(error))

        return self.assertFailure(result, TypeError).addCallback(checkMessage)


    def test_applicationProvidedContentType(self):
        """
        If I{Content-Type} is included in the headers passed to the
        I{start_response} callable, one I{Content-Type} header is included in
        the response.
        """
        return self._headersTest(
            [('content-type', 'monkeys are great')],
            [b'Content-Type: monkeys are great'])


    def test_applicationProvidedServerAndDate(self):
        """
        If either I{Server} or I{Date} is included in the headers passed to the
        I{start_response} callable, they are disregarded.
        """
        return self._headersTest(
            [('server', 'foo'), ('Server', 'foo'),
             ('date', 'bar'), ('dATE', 'bar')],
            [])


    def test_delayedUntilReturn(self):
        """
        Nothing is written in response to a request when the I{start_response}
        callable is invoked.  If the iterator returned by the application
        object produces only empty strings, the response is written after the
        last element is produced.
        """
        channel = DummyChannel()

        intermediateValues = []
        def record():
            intermediateValues.append(channel.transport.written.getvalue())

        def applicationFactory():
            def application(environ, startResponse):
                startResponse('200 OK', [('foo', 'bar'), ('baz', 'quux')])
                yield b''
                record()
            return application

        d, requestFactory = self.requestFactoryFactory()
        def cbRendered(ignored):
            self.assertEqual(intermediateValues, [b''])
        d.addCallback(cbRendered)

        self.lowLevelRender(
            requestFactory, applicationFactory,
            lambda: channel, 'GET', '1.1', [], [''], None, [])

        return d


    def test_delayedUntilContent(self):
        """
        Nothing is written in response to a request when the I{start_response}
        callable is invoked.  Once a non-empty string has been produced by the
        iterator returned by the application object, the response status and
        headers are written.
        """
        channel = DummyChannel()

        intermediateValues = []
        def record():
            intermediateValues.append(channel.transport.written.getvalue())

        def applicationFactory():
            def application(environ, startResponse):
                startResponse('200 OK', [('foo', 'bar')])
                yield b''
                record()
                yield b'foo'
                record()
            return application

        d, requestFactory = self.requestFactoryFactory()
        def cbRendered(ignored):
            self.assertFalse(intermediateValues[0])
            self.assertTrue(intermediateValues[1])
        d.addCallback(cbRendered)

        self.lowLevelRender(
            requestFactory, applicationFactory,
            lambda: channel, 'GET', '1.1', [], [''], None, [])

        return d


    def test_content(self):
        """
        Content produced by the iterator returned by the application object is
        written to the request as it is produced.
        """
        channel = DummyChannel()

        intermediateValues = []
        def record():
            intermediateValues.append(channel.transport.written.getvalue())

        def applicationFactory():
            def application(environ, startResponse):
                startResponse('200 OK', [('content-length', '6')])
                yield b'foo'
                record()
                yield b'bar'
                record()
            return application

        d, requestFactory = self.requestFactoryFactory()
        def cbRendered(ignored):
            self.assertEqual(
                self.getContentFromResponse(intermediateValues[0]),
                b'foo')
            self.assertEqual(
                self.getContentFromResponse(intermediateValues[1]),
                b'foobar')
        d.addCallback(cbRendered)

        self.lowLevelRender(
            requestFactory, applicationFactory,
            lambda: channel, 'GET', '1.1', [], [''], None, [])

        return d


    def test_multipleStartResponse(self):
        """
        If the I{start_response} callable is invoked multiple times before a
        data for the response body is produced, the values from the last call
        are used.
        """
        channel = DummyChannel()

        def applicationFactory():
            def application(environ, startResponse):
                startResponse('100 Foo', [])
                startResponse('200 Bar', [])
                return iter(())
            return application

        d, requestFactory = self.requestFactoryFactory()
        def cbRendered(ignored):
            self.assertTrue(
                channel.transport.written.getvalue().startswith(
                    b'HTTP/1.1 200 Bar\r\n'))
        d.addCallback(cbRendered)

        self.lowLevelRender(
            requestFactory, applicationFactory,
            lambda: channel, 'GET', '1.1', [], [''], None, [])

        return d


    def test_startResponseWithException(self):
        """
        If the I{start_response} callable is invoked with a third positional
        argument before the status and headers have been written to the
        response, the status and headers become the newly supplied values.
        """
        channel = DummyChannel()

        def applicationFactory():
            def application(environ, startResponse):
                startResponse('100 Foo', [], (Exception, Exception("foo"), None))
                return iter(())
            return application

        d, requestFactory = self.requestFactoryFactory()
        def cbRendered(ignored):
            self.assertTrue(
                channel.transport.written.getvalue().startswith(
                    b'HTTP/1.1 100 Foo\r\n'))
        d.addCallback(cbRendered)

        self.lowLevelRender(
            requestFactory, applicationFactory,
            lambda: channel, 'GET', '1.1', [], [''], None, [])

        return d


    def test_startResponseWithExceptionTooLate(self):
        """
        If the I{start_response} callable is invoked with a third positional
        argument after the status and headers have been written to the
        response, the supplied I{exc_info} values are re-raised to the
        application.
        """
        channel = DummyChannel()

        class SomeException(Exception):
            pass

        try:
            raise SomeException()
        except:
            excInfo = exc_info()

        reraised = []

        def applicationFactory():
            def application(environ, startResponse):
                startResponse('200 OK', [])
                yield b'foo'
                try:
                    startResponse('500 ERR', [], excInfo)
                except:
                    reraised.append(exc_info())
            return application

        d, requestFactory = self.requestFactoryFactory()
        def cbRendered(ignored):
            self.assertTrue(
                channel.transport.written.getvalue().startswith(
                    b'HTTP/1.1 200 OK\r\n'))
            self.assertEqual(reraised[0][0], excInfo[0])
            self.assertEqual(reraised[0][1], excInfo[1])

            # Show that the tracebacks end with the same stack frames.
            tb1 = reraised[0][2].tb_next
            tb2 = excInfo[2]
            self.assertEqual(
                # On Python 2 (str is bytes) we need to move back only one
                # stack frame to skip. On Python 3 we need to move two frames.
                traceback.extract_tb(tb1)[1 if str is bytes else 2],
                traceback.extract_tb(tb2)[0]
            )

        d.addCallback(cbRendered)

        self.lowLevelRender(
            requestFactory, applicationFactory,
            lambda: channel, 'GET', '1.1', [], [''], None, [])

        return d


    def test_write(self):
        """
        I{start_response} returns the I{write} callable which can be used to
        write bytes to the response body without buffering.
        """
        channel = DummyChannel()

        intermediateValues = []
        def record():
            intermediateValues.append(channel.transport.written.getvalue())

        def applicationFactory():
            def application(environ, startResponse):
                write = startResponse('100 Foo', [('content-length', '6')])
                write(b'foo')
                record()
                write(b'bar')
                record()
                return iter(())
            return application

        d, requestFactory = self.requestFactoryFactory()
        def cbRendered(ignored):
            self.assertEqual(
                self.getContentFromResponse(intermediateValues[0]),
                b'foo')
            self.assertEqual(
                self.getContentFromResponse(intermediateValues[1]),
                b'foobar')
        d.addCallback(cbRendered)

        self.lowLevelRender(
            requestFactory, applicationFactory,
            lambda: channel, 'GET', '1.1', [], [''], None, [])

        return d


    def test_writeAcceptsOnlyByteStrings(self):
        """
        The C{write} callable returned from C{start_response} only accepts
        byte strings.
        """
        def application(environ, startResponse):
            write = startResponse("200 OK", [])
            write(u"bogus")
            return iter(())

        request, result = self.prepareRequest(application)
        request.requestReceived()

        def checkMessage(error):
            if _PY3:
                self.assertEqual(
                    "Can only write bytes to a transport, not 'bogus'",
                    str(error))
            else:
                self.assertEqual(
                    "Can only write bytes to a transport, not u'bogus'",
                    str(error))

        return self.assertFailure(result, TypeError).addCallback(checkMessage)



class ApplicationTests(WSGITestsMixin, TestCase):
    """
    Tests for things which are done to the application object and the iterator
    it returns.
    """
    def enableThreads(self):
        self.reactor = reactor
        self.threadpool = ThreadPool()
        self.threadpool.start()
        self.addCleanup(self.threadpool.stop)


    def test_close(self):
        """
        If the application object returns an iterator which also has a I{close}
        method, that method is called after iteration is complete.
        """
        channel = DummyChannel()

        class Result:
            def __init__(self):
                self.open = True

            def __iter__(self):
                for i in range(3):
                    if self.open:
                        yield intToBytes(i)

            def close(self):
                self.open = False

        result = Result()
        def applicationFactory():
            def application(environ, startResponse):
                startResponse('200 OK', [('content-length', '3')])
                return result
            return application

        d, requestFactory = self.requestFactoryFactory()
        def cbRendered(ignored):
            self.assertEqual(
                self.getContentFromResponse(
                    channel.transport.written.getvalue()),
                b'012')
            self.assertFalse(result.open)
        d.addCallback(cbRendered)

        self.lowLevelRender(
            requestFactory, applicationFactory,
            lambda: channel, 'GET', '1.1', [], [''])

        return d


    def test_applicationCalledInThread(self):
        """
        The application object is invoked and iterated in a thread which is not
        the reactor thread.
        """
        self.enableThreads()
        invoked = []

        def applicationFactory():
            def application(environ, startResponse):
                def result():
                    for i in range(3):
                        invoked.append(getThreadID())
                        yield intToBytes(i)
                invoked.append(getThreadID())
                startResponse('200 OK', [('content-length', '3')])
                return result()
            return application

        d, requestFactory = self.requestFactoryFactory()
        def cbRendered(ignored):
            self.assertNotIn(getThreadID(), invoked)
            self.assertEqual(len(set(invoked)), 1)
        d.addCallback(cbRendered)

        self.lowLevelRender(
            requestFactory, applicationFactory,
            DummyChannel, 'GET', '1.1', [], [''])

        return d


    def test_writeCalledFromThread(self):
        """
        The I{write} callable returned by I{start_response} calls the request's
        C{write} method in the reactor thread.
        """
        self.enableThreads()
        invoked = []

        class ThreadVerifier(Request):
            def write(self, bytes):
                invoked.append(getThreadID())
                return Request.write(self, bytes)

        def applicationFactory():
            def application(environ, startResponse):
                write = startResponse('200 OK', [])
                write(b'foo')
                return iter(())
            return application

        d, requestFactory = self.requestFactoryFactory(ThreadVerifier)
        def cbRendered(ignored):
            self.assertEqual(set(invoked), set([getThreadID()]))
        d.addCallback(cbRendered)

        self.lowLevelRender(
            requestFactory, applicationFactory, DummyChannel,
            'GET', '1.1', [], [''])

        return d


    def test_iteratedValuesWrittenFromThread(self):
        """
        Strings produced by the iterator returned by the application object are
        written to the request in the reactor thread.
        """
        self.enableThreads()
        invoked = []

        class ThreadVerifier(Request):
            def write(self, bytes):
                invoked.append(getThreadID())
                return Request.write(self, bytes)

        def applicationFactory():
            def application(environ, startResponse):
                startResponse('200 OK', [])
                yield b'foo'
            return application

        d, requestFactory = self.requestFactoryFactory(ThreadVerifier)
        def cbRendered(ignored):
            self.assertEqual(set(invoked), set([getThreadID()]))
        d.addCallback(cbRendered)

        self.lowLevelRender(
            requestFactory, applicationFactory, DummyChannel,
            'GET', '1.1', [], [''])

        return d


    def test_statusWrittenFromThread(self):
        """
        The response status is set on the request object in the reactor thread.
        """
        self.enableThreads()
        invoked = []

        class ThreadVerifier(Request):
            def setResponseCode(self, code, message):
                invoked.append(getThreadID())
                return Request.setResponseCode(self, code, message)

        def applicationFactory():
            def application(environ, startResponse):
                startResponse('200 OK', [])
                return iter(())
            return application

        d, requestFactory = self.requestFactoryFactory(ThreadVerifier)
        def cbRendered(ignored):
            self.assertEqual(set(invoked), set([getThreadID()]))
        d.addCallback(cbRendered)

        self.lowLevelRender(
            requestFactory, applicationFactory, DummyChannel,
            'GET', '1.1', [], [''])

        return d


    def test_connectionClosedDuringIteration(self):
        """
        If the request connection is lost while the application object is being
        iterated, iteration is stopped.
        """
        class UnreliableConnection(Request):
            """
            This is a request which pretends its connection is lost immediately
            after the first write is done to it.
            """
            def write(self, bytes):
                self.connectionLost(Failure(ConnectionLost("No more connection")))

        self.badIter = False
        def appIter():
            yield b"foo"
            self.badIter = True
            raise Exception("Should not have gotten here")

        def applicationFactory():
            def application(environ, startResponse):
                startResponse('200 OK', [])
                return appIter()
            return application

        d, requestFactory = self.requestFactoryFactory(UnreliableConnection)
        def cbRendered(ignored):
            self.assertFalse(self.badIter, "Should not have resumed iteration")
        d.addCallback(cbRendered)

        self.lowLevelRender(
            requestFactory, applicationFactory, DummyChannel,
            'GET', '1.1', [], [''])

        return self.assertFailure(d, ConnectionLost)


    def _internalServerErrorTest(self, application):
        channel = DummyChannel()

        def applicationFactory():
            return application

        d, requestFactory = self.requestFactoryFactory()
        def cbRendered(ignored):
            errors = self.flushLoggedErrors(RuntimeError)
            self.assertEqual(len(errors), 1)

            self.assertTrue(
                channel.transport.written.getvalue().startswith(
                    b'HTTP/1.1 500 Internal Server Error'))
        d.addCallback(cbRendered)

        self.lowLevelRender(
            requestFactory, applicationFactory,
            lambda: channel, 'GET', '1.1', [], [''], None, [])

        return d


    def test_applicationExceptionBeforeStartResponse(self):
        """
        If the application raises an exception before calling I{start_response}
        then the response status is I{500} and the exception is logged.
        """
        def application(environ, startResponse):
            raise RuntimeError("This application had some error.")
        return self._internalServerErrorTest(application)


    def test_applicationExceptionAfterStartResponse(self):
        """
        If the application calls I{start_response} but then raises an exception
        before any data is written to the response then the response status is
        I{500} and the exception is logged.
        """
        def application(environ, startResponse):
            startResponse('200 OK', [])
            raise RuntimeError("This application had some error.")
        return self._internalServerErrorTest(application)


    def _connectionClosedTest(self, application, responseContent):
        channel = DummyChannel()

        def applicationFactory():
            return application

        d, requestFactory = self.requestFactoryFactory()

        # Capture the request so we can disconnect it later on.
        requests = []
        def requestFactoryWrapper(*a, **kw):
            requests.append(requestFactory(*a, **kw))
            return requests[-1]

        def ebRendered(ignored):
            errors = self.flushLoggedErrors(RuntimeError)
            self.assertEqual(len(errors), 1)

            response = channel.transport.written.getvalue()
            self.assertTrue(response.startswith(b'HTTP/1.1 200 OK'))
            # Chunked transfer-encoding makes this a little messy.
            self.assertIn(responseContent, response)
        d.addErrback(ebRendered)

        self.lowLevelRender(
            requestFactoryWrapper, applicationFactory,
            lambda: channel, 'GET', '1.1', [], [''], None, [])

        # By now the connection should be closed.
        self.assertTrue(channel.transport.disconnected)
        # Give it a little push to go the rest of the way.
        requests[0].connectionLost(Failure(ConnectionLost("All gone")))

        return d


    def test_applicationExceptionAfterWrite(self):
        """
        If the application raises an exception after the response status has
        already been sent then the connection is closed and the exception is
        logged.
        """
        responseContent = (
            b'Some bytes, triggering the server to start sending the response')

        def application(environ, startResponse):
            startResponse('200 OK', [])
            yield responseContent
            raise RuntimeError("This application had some error.")
        return self._connectionClosedTest(application, responseContent)


    def test_applicationCloseException(self):
        """
        If the application returns a closeable iterator and the C{close} method
        raises an exception when called then the connection is still closed and
        the exception is logged.
        """
        responseContent = b'foo'

        class Application(object):
            def __init__(self, environ, startResponse):
                startResponse('200 OK', [])

            def __iter__(self):
                yield responseContent

            def close(self):
                raise RuntimeError("This application had some error.")

        return self._connectionClosedTest(Application, responseContent)
