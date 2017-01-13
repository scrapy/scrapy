# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
An implementation of
U{Python Web Server Gateway Interface v1.0.1<http://www.python.org/dev/peps/pep-3333/>}.
"""

__metaclass__ = type

from collections import Sequence
from sys import exc_info
from warnings import warn

from zope.interface import implementer

from twisted.internet.threads import blockingCallFromThread
from twisted.python.compat import reraise
from twisted.python.log import msg, err
from twisted.python.failure import Failure
from twisted.web.resource import IResource
from twisted.web.server import NOT_DONE_YET
from twisted.web.http import INTERNAL_SERVER_ERROR



# PEP-3333 -- which has superseded PEP-333 -- states that, in both Python 2
# and Python 3, text strings MUST be represented using the platform's native
# string type, limited to characters defined in ISO-8859-1. Byte strings are
# used only for values read from wsgi.input, passed to write() or yielded by
# the application.
#
# Put another way:
#
# - In Python 2, all text strings and binary data are of type str/bytes and
#   NEVER of type unicode. Whether the strings contain binary data or
#   ISO-8859-1 text depends on context.
#
# - In Python 3, all text strings are of type str, and all binary data are of
#   type bytes. Text MUST always be limited to that which can be encoded as
#   ISO-8859-1, U+0000 to U+00FF inclusive.
#
# The following pair of functions -- _wsgiString() and _wsgiStringToBytes() --
# are used to make Twisted's WSGI support compliant with the standard.
if str is bytes:
    def _wsgiString(string):  # Python 2.
        """
        Convert C{string} to an ISO-8859-1 byte string, if it is not already.

        @type string: C{str}/C{bytes} or C{unicode}
        @rtype: C{str}/C{bytes}

        @raise UnicodeEncodeError: If C{string} contains non-ISO-8859-1 chars.
        """
        if isinstance(string, str):
            return string
        else:
            return string.encode('iso-8859-1')

    def _wsgiStringToBytes(string):  # Python 2.
        """
        Return C{string} as is; a WSGI string is a byte string in Python 2.

        @type string: C{str}/C{bytes}
        @rtype: C{str}/C{bytes}
        """
        return string

else:
    def _wsgiString(string):  # Python 3.
        """
        Convert C{string} to a WSGI "bytes-as-unicode" string.

        If it's a byte string, decode as ISO-8859-1. If it's a Unicode string,
        round-trip it to bytes and back using ISO-8859-1 as the encoding.

        @type string: C{str} or C{bytes}
        @rtype: C{str}

        @raise UnicodeEncodeError: If C{string} contains non-ISO-8859-1 chars.
        """
        if isinstance(string, str):
            return string.encode("iso-8859-1").decode('iso-8859-1')
        else:
            return string.decode("iso-8859-1")

    def _wsgiStringToBytes(string):  # Python 3.
        """
        Convert C{string} from a WSGI "bytes-as-unicode" string to an
        ISO-8859-1 byte string.

        @type string: C{str}
        @rtype: C{bytes}

        @raise UnicodeEncodeError: If C{string} contains non-ISO-8859-1 chars.
        """
        return string.encode("iso-8859-1")



class _ErrorStream:
    """
    File-like object instances of which are used as the value for the
    C{'wsgi.errors'} key in the C{environ} dictionary passed to the application
    object.

    This simply passes writes on to L{logging<twisted.python.log>} system as
    error events from the C{'wsgi'} system.  In the future, it may be desirable
    to expose more information in the events it logs, such as the application
    object which generated the message.
    """

    def write(self, data):
        """
        Generate an event for the logging system with the given bytes as the
        message.

        This is called in a WSGI application thread, not the I/O thread.

        @type data: str

        @raise TypeError: On Python 3, if C{data} is not a native string. On
            Python 2 a warning will be issued.
        """
        if not isinstance(data, str):
            if str is bytes:
                warn("write() argument should be str, not %r (%s)" % (
                    data, type(data).__name__), category=UnicodeWarning)
            else:
                raise TypeError(
                    "write() argument must be str, not %r (%s)"
                    % (data, type(data).__name__))

        msg(data, system='wsgi', isError=True)


    def writelines(self, iovec):
        """
        Join the given lines and pass them to C{write} to be handled in the
        usual way.

        This is called in a WSGI application thread, not the I/O thread.

        @param iovec: A C{list} of C{'\\n'}-terminated C{str} which will be
            logged.

        @raise TypeError: On Python 3, if C{iovec} contains any non-native
            strings. On Python 2 a warning will be issued.
        """
        self.write(''.join(iovec))


    def flush(self):
        """
        Nothing is buffered, so flushing does nothing.  This method is required
        to exist by PEP 333, though.

        This is called in a WSGI application thread, not the I/O thread.
        """



class _InputStream:
    """
    File-like object instances of which are used as the value for the
    C{'wsgi.input'} key in the C{environ} dictionary passed to the application
    object.

    This only exists to make the handling of C{readline(-1)} consistent across
    different possible underlying file-like object implementations.  The other
    supported methods pass through directly to the wrapped object.
    """
    def __init__(self, input):
        """
        Initialize the instance.

        This is called in the I/O thread, not a WSGI application thread.
        """
        self._wrapped = input


    def read(self, size=None):
        """
        Pass through to the underlying C{read}.

        This is called in a WSGI application thread, not the I/O thread.
        """
        # Avoid passing None because cStringIO and file don't like it.
        if size is None:
            return self._wrapped.read()
        return self._wrapped.read(size)


    def readline(self, size=None):
        """
        Pass through to the underlying C{readline}, with a size of C{-1} replaced
        with a size of L{None}.

        This is called in a WSGI application thread, not the I/O thread.
        """
        # Check for -1 because StringIO doesn't handle it correctly.  Check for
        # None because files and tempfiles don't accept that.
        if size == -1 or size is None:
            return self._wrapped.readline()
        return self._wrapped.readline(size)


    def readlines(self, size=None):
        """
        Pass through to the underlying C{readlines}.

        This is called in a WSGI application thread, not the I/O thread.
        """
        # Avoid passing None because cStringIO and file don't like it.
        if size is None:
            return self._wrapped.readlines()
        return self._wrapped.readlines(size)


    def __iter__(self):
        """
        Pass through to the underlying C{__iter__}.

        This is called in a WSGI application thread, not the I/O thread.
        """
        return iter(self._wrapped)



class _WSGIResponse:
    """
    Helper for L{WSGIResource} which drives the WSGI application using a
    threadpool and hooks it up to the L{http.Request}.

    @ivar started: A L{bool} indicating whether or not the response status and
        headers have been written to the request yet.  This may only be read or
        written in the WSGI application thread.

    @ivar reactor: An L{IReactorThreads} provider which is used to call methods
        on the request in the I/O thread.

    @ivar threadpool: A L{ThreadPool} which is used to call the WSGI
        application object in a non-I/O thread.

    @ivar application: The WSGI application object.

    @ivar request: The L{http.Request} upon which the WSGI environment is
        based and to which the application's output will be sent.

    @ivar environ: The WSGI environment L{dict}.

    @ivar status: The HTTP response status L{str} supplied to the WSGI
        I{start_response} callable by the application.

    @ivar headers: A list of HTTP response headers supplied to the WSGI
        I{start_response} callable by the application.

    @ivar _requestFinished: A flag which indicates whether it is possible to
        generate more response data or not.  This is L{False} until
        L{http.Request.notifyFinish} tells us the request is done,
        then L{True}.
    """

    _requestFinished = False

    def __init__(self, reactor, threadpool, application, request):
        self.started = False
        self.reactor = reactor
        self.threadpool = threadpool
        self.application = application
        self.request = request
        self.request.notifyFinish().addBoth(self._finished)

        if request.prepath:
            scriptName = b'/' + b'/'.join(request.prepath)
        else:
            scriptName = b''

        if request.postpath:
            pathInfo = b'/' + b'/'.join(request.postpath)
        else:
            pathInfo = b''

        parts = request.uri.split(b'?', 1)
        if len(parts) == 1:
            queryString = b''
        else:
            queryString = parts[1]

        # All keys and values need to be native strings, i.e. of type str in
        # *both* Python 2 and Python 3, so says PEP-3333.
        self.environ = {
            'REQUEST_METHOD': _wsgiString(request.method),
            'REMOTE_ADDR': _wsgiString(request.getClientIP()),
            'SCRIPT_NAME': _wsgiString(scriptName),
            'PATH_INFO': _wsgiString(pathInfo),
            'QUERY_STRING': _wsgiString(queryString),
            'CONTENT_TYPE': _wsgiString(
                request.getHeader(b'content-type') or ''),
            'CONTENT_LENGTH': _wsgiString(
                request.getHeader(b'content-length') or ''),
            'SERVER_NAME': _wsgiString(request.getRequestHostname()),
            'SERVER_PORT': _wsgiString(str(request.getHost().port)),
            'SERVER_PROTOCOL': _wsgiString(request.clientproto)}

        # The application object is entirely in control of response headers;
        # disable the default Content-Type value normally provided by
        # twisted.web.server.Request.
        self.request.defaultContentType = None

        for name, values in request.requestHeaders.getAllRawHeaders():
            name = 'HTTP_' + _wsgiString(name).upper().replace('-', '_')
            # It might be preferable for http.HTTPChannel to clear out
            # newlines.
            self.environ[name] = ','.join(
                _wsgiString(v) for v in values).replace('\n', ' ')

        self.environ.update({
                'wsgi.version': (1, 0),
                'wsgi.url_scheme': request.isSecure() and 'https' or 'http',
                'wsgi.run_once': False,
                'wsgi.multithread': True,
                'wsgi.multiprocess': False,
                'wsgi.errors': _ErrorStream(),
                # Attend: request.content was owned by the I/O thread up until
                # this point.  By wrapping it and putting the result into the
                # environment dictionary, it is effectively being given to
                # another thread.  This means that whatever it is, it has to be
                # safe to access it from two different threads.  The access
                # *should* all be serialized (first the I/O thread writes to
                # it, then the WSGI thread reads from it, then the I/O thread
                # closes it).  However, since the request is made available to
                # arbitrary application code during resource traversal, it's
                # possible that some other code might decide to use it in the
                # I/O thread concurrently with its use in the WSGI thread.
                # More likely than not, this will break.  This seems like an
                # unlikely possibility to me, but if it is to be allowed,
                # something here needs to change. -exarkun
                'wsgi.input': _InputStream(request.content)})


    def _finished(self, ignored):
        """
        Record the end of the response generation for the request being
        serviced.
        """
        self._requestFinished = True


    def startResponse(self, status, headers, excInfo=None):
        """
        The WSGI I{start_response} callable.  The given values are saved until
        they are needed to generate the response.

        This will be called in a non-I/O thread.
        """
        if self.started and excInfo is not None:
            reraise(excInfo[1], excInfo[2])

        # PEP-3333 mandates that status should be a native string. In practice
        # this is mandated by Twisted's HTTP implementation too, so we enforce
        # on both Python 2 and Python 3.
        if not isinstance(status, str):
            raise TypeError(
                "status must be str, not %r (%s)"
                % (status, type(status).__name__))

        # PEP-3333 mandates that headers should be a plain list, but in
        # practice we work with any sequence type and only warn when it's not
        # a plain list.
        if isinstance(headers, list):
            pass  # This is okay.
        elif isinstance(headers, Sequence):
            warn("headers should be a list, not %r (%s)" % (
                headers, type(headers).__name__), category=RuntimeWarning)
        else:
            raise TypeError(
                "headers must be a list, not %r (%s)"
                % (headers, type(headers).__name__))

        # PEP-3333 mandates that each header should be a (str, str) tuple, but
        # in practice we work with any sequence type and only warn when it's
        # not a plain list.
        for header in headers:
            if isinstance(header, tuple):
                pass  # This is okay.
            elif isinstance(header, Sequence):
                warn("header should be a (str, str) tuple, not %r (%s)" % (
                    header, type(header).__name__), category=RuntimeWarning)
            else:
                raise TypeError(
                    "header must be a (str, str) tuple, not %r (%s)"
                    % (header, type(header).__name__))

            # However, the sequence MUST contain only 2 elements.
            if len(header) != 2:
                raise TypeError(
                    "header must be a (str, str) tuple, not %r"
                    % (header, ))

            # Both elements MUST be native strings. Non-native strings will be
            # rejected by the underlying HTTP machinery in any case, but we
            # reject them here in order to provide a more informative error.
            for elem in header:
                if not isinstance(elem, str):
                    raise TypeError(
                        "header must be (str, str) tuple, not %r"
                        % (header, ))

        self.status = status
        self.headers = headers
        return self.write


    def write(self, data):
        """
        The WSGI I{write} callable returned by the I{start_response} callable.
        The given bytes will be written to the response body, possibly flushing
        the status and headers first.

        This will be called in a non-I/O thread.
        """
        # PEP-3333 states:
        #
        #   The server or gateway must transmit the yielded bytestrings to the
        #   client in an unbuffered fashion, completing the transmission of
        #   each bytestring before requesting another one.
        #
        # This write() method is used for the imperative and (indirectly) for
        # the more familiar iterable-of-bytestrings WSGI mechanism. It uses
        # C{blockingCallFromThread} to schedule writes. This allows exceptions
        # to propagate up from the underlying HTTP implementation. However,
        # that underlying implementation does not, as yet, provide any way to
        # know if the written data has been transmitted, so this method
        # violates the above part of PEP-3333.
        #
        # PEP-3333 also says that a server may:
        #
        #   Use a different thread to ensure that the block continues to be
        #   transmitted while the application produces the next block.
        #
        # Which suggests that this is actually compliant with PEP-3333,
        # because writes are done in the reactor thread.
        #
        # However, providing some back-pressure may nevertheless be a Good
        # Thing at some point in the future.

        def wsgiWrite(started):
            if not started:
                self._sendResponseHeaders()
            self.request.write(data)

        try:
            return blockingCallFromThread(
                self.reactor, wsgiWrite, self.started)
        finally:
            self.started = True


    def _sendResponseHeaders(self):
        """
        Set the response code and response headers on the request object, but
        do not flush them.  The caller is responsible for doing a write in
        order for anything to actually be written out in response to the
        request.

        This must be called in the I/O thread.
        """
        code, message = self.status.split(None, 1)
        code = int(code)
        self.request.setResponseCode(code, _wsgiStringToBytes(message))

        for name, value in self.headers:
            # Don't allow the application to control these required headers.
            if name.lower() not in ('server', 'date'):
                self.request.responseHeaders.addRawHeader(
                    _wsgiStringToBytes(name), _wsgiStringToBytes(value))


    def start(self):
        """
        Start the WSGI application in the threadpool.

        This must be called in the I/O thread.
        """
        self.threadpool.callInThread(self.run)


    def run(self):
        """
        Call the WSGI application object, iterate it, and handle its output.

        This must be called in a non-I/O thread (ie, a WSGI application
        thread).
        """
        try:
            appIterator = self.application(self.environ, self.startResponse)
            for elem in appIterator:
                if elem:
                    self.write(elem)
                if self._requestFinished:
                    break
            close = getattr(appIterator, 'close', None)
            if close is not None:
                close()
        except:
            def wsgiError(started, type, value, traceback):
                err(Failure(value, type, traceback), "WSGI application error")
                if started:
                    self.request.loseConnection()
                else:
                    self.request.setResponseCode(INTERNAL_SERVER_ERROR)
                    self.request.finish()
            self.reactor.callFromThread(wsgiError, self.started, *exc_info())
        else:
            def wsgiFinish(started):
                if not self._requestFinished:
                    if not started:
                        self._sendResponseHeaders()
                    self.request.finish()
            self.reactor.callFromThread(wsgiFinish, self.started)
        self.started = True



@implementer(IResource)
class WSGIResource:
    """
    An L{IResource} implementation which delegates responsibility for all
    resources hierarchically inferior to it to a WSGI application.

    @ivar _reactor: An L{IReactorThreads} provider which will be passed on to
        L{_WSGIResponse} to schedule calls in the I/O thread.

    @ivar _threadpool: A L{ThreadPool} which will be passed on to
        L{_WSGIResponse} to run the WSGI application object.

    @ivar _application: The WSGI application object.
    """

    # Further resource segments are left up to the WSGI application object to
    # handle.
    isLeaf = True

    def __init__(self, reactor, threadpool, application):
        self._reactor = reactor
        self._threadpool = threadpool
        self._application = application


    def render(self, request):
        """
        Turn the request into the appropriate C{environ} C{dict} suitable to be
        passed to the WSGI application object and then pass it on.

        The WSGI application object is given almost complete control of the
        rendering process.  C{NOT_DONE_YET} will always be returned in order
        and response completion will be dictated by the application object, as
        will the status, headers, and the response body.
        """
        response = _WSGIResponse(
            self._reactor, self._threadpool, self._application, request)
        response.start()
        return NOT_DONE_YET


    def getChildWithDefault(self, name, request):
        """
        Reject attempts to retrieve a child resource.  All path segments beyond
        the one which refers to this resource are handled by the WSGI
        application object.
        """
        raise RuntimeError("Cannot get IResource children from WSGIResource")


    def putChild(self, path, child):
        """
        Reject attempts to add a child resource to this resource.  The WSGI
        application object handles all path segments beneath this resource, so
        L{IResource} children can never be found.
        """
        raise RuntimeError("Cannot put IResource children under WSGIResource")


__all__ = ['WSGIResource']
