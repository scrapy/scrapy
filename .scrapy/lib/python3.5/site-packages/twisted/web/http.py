# -*- test-case-name: twisted.web.test.test_http -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
HyperText Transfer Protocol implementation.

This is the basic server-side protocol implementation used by the Twisted
Web server.  It can parse HTTP 1.0 requests and supports many HTTP 1.1
features as well.  Additionally, some functionality implemented here is
also useful for HTTP clients (such as the chunked encoding parser).

@var CACHED: A marker value to be returned from cache-related request methods to
    indicate to the caller that a cached response will be usable and no response
    body should be generated.

@var NOT_MODIFIED: An HTTP response code indicating that a requested
    pre-condition (for example, the condition represented by an
    I{If-Modified-Since} header is present in the request) has succeeded.  This
    indicates a response body cached by the client can be used.

@var PRECONDITION_FAILED: An HTTP response code indicating that a requested
    pre-condition (for example, the condition represented by an I{If-None-Match}
    header is present in the request) has failed.  This should typically
    indicate that the server has not taken the requested action.
"""

from __future__ import division, absolute_import

__all__ = [
    'SWITCHING', 'OK', 'CREATED', 'ACCEPTED', 'NON_AUTHORITATIVE_INFORMATION',
    'NO_CONTENT', 'RESET_CONTENT', 'PARTIAL_CONTENT', 'MULTI_STATUS',

    'MULTIPLE_CHOICE', 'MOVED_PERMANENTLY', 'FOUND', 'SEE_OTHER',
    'NOT_MODIFIED', 'USE_PROXY', 'TEMPORARY_REDIRECT',

    'BAD_REQUEST', 'UNAUTHORIZED', 'PAYMENT_REQUIRED', 'FORBIDDEN', 'NOT_FOUND',
    'NOT_ALLOWED', 'NOT_ACCEPTABLE', 'PROXY_AUTH_REQUIRED', 'REQUEST_TIMEOUT',
    'CONFLICT', 'GONE', 'LENGTH_REQUIRED', 'PRECONDITION_FAILED',
    'REQUEST_ENTITY_TOO_LARGE', 'REQUEST_URI_TOO_LONG',
    'UNSUPPORTED_MEDIA_TYPE', 'REQUESTED_RANGE_NOT_SATISFIABLE',
    'EXPECTATION_FAILED',

    'INTERNAL_SERVER_ERROR', 'NOT_IMPLEMENTED', 'BAD_GATEWAY',
    'SERVICE_UNAVAILABLE', 'GATEWAY_TIMEOUT', 'HTTP_VERSION_NOT_SUPPORTED',
    'INSUFFICIENT_STORAGE_SPACE', 'NOT_EXTENDED',

    'RESPONSES', 'CACHED',

    'urlparse', 'parse_qs', 'datetimeToString', 'datetimeToLogString', 'timegm',
    'stringToDatetime', 'toChunk', 'fromChunk', 'parseContentRange',

    'StringTransport', 'HTTPClient', 'NO_BODY_CODES', 'Request',
    'PotentialDataLoss', 'HTTPChannel', 'HTTPFactory',
    ]


# system imports
import tempfile
import base64, binascii
import cgi
import math
import time
import calendar
import warnings
import os
from io import BytesIO as StringIO

try:
    from urlparse import (
        ParseResult as ParseResultBytes, urlparse as _urlparse)
    from urllib import unquote
    from cgi import parse_header as _parseHeader
except ImportError:
    from urllib.parse import (
        ParseResultBytes, urlparse as _urlparse, unquote_to_bytes as unquote)

    def _parseHeader(line):
        # cgi.parse_header requires a str
        key, pdict = cgi.parse_header(line.decode('charmap'))

        # We want the key as bytes, and cgi.parse_multipart (which consumes
        # pdict) expects a dict of str keys but bytes values
        key = key.encode('charmap')
        pdict = {x:y.encode('charmap') for x, y in pdict.items()}
        return (key, pdict)


from zope.interface import implementer, provider

# twisted imports
from twisted.python.compat import (
    _PY3, unicode, intToBytes, networkString, nativeString)
from twisted.python.deprecate import deprecated
from twisted.python import log
from twisted.python.versions import Version
from twisted.python.components import proxyForInterface
from twisted.internet import interfaces, protocol, address
from twisted.internet.defer import Deferred
from twisted.internet.interfaces import IProtocol
from twisted.protocols import policies, basic

from twisted.web.iweb import (
    IRequest, IAccessLogFormatter, INonQueuedRequestFactory)
from twisted.web.http_headers import Headers

try:
    from twisted.web._http2 import H2Connection
    H2_ENABLED = True
except ImportError:
    H2Connection = None
    H2_ENABLED = False

from twisted.web._responses import (
    SWITCHING,

    OK, CREATED, ACCEPTED, NON_AUTHORITATIVE_INFORMATION, NO_CONTENT,
    RESET_CONTENT, PARTIAL_CONTENT, MULTI_STATUS,

    MULTIPLE_CHOICE, MOVED_PERMANENTLY, FOUND, SEE_OTHER, NOT_MODIFIED,
    USE_PROXY, TEMPORARY_REDIRECT,

    BAD_REQUEST, UNAUTHORIZED, PAYMENT_REQUIRED, FORBIDDEN, NOT_FOUND,
    NOT_ALLOWED, NOT_ACCEPTABLE, PROXY_AUTH_REQUIRED, REQUEST_TIMEOUT,
    CONFLICT, GONE, LENGTH_REQUIRED, PRECONDITION_FAILED,
    REQUEST_ENTITY_TOO_LARGE, REQUEST_URI_TOO_LONG, UNSUPPORTED_MEDIA_TYPE,
    REQUESTED_RANGE_NOT_SATISFIABLE, EXPECTATION_FAILED,

    INTERNAL_SERVER_ERROR, NOT_IMPLEMENTED, BAD_GATEWAY, SERVICE_UNAVAILABLE,
    GATEWAY_TIMEOUT, HTTP_VERSION_NOT_SUPPORTED, INSUFFICIENT_STORAGE_SPACE,
    NOT_EXTENDED,

    RESPONSES)

if _PY3:
    _intTypes = int
else:
    _intTypes = (int, long)

protocol_version = "HTTP/1.1"

CACHED = """Magic constant returned by http.Request methods to set cache
validation headers when the request is conditional and the value fails
the condition."""

# backwards compatibility
responses = RESPONSES


# datetime parsing and formatting
weekdayname = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
monthname = [None,
             'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
             'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
weekdayname_lower = [name.lower() for name in weekdayname]
monthname_lower = [name and name.lower() for name in monthname]

def urlparse(url):
    """
    Parse an URL into six components.

    This is similar to C{urlparse.urlparse}, but rejects C{unicode} input
    and always produces C{bytes} output.

    @type url: C{bytes}

    @raise TypeError: The given url was a C{unicode} string instead of a
        C{bytes}.

    @return: The scheme, net location, path, params, query string, and fragment
        of the URL - all as C{bytes}.
    @rtype: C{ParseResultBytes}
    """
    if isinstance(url, unicode):
        raise TypeError("url must be bytes, not unicode")
    scheme, netloc, path, params, query, fragment = _urlparse(url)
    if isinstance(scheme, unicode):
        scheme = scheme.encode('ascii')
        netloc = netloc.encode('ascii')
        path = path.encode('ascii')
        query = query.encode('ascii')
        fragment = fragment.encode('ascii')
    return ParseResultBytes(scheme, netloc, path, params, query, fragment)



def parse_qs(qs, keep_blank_values=0, strict_parsing=0):
    """
    Like C{cgi.parse_qs}, but with support for parsing byte strings on Python 3.

    @type qs: C{bytes}
    """
    d = {}
    items = [s2 for s1 in qs.split(b"&") for s2 in s1.split(b";")]
    for item in items:
        try:
            k, v = item.split(b"=", 1)
        except ValueError:
            if strict_parsing:
                raise
            continue
        if v or keep_blank_values:
            k = unquote(k.replace(b"+", b" "))
            v = unquote(v.replace(b"+", b" "))
            if k in d:
                d[k].append(v)
            else:
                d[k] = [v]
    return d



def datetimeToString(msSinceEpoch=None):
    """
    Convert seconds since epoch to HTTP datetime string.

    @rtype: C{bytes}
    """
    if msSinceEpoch == None:
        msSinceEpoch = time.time()
    year, month, day, hh, mm, ss, wd, y, z = time.gmtime(msSinceEpoch)
    s = networkString("%s, %02d %3s %4d %02d:%02d:%02d GMT" % (
            weekdayname[wd],
            day, monthname[month], year,
            hh, mm, ss))
    return s



def datetimeToLogString(msSinceEpoch=None):
    """
    Convert seconds since epoch to log datetime string.

    @rtype: C{str}
    """
    if msSinceEpoch == None:
        msSinceEpoch = time.time()
    year, month, day, hh, mm, ss, wd, y, z = time.gmtime(msSinceEpoch)
    s = "[%02d/%3s/%4d:%02d:%02d:%02d +0000]" % (
        day, monthname[month], year,
        hh, mm, ss)
    return s



def timegm(year, month, day, hour, minute, second):
    """
    Convert time tuple in GMT to seconds since epoch, GMT
    """
    EPOCH = 1970
    if year < EPOCH:
        raise ValueError("Years prior to %d not supported" % (EPOCH,))
    assert 1 <= month <= 12
    days = 365*(year-EPOCH) + calendar.leapdays(EPOCH, year)
    for i in range(1, month):
        days = days + calendar.mdays[i]
    if month > 2 and calendar.isleap(year):
        days = days + 1
    days = days + day - 1
    hours = days*24 + hour
    minutes = hours*60 + minute
    seconds = minutes*60 + second
    return seconds



def stringToDatetime(dateString):
    """
    Convert an HTTP date string (one of three formats) to seconds since epoch.

    @type dateString: C{bytes}
    """
    parts = nativeString(dateString).split()

    if not parts[0][0:3].lower() in weekdayname_lower:
        # Weekday is stupid. Might have been omitted.
        try:
            return stringToDatetime(b"Sun, " + dateString)
        except ValueError:
            # Guess not.
            pass

    partlen = len(parts)
    if (partlen == 5 or partlen == 6) and parts[1].isdigit():
        # 1st date format: Sun, 06 Nov 1994 08:49:37 GMT
        # (Note: "GMT" is literal, not a variable timezone)
        # (also handles without "GMT")
        # This is the normal format
        day = parts[1]
        month = parts[2]
        year = parts[3]
        time = parts[4]
    elif (partlen == 3 or partlen == 4) and parts[1].find('-') != -1:
        # 2nd date format: Sunday, 06-Nov-94 08:49:37 GMT
        # (Note: "GMT" is literal, not a variable timezone)
        # (also handles without without "GMT")
        # Two digit year, yucko.
        day, month, year = parts[1].split('-')
        time = parts[2]
        year=int(year)
        if year < 69:
            year = year + 2000
        elif year < 100:
            year = year + 1900
    elif len(parts) == 5:
        # 3rd date format: Sun Nov  6 08:49:37 1994
        # ANSI C asctime() format.
        day = parts[2]
        month = parts[1]
        year = parts[4]
        time = parts[3]
    else:
        raise ValueError("Unknown datetime format %r" % dateString)

    day = int(day)
    month = int(monthname_lower.index(month.lower()))
    year = int(year)
    hour, min, sec = map(int, time.split(':'))
    return int(timegm(year, month, day, hour, min, sec))



def toChunk(data):
    """
    Convert string to a chunk.

    @type data: C{bytes}

    @returns: a tuple of C{bytes} representing the chunked encoding of data
    """
    return (networkString('%x' % (len(data),)), b"\r\n", data, b"\r\n")



def fromChunk(data):
    """
    Convert chunk to string.

    @type data: C{bytes}

    @return: tuple of (result, remaining) - both C{bytes}.

    @raise ValueError: If the given data is not a correctly formatted chunked
        byte string.
    """
    prefix, rest = data.split(b'\r\n', 1)
    length = int(prefix, 16)
    if length < 0:
        raise ValueError("Chunk length must be >= 0, not %d" % (length,))
    if rest[length:length + 2] != b'\r\n':
        raise ValueError("chunk must end with CRLF")
    return rest[:length], rest[length + 2:]



def parseContentRange(header):
    """
    Parse a content-range header into (start, end, realLength).

    realLength might be None if real length is not known ('*').
    """
    kind, other = header.strip().split()
    if kind.lower() != "bytes":
        raise ValueError("a range of type %r is not supported")
    startend, realLength = other.split("/")
    start, end = map(int, startend.split("-"))
    if realLength == "*":
        realLength = None
    else:
        realLength = int(realLength)
    return (start, end, realLength)



class StringTransport:
    """
    I am a StringIO wrapper that conforms for the transport API. I support
    the `writeSequence' method.
    """
    def __init__(self):
        self.s = StringIO()
    def writeSequence(self, seq):
        self.s.write(b''.join(seq))
    def __getattr__(self, attr):
        return getattr(self.__dict__['s'], attr)



class HTTPClient(basic.LineReceiver):
    """
    A client for HTTP 1.0.

    Notes:
    You probably want to send a 'Host' header with the name of the site you're
    connecting to, in order to not break name based virtual hosting.

    @ivar length: The length of the request body in bytes.
    @type length: C{int}

    @ivar firstLine: Are we waiting for the first header line?
    @type firstLine: C{bool}

    @ivar __buffer: The buffer that stores the response to the HTTP request.
    @type __buffer: A C{StringIO} object.

    @ivar _header: Part or all of an HTTP request header.
    @type _header: C{bytes}
    """
    length = None
    firstLine = True
    __buffer = None
    _header = b""

    def sendCommand(self, command, path):
        self.transport.writeSequence([command, b' ', path, b' HTTP/1.0\r\n'])

    def sendHeader(self, name, value):
        if not isinstance(value, bytes):
            # XXX Deprecate this case
            value = networkString(str(value))
        self.transport.writeSequence([name, b': ', value, b'\r\n'])

    def endHeaders(self):
        self.transport.write(b'\r\n')


    def extractHeader(self, header):
        """
        Given a complete HTTP header, extract the field name and value and
        process the header.

        @param header: a complete HTTP request header of the form
            'field-name: value'.
        @type header: C{bytes}
        """
        key, val = header.split(b':', 1)
        val = val.lstrip()
        self.handleHeader(key, val)
        if key.lower() == b'content-length':
            self.length = int(val)


    def lineReceived(self, line):
        """
        Parse the status line and headers for an HTTP request.

        @param line: Part of an HTTP request header. Request bodies are parsed
            in L{HTTPClient.rawDataReceived}.
        @type line: C{bytes}
        """
        if self.firstLine:
            self.firstLine = False
            l = line.split(None, 2)
            version = l[0]
            status = l[1]
            try:
                message = l[2]
            except IndexError:
                # sometimes there is no message
                message = b""
            self.handleStatus(version, status, message)
            return
        if not line:
            if self._header != b"":
                # Only extract headers if there are any
                self.extractHeader(self._header)
            self.__buffer = StringIO()
            self.handleEndHeaders()
            self.setRawMode()
            return

        if line.startswith(b'\t') or line.startswith(b' '):
            # This line is part of a multiline header. According to RFC 822, in
            # "unfolding" multiline headers you do not strip the leading
            # whitespace on the continuing line.
            self._header = self._header + line
        elif self._header:
            # This line starts a new header, so process the previous one.
            self.extractHeader(self._header)
            self._header = line
        else: # First header
            self._header = line


    def connectionLost(self, reason):
        self.handleResponseEnd()

    def handleResponseEnd(self):
        """
        The response has been completely received.

        This callback may be invoked more than once per request.
        """
        if self.__buffer is not None:
            b = self.__buffer.getvalue()
            self.__buffer = None
            self.handleResponse(b)

    def handleResponsePart(self, data):
        self.__buffer.write(data)

    def connectionMade(self):
        pass

    def handleStatus(self, version, status, message):
        """
        Called when the status-line is received.

        @param version: e.g. 'HTTP/1.0'
        @param status: e.g. '200'
        @type status: C{bytes}
        @param message: e.g. 'OK'
        """

    def handleHeader(self, key, val):
        """
        Called every time a header is received.
        """

    def handleEndHeaders(self):
        """
        Called when all headers have been received.
        """


    def rawDataReceived(self, data):
        if self.length is not None:
            data, rest = data[:self.length], data[self.length:]
            self.length -= len(data)
        else:
            rest = b''
        self.handleResponsePart(data)
        if self.length == 0:
            self.handleResponseEnd()
            self.setLineMode(rest)



# response codes that must have empty bodies
NO_BODY_CODES = (204, 304)


# Sentinel object that detects people explicitly passing `queued` to Request.
_QUEUED_SENTINEL = object()


@implementer(interfaces.IConsumer)
class Request:
    """
    A HTTP request.

    Subclasses should override the process() method to determine how
    the request will be processed.

    @ivar method: The HTTP method that was used.
    @ivar uri: The full URI that was requested (includes arguments).
    @ivar path: The path only (arguments not included).
    @ivar args: All of the arguments, including URL and POST arguments.
    @type args: A mapping of strings (the argument names) to lists of values.
                i.e., ?foo=bar&foo=baz&quux=spam results in
                {'foo': ['bar', 'baz'], 'quux': ['spam']}.

    @ivar cookies: The cookies that will be sent in the response.
    @type cookies: L{list} of L{bytes}

    @type requestHeaders: L{http_headers.Headers}
    @ivar requestHeaders: All received HTTP request headers.

    @type responseHeaders: L{http_headers.Headers}
    @ivar responseHeaders: All HTTP response headers to be sent.

    @ivar notifications: A C{list} of L{Deferred}s which are waiting for
        notification that the response to this request has been finished
        (successfully or with an error).  Don't use this attribute directly,
        instead use the L{Request.notifyFinish} method.

    @ivar _disconnected: A flag which is C{False} until the connection over
        which this request was received is closed and which is C{True} after
        that.
    @type _disconnected: C{bool}
    """
    producer = None
    finished = 0
    code = OK
    code_message = RESPONSES[OK]
    method = "(no method yet)"
    clientproto = b"(no clientproto yet)"
    uri = "(no uri yet)"
    startedWriting = 0
    chunked = 0
    sentLength = 0 # content-length of response, or total bytes sent via chunking
    etag = None
    lastModified = None
    args = None
    path = None
    content = None
    _forceSSL = 0
    _disconnected = False

    def __init__(self, channel, queued=_QUEUED_SENTINEL):
        """
        @param channel: the channel we're connected to.
        @param queued: (deprecated) are we in the request queue, or can we
            start writing to the transport?
        """
        self.notifications = []
        self.channel = channel
        self.requestHeaders = Headers()
        self.received_cookies = {}
        self.responseHeaders = Headers()
        self.cookies = [] # outgoing cookies
        self.transport = self.channel.transport

        if queued is _QUEUED_SENTINEL:
            queued = False

        self.queued = queued


    def _cleanup(self):
        """
        Called when have finished responding and are no longer queued.
        """
        if self.producer:
            log.err(RuntimeError("Producer was not unregistered for %s" % self.uri))
            self.unregisterProducer()
        self.channel.requestDone(self)
        del self.channel
        if self.content is not None:
            try:
                self.content.close()
            except OSError:
                # win32 suckiness, no idea why it does this
                pass
            del self.content
        for d in self.notifications:
            d.callback(None)
        self.notifications = []

    # methods for channel - end users should not use these

    def noLongerQueued(self):
        """
        Notify the object that it is no longer queued.

        We start writing whatever data we have to the transport, etc.

        This method is not intended for users.

        In 16.3 this method was changed to become a no-op, as L{Request}
        objects are now never queued.
        """
        pass


    def gotLength(self, length):
        """
        Called when HTTP channel got length of content in this request.

        This method is not intended for users.

        @param length: The length of the request body, as indicated by the
            request headers.  L{None} if the request headers do not indicate a
            length.
        """
        if length is not None and length < 100000:
            self.content = StringIO()
        else:
            self.content = tempfile.TemporaryFile()


    def parseCookies(self):
        """
        Parse cookie headers.

        This method is not intended for users.
        """
        cookieheaders = self.requestHeaders.getRawHeaders(b"cookie")

        if cookieheaders is None:
            return

        for cookietxt in cookieheaders:
            if cookietxt:
                for cook in cookietxt.split(b';'):
                    cook = cook.lstrip()
                    try:
                        k, v = cook.split(b'=', 1)
                        self.received_cookies[k] = v
                    except ValueError:
                        pass


    def handleContentChunk(self, data):
        """
        Write a chunk of data.

        This method is not intended for users.
        """
        self.content.write(data)


    def requestReceived(self, command, path, version):
        """
        Called by channel when all data has been received.

        This method is not intended for users.

        @type command: C{bytes}
        @param command: The HTTP verb of this request.  This has the case
            supplied by the client (eg, it maybe "get" rather than "GET").

        @type path: C{bytes}
        @param path: The URI of this request.

        @type version: C{bytes}
        @param version: The HTTP version of this request.
        """
        self.content.seek(0,0)
        self.args = {}

        self.method, self.uri = command, path
        self.clientproto = version
        x = self.uri.split(b'?', 1)

        if len(x) == 1:
            self.path = self.uri
        else:
            self.path, argstring = x
            self.args = parse_qs(argstring, 1)

        # cache the client and server information, we'll need this later to be
        # serialized and sent with the request so CGIs will work remotely
        self.client = self.channel.getPeer()
        self.host = self.channel.getHost()

        # Argument processing
        args = self.args
        ctype = self.requestHeaders.getRawHeaders(b'content-type')
        if ctype is not None:
            ctype = ctype[0]

        if self.method == b"POST" and ctype:
            mfd = b'multipart/form-data'
            key, pdict = _parseHeader(ctype)
            if key == b'application/x-www-form-urlencoded':
                args.update(parse_qs(self.content.read(), 1))
            elif key == mfd:
                try:
                    cgiArgs = cgi.parse_multipart(self.content, pdict)

                    if _PY3:
                        # parse_multipart on Python 3 decodes the header bytes
                        # as iso-8859-1 and returns a str key -- we want bytes
                        # so encode it back
                        self.args.update({x.encode('iso-8859-1'): y
                                          for x, y in cgiArgs.items()})
                    else:
                        self.args.update(cgiArgs)
                except:
                    # It was a bad request.
                    self.channel._respondToBadRequestAndDisconnect()
                    return
            self.content.seek(0, 0)

        self.process()


    def __repr__(self):
        """
        Return a string description of the request including such information
        as the request method and request URI.

        @return: A string loosely describing this L{Request} object.
        @rtype: L{str}
        """
        return '<%s at 0x%x method=%s uri=%s clientproto=%s>' % (
            self.__class__.__name__,
            id(self),
            nativeString(self.method),
            nativeString(self.uri),
            nativeString(self.clientproto))


    def process(self):
        """
        Override in subclasses.

        This method is not intended for users.
        """
        pass


    # consumer interface

    def registerProducer(self, producer, streaming):
        """
        Register a producer.
        """
        if self.producer:
            raise ValueError(
                "registering producer %s before previous one (%s) was "
                "unregistered" % (producer, self.producer))

        self.streamingProducer = streaming
        self.producer = producer
        self.channel.registerProducer(producer, streaming)

    def unregisterProducer(self):
        """
        Unregister the producer.
        """
        self.channel.unregisterProducer()
        self.producer = None


    # The following is the public interface that people should be
    # writing to.
    def getHeader(self, key):
        """
        Get an HTTP request header.

        @type key: C{bytes}
        @param key: The name of the header to get the value of.

        @rtype: C{bytes} or L{None}
        @return: The value of the specified header, or L{None} if that header
            was not present in the request.
        """
        value = self.requestHeaders.getRawHeaders(key)
        if value is not None:
            return value[-1]


    def getCookie(self, key):
        """
        Get a cookie that was sent from the network.
        """
        return self.received_cookies.get(key)


    def notifyFinish(self):
        """
        Notify when the response to this request has finished.

        @rtype: L{Deferred}

        @return: A L{Deferred} which will be triggered when the request is
            finished -- with a L{None} value if the request finishes
            successfully or with an error if the request is interrupted by an
            error (for example, the client closing the connection prematurely).
        """
        self.notifications.append(Deferred())
        return self.notifications[-1]


    def finish(self):
        """
        Indicate that all response data has been written to this L{Request}.
        """
        if self._disconnected:
            raise RuntimeError(
                "Request.finish called on a request after its connection was lost; "
                "use Request.notifyFinish to keep track of this.")
        if self.finished:
            warnings.warn("Warning! request.finish called twice.", stacklevel=2)
            return

        if not self.startedWriting:
            # write headers
            self.write(b'')

        if self.chunked:
            # write last chunk and closing CRLF
            self.channel.write(b"0\r\n\r\n")

        # log request
        if (hasattr(self.channel, "factory") and
                self.channel.factory is not None):
            self.channel.factory.log(self)

        self.finished = 1
        if not self.queued:
            self._cleanup()


    def write(self, data):
        """
        Write some data as a result of an HTTP request.  The first
        time this is called, it writes out response data.

        @type data: C{bytes}
        @param data: Some bytes to be sent as part of the response body.
        """
        if self.finished:
            raise RuntimeError('Request.write called on a request after '
                               'Request.finish was called.')
        if not self.startedWriting:
            self.startedWriting = 1
            version = self.clientproto
            code = intToBytes(self.code)
            reason = self.code_message
            headers = []

            # if we don't have a content length, we send data in
            # chunked mode, so that we can support pipelining in
            # persistent connections.
            if ((version == b"HTTP/1.1") and
                (self.responseHeaders.getRawHeaders(b'content-length') is None) and
                self.method != b"HEAD" and self.code not in NO_BODY_CODES):
                headers.append((b'Transfer-Encoding', b'chunked'))
                self.chunked = 1

            if self.lastModified is not None:
                if self.responseHeaders.hasHeader(b'last-modified'):
                    log.msg("Warning: last-modified specified both in"
                            " header list and lastModified attribute.")
                else:
                    self.responseHeaders.setRawHeaders(
                        b'last-modified',
                        [datetimeToString(self.lastModified)])

            if self.etag is not None:
                self.responseHeaders.setRawHeaders(b'ETag', [self.etag])

            for name, values in self.responseHeaders.getAllRawHeaders():
                for value in values:
                    if not isinstance(value, bytes):
                        warnings.warn(
                            "Passing non-bytes header values is deprecated "
                            "since Twisted 12.3. Pass only bytes instead.",
                            category=DeprecationWarning, stacklevel=2)
                        # Backward compatible cast for non-bytes values
                        value = networkString('%s' % (value,))
                    headers.append((name, value))

            for cookie in self.cookies:
                headers.append((b'Set-Cookie', cookie))

            self.channel.writeHeaders(version, code, reason, headers)

            # if this is a "HEAD" request, we shouldn't return any data
            if self.method == b"HEAD":
                self.write = lambda data: None
                return

            # for certain result codes, we should never return any data
            if self.code in NO_BODY_CODES:
                self.write = lambda data: None
                return

        self.sentLength = self.sentLength + len(data)
        if data:
            if self.chunked:
                self.channel.writeSequence(toChunk(data))
            else:
                self.channel.write(data)

    def addCookie(self, k, v, expires=None, domain=None, path=None,
                  max_age=None, comment=None, secure=None, httpOnly=False):
        """
        Set an outgoing HTTP cookie.

        In general, you should consider using sessions instead of cookies, see
        L{twisted.web.server.Request.getSession} and the
        L{twisted.web.server.Session} class for details.

        @param k: cookie name
        @type k: L{bytes} or L{unicode}

        @param v: cookie value
        @type v: L{bytes} or L{unicode}

        @param expires: cookie expire attribute value in
            "Wdy, DD Mon YYYY HH:MM:SS GMT" format
        @type expires: L{bytes} or L{unicode}

        @param domain: cookie domain
        @type domain: L{bytes} or L{unicode}

        @param path: cookie path
        @type path: L{bytes} or L{unicode}

        @param max_age: cookie expiration in seconds from reception
        @type max_age: L{bytes} or L{unicode}

        @param comment: cookie comment
        @type comment: L{bytes} or L{unicode}

        @param secure: direct browser to send the cookie on encrypted
            connections only
        @type secure: L{bool}

        @param httpOnly: direct browser not to expose cookies through channels
            other than HTTP (and HTTPS) requests
        @type httpOnly: L{bool}

        @raises: L{DeprecationWarning} if an argument is not L{bytes} or
            L{unicode}.
        """
        def _ensureBytes(val):
            """
            Ensure that C{val} is bytes, encoding using UTF-8 if needed.
            """
            if val is None:
                # It's None, so we don't want to touch it
                return val

            if isinstance(val, bytes):
                return val
            elif isinstance(val, unicode):
                return val.encode('utf8')

            # Not bytes or unicode, relying on string conversion legacy
            # str() it, and warn, it's the best we can do
            warnings.warn(
                "Passing non-bytes or non-unicode cookie arguments is "
                "deprecated since Twisted 16.1.",
                category=DeprecationWarning, stacklevel=3)

            return str(val).encode('utf8')

        cookie = _ensureBytes(k) + b"=" + _ensureBytes(v)
        if expires is not None:
            cookie = cookie + b"; Expires=" + _ensureBytes(expires)
        if domain is not None:
            cookie = cookie + b"; Domain=" + _ensureBytes(domain)
        if path is not None:
            cookie = cookie + b"; Path=" + _ensureBytes(path)
        if max_age is not None:
            cookie = cookie + b"; Max-Age=" + _ensureBytes(max_age)
        if comment is not None:
            cookie = cookie + b"; Comment=" + _ensureBytes(comment)
        if secure:
            cookie = cookie + b"; Secure"
        if httpOnly:
            cookie = cookie + b"; HttpOnly"
        self.cookies.append(cookie)

    def setResponseCode(self, code, message=None):
        """
        Set the HTTP response code.

        @type code: C{int}
        @type message: C{bytes}
        """
        if not isinstance(code, _intTypes):
            raise TypeError("HTTP response code must be int or long")
        self.code = code
        if message:
            if not isinstance(message, bytes):
                raise TypeError("HTTP response status message must be bytes")
            self.code_message = message
        else:
            self.code_message = RESPONSES.get(code, b"Unknown Status")


    def setHeader(self, name, value):
        """
        Set an HTTP response header.  Overrides any previously set values for
        this header.

        @type name: C{bytes}
        @param name: The name of the header for which to set the value.

        @type value: C{bytes}
        @param value: The value to set for the named header.
        """
        self.responseHeaders.setRawHeaders(name, [value])


    def redirect(self, url):
        """
        Utility function that does a redirect.

        The request should have finish() called after this.
        """
        self.setResponseCode(FOUND)
        self.setHeader(b"location", url)


    def setLastModified(self, when):
        """
        Set the C{Last-Modified} time for the response to this request.

        If I am called more than once, I ignore attempts to set
        Last-Modified earlier, only replacing the Last-Modified time
        if it is to a later value.

        If I am a conditional request, I may modify my response code
        to L{NOT_MODIFIED} if appropriate for the time given.

        @param when: The last time the resource being returned was
            modified, in seconds since the epoch.
        @type when: number
        @return: If I am a C{If-Modified-Since} conditional request and
            the time given is not newer than the condition, I return
            L{http.CACHED<CACHED>} to indicate that you should write no
            body.  Otherwise, I return a false value.
        """
        # time.time() may be a float, but the HTTP-date strings are
        # only good for whole seconds.
        when = int(math.ceil(when))
        if (not self.lastModified) or (self.lastModified < when):
            self.lastModified = when

        modifiedSince = self.getHeader(b'if-modified-since')
        if modifiedSince:
            firstPart = modifiedSince.split(b';', 1)[0]
            try:
                modifiedSince = stringToDatetime(firstPart)
            except ValueError:
                return None
            if modifiedSince >= self.lastModified:
                self.setResponseCode(NOT_MODIFIED)
                return CACHED
        return None

    def setETag(self, etag):
        """
        Set an C{entity tag} for the outgoing response.

        That's \"entity tag\" as in the HTTP/1.1 C{ETag} header, \"used
        for comparing two or more entities from the same requested
        resource.\"

        If I am a conditional request, I may modify my response code
        to L{NOT_MODIFIED} or L{PRECONDITION_FAILED}, if appropriate
        for the tag given.

        @param etag: The entity tag for the resource being returned.
        @type etag: string
        @return: If I am a C{If-None-Match} conditional request and
            the tag matches one in the request, I return
            L{http.CACHED<CACHED>} to indicate that you should write
            no body.  Otherwise, I return a false value.
        """
        if etag:
            self.etag = etag

        tags = self.getHeader(b"if-none-match")
        if tags:
            tags = tags.split()
            if (etag in tags) or (b'*' in tags):
                self.setResponseCode(((self.method in (b"HEAD", b"GET"))
                                      and NOT_MODIFIED)
                                     or PRECONDITION_FAILED)
                return CACHED
        return None


    def getAllHeaders(self):
        """
        Return dictionary mapping the names of all received headers to the last
        value received for each.

        Since this method does not return all header information,
        C{self.requestHeaders.getAllRawHeaders()} may be preferred.
        """
        headers = {}
        for k, v in self.requestHeaders.getAllRawHeaders():
            headers[k.lower()] = v[-1]
        return headers


    def getRequestHostname(self):
        """
        Get the hostname that the user passed in to the request.

        This will either use the Host: header (if it is available) or the
        host we are listening on if the header is unavailable.

        @returns: the requested hostname
        @rtype: C{bytes}
        """
        # XXX This method probably has no unit tests.  I changed it a ton and
        # nothing failed.
        host = self.getHeader(b'host')
        if host:
            return host.split(b':', 1)[0]
        return networkString(self.getHost().host)


    def getHost(self):
        """
        Get my originally requesting transport's host.

        Don't rely on the 'transport' attribute, since Request objects may be
        copied remotely.  For information on this method's return value, see
        L{twisted.internet.tcp.Port}.
        """
        return self.host

    def setHost(self, host, port, ssl=0):
        """
        Change the host and port the request thinks it's using.

        This method is useful for working with reverse HTTP proxies (e.g.
        both Squid and Apache's mod_proxy can do this), when the address
        the HTTP client is using is different than the one we're listening on.

        For example, Apache may be listening on https://www.example.com/, and
        then forwarding requests to http://localhost:8080/, but we don't want
        HTML produced by Twisted to say b'http://localhost:8080/', they should
        say b'https://www.example.com/', so we do::

           request.setHost(b'www.example.com', 443, ssl=1)

        @type host: C{bytes}
        @param host: The value to which to change the host header.

        @type ssl: C{bool}
        @param ssl: A flag which, if C{True}, indicates that the request is
            considered secure (if C{True}, L{isSecure} will return C{True}).
        """
        self._forceSSL = ssl # set first so isSecure will work
        if self.isSecure():
            default = 443
        else:
            default = 80
        if port == default:
            hostHeader = host
        else:
            hostHeader = host + b":" + intToBytes(port)
        self.requestHeaders.setRawHeaders(b"host", [hostHeader])
        self.host = address.IPv4Address("TCP", host, port)


    def getClientIP(self):
        """
        Return the IP address of the client who submitted this request.

        @returns: the client IP address
        @rtype: C{str}
        """
        if isinstance(self.client, address.IPv4Address):
            return self.client.host
        else:
            return None

    def isSecure(self):
        """
        Return L{True} if this request is using a secure transport.

        Normally this method returns L{True} if this request's L{HTTPChannel}
        instance is using a transport that implements
        L{interfaces.ISSLTransport}.

        This will also return L{True} if L{Request.setHost} has been called
        with C{ssl=True}.

        @returns: L{True} if this request is secure
        @rtype: C{bool}
        """
        if self._forceSSL:
            return True
        channel = getattr(self, 'channel', None)
        if channel is None:
            return False
        return channel.isSecure()


    def _authorize(self):
        # Authorization, (mostly) per the RFC
        try:
            authh = self.getHeader(b"Authorization")
            if not authh:
                self.user = self.password = ''
                return
            bas, upw = authh.split()
            if bas.lower() != b"basic":
                raise ValueError()
            upw = base64.decodestring(upw)
            self.user, self.password = upw.split(b':', 1)
        except (binascii.Error, ValueError):
            self.user = self.password = ""
        except:
            log.err()
            self.user = self.password = ""


    def getUser(self):
        """
        Return the HTTP user sent with this request, if any.

        If no user was supplied, return the empty string.

        @returns: the HTTP user, if any
        @rtype: C{bytes}
        """
        try:
            return self.user
        except:
            pass
        self._authorize()
        return self.user


    def getPassword(self):
        """
        Return the HTTP password sent with this request, if any.

        If no password was supplied, return the empty string.

        @returns: the HTTP password, if any
        @rtype: C{bytes}
        """
        try:
            return self.password
        except:
            pass
        self._authorize()
        return self.password


    def getClient(self):
        """
        Get the client's IP address, if it has one.  No attempt is made to
        resolve the address to a hostname.

        @return: The same value as C{getClientIP}.
        @rtype: L{bytes}
        """
        return self.getClientIP()


    def connectionLost(self, reason):
        """
        There is no longer a connection for this request to respond over.
        Clean up anything which can't be useful anymore.
        """
        self._disconnected = True
        self.channel = None
        if self.content is not None:
            self.content.close()
        for d in self.notifications:
            d.errback(reason)
        self.notifications = []


    def loseConnection(self):
        """
        Pass the loseConnection through to the underlying channel.
        """
        self.channel.loseConnection()


Request.getClient = deprecated(
    Version("Twisted", 15, 0, 0),
    "Twisted Names to resolve hostnames")(Request.getClient)


Request.noLongerQueued = deprecated(
    Version("Twisted", 16, 3, 0))(Request.noLongerQueued)


class _DataLoss(Exception):
    """
    L{_DataLoss} indicates that not all of a message body was received. This
    is only one of several possible exceptions which may indicate that data
    was lost.  Because of this, it should not be checked for by
    specifically; any unexpected exception should be treated as having
    caused data loss.
    """



class PotentialDataLoss(Exception):
    """
    L{PotentialDataLoss} may be raised by a transfer encoding decoder's
    C{noMoreData} method to indicate that it cannot be determined if the
    entire response body has been delivered.  This only occurs when making
    requests to HTTP servers which do not set I{Content-Length} or a
    I{Transfer-Encoding} in the response because in this case the end of the
    response is indicated by the connection being closed, an event which may
    also be due to a transient network problem or other error.
    """



class _MalformedChunkedDataError(Exception):
    """
    C{_ChunkedTranferDecoder} raises L{_MalformedChunkedDataError} from its
    C{dataReceived} method when it encounters malformed data. This exception
    indicates a client-side error. If this exception is raised, the connection
    should be dropped with a 400 error.
    """



class _IdentityTransferDecoder(object):
    """
    Protocol for accumulating bytes up to a specified length.  This handles the
    case where no I{Transfer-Encoding} is specified.

    @ivar contentLength: Counter keeping track of how many more bytes there are
        to receive.

    @ivar dataCallback: A one-argument callable which will be invoked each
        time application data is received.

    @ivar finishCallback: A one-argument callable which will be invoked when
        the terminal chunk is received.  It will be invoked with all bytes
        which were delivered to this protocol which came after the terminal
        chunk.
    """
    def __init__(self, contentLength, dataCallback, finishCallback):
        self.contentLength = contentLength
        self.dataCallback = dataCallback
        self.finishCallback = finishCallback


    def dataReceived(self, data):
        """
        Interpret the next chunk of bytes received.  Either deliver them to the
        data callback or invoke the finish callback if enough bytes have been
        received.

        @raise RuntimeError: If the finish callback has already been invoked
            during a previous call to this methood.
        """
        if self.dataCallback is None:
            raise RuntimeError(
                "_IdentityTransferDecoder cannot decode data after finishing")

        if self.contentLength is None:
            self.dataCallback(data)
        elif len(data) < self.contentLength:
            self.contentLength -= len(data)
            self.dataCallback(data)
        else:
            # Make the state consistent before invoking any code belonging to
            # anyone else in case noMoreData ends up being called beneath this
            # stack frame.
            contentLength = self.contentLength
            dataCallback = self.dataCallback
            finishCallback = self.finishCallback
            self.dataCallback = self.finishCallback = None
            self.contentLength = 0

            dataCallback(data[:contentLength])
            finishCallback(data[contentLength:])


    def noMoreData(self):
        """
        All data which will be delivered to this decoder has been.  Check to
        make sure as much data as was expected has been received.

        @raise PotentialDataLoss: If the content length is unknown.
        @raise _DataLoss: If the content length is known and fewer than that
            many bytes have been delivered.

        @return: L{None}
        """
        finishCallback = self.finishCallback
        self.dataCallback = self.finishCallback = None
        if self.contentLength is None:
            finishCallback(b'')
            raise PotentialDataLoss()
        elif self.contentLength != 0:
            raise _DataLoss()



class _ChunkedTransferDecoder(object):
    """
    Protocol for decoding I{chunked} Transfer-Encoding, as defined by RFC 2616,
    section 3.6.1.  This protocol can interpret the contents of a request or
    response body which uses the I{chunked} Transfer-Encoding.  It cannot
    interpret any of the rest of the HTTP protocol.

    It may make sense for _ChunkedTransferDecoder to be an actual IProtocol
    implementation.  Currently, the only user of this class will only ever
    call dataReceived on it.  However, it might be an improvement if the
    user could connect this to a transport and deliver connection lost
    notification.  This way, `dataCallback` becomes `self.transport.write`
    and perhaps `finishCallback` becomes `self.transport.loseConnection()`
    (although I'm not sure where the extra data goes in that case).  This
    could also allow this object to indicate to the receiver of data that
    the stream was not completely received, an error case which should be
    noticed. -exarkun

    @ivar dataCallback: A one-argument callable which will be invoked each
        time application data is received.

    @ivar finishCallback: A one-argument callable which will be invoked when
        the terminal chunk is received.  It will be invoked with all bytes
        which were delivered to this protocol which came after the terminal
        chunk.

    @ivar length: Counter keeping track of how many more bytes in a chunk there
        are to receive.

    @ivar state: One of C{'CHUNK_LENGTH'}, C{'CRLF'}, C{'TRAILER'},
        C{'BODY'}, or C{'FINISHED'}.  For C{'CHUNK_LENGTH'}, data for the
        chunk length line is currently being read.  For C{'CRLF'}, the CR LF
        pair which follows each chunk is being read. For C{'TRAILER'}, the CR
        LF pair which follows the terminal 0-length chunk is currently being
        read. For C{'BODY'}, the contents of a chunk are being read. For
        C{'FINISHED'}, the last chunk has been completely read and no more
        input is valid.
    """
    state = 'CHUNK_LENGTH'

    def __init__(self, dataCallback, finishCallback):
        self.dataCallback = dataCallback
        self.finishCallback = finishCallback
        self._buffer = b''


    def _dataReceived_CHUNK_LENGTH(self, data):
        if b'\r\n' in data:
            line, rest = data.split(b'\r\n', 1)
            parts = line.split(b';')
            try:
                self.length = int(parts[0], 16)
            except ValueError:
                raise _MalformedChunkedDataError(
                    "Chunk-size must be an integer.")
            if self.length == 0:
                self.state = 'TRAILER'
            else:
                self.state = 'BODY'
            return rest
        else:
            self._buffer = data
            return b''


    def _dataReceived_CRLF(self, data):
        if data.startswith(b'\r\n'):
            self.state = 'CHUNK_LENGTH'
            return data[2:]
        else:
            self._buffer = data
            return b''


    def _dataReceived_TRAILER(self, data):
        if data.startswith(b'\r\n'):
            data = data[2:]
            self.state = 'FINISHED'
            self.finishCallback(data)
        else:
            self._buffer = data
        return b''


    def _dataReceived_BODY(self, data):
        if len(data) >= self.length:
            chunk, data = data[:self.length], data[self.length:]
            self.dataCallback(chunk)
            self.state = 'CRLF'
            return data
        elif len(data) < self.length:
            self.length -= len(data)
            self.dataCallback(data)
            return b''


    def _dataReceived_FINISHED(self, data):
        raise RuntimeError(
            "_ChunkedTransferDecoder.dataReceived called after last "
            "chunk was processed")


    def dataReceived(self, data):
        """
        Interpret data from a request or response body which uses the
        I{chunked} Transfer-Encoding.
        """
        data = self._buffer + data
        self._buffer = b''
        while data:
            data = getattr(self, '_dataReceived_%s' % (self.state,))(data)


    def noMoreData(self):
        """
        Verify that all data has been received.  If it has not been, raise
        L{_DataLoss}.
        """
        if self.state != 'FINISHED':
            raise _DataLoss(
                "Chunked decoder in %r state, still expecting more data to "
                "get to 'FINISHED' state." % (self.state,))



@implementer(interfaces.IPushProducer)
class _NoPushProducer(object):
    """
    A no-op version of L{interfaces.IPushProducer}, used to abstract over the
    possibility that a L{HTTPChannel} transport does not provide
    L{IPushProducer}.
    """
    def pauseProducing(self):
        """
        Pause producing data.

        Tells a producer that it has produced too much data to process for
        the time being, and to stop until resumeProducing() is called.
        """
        pass


    def resumeProducing(self):
        """
        Resume producing data.

        This tells a producer to re-add itself to the main loop and produce
        more data for its consumer.
        """
        pass



@implementer(interfaces.ITransport)
class HTTPChannel(basic.LineReceiver, policies.TimeoutMixin):
    """
    A receiver for HTTP requests.

    @ivar MAX_LENGTH: Maximum length for initial request line and each line
        from the header.

    @ivar _transferDecoder: L{None} or a decoder instance if the request body
        uses the I{chunked} Transfer-Encoding.
    @type _transferDecoder: L{_ChunkedTransferDecoder}

    @ivar maxHeaders: Maximum number of headers allowed per request.
    @type maxHeaders: C{int}

    @ivar totalHeadersSize: Maximum bytes for request line plus all headers
        from the request.
    @type totalHeadersSize: C{int}

    @ivar _receivedHeaderSize: Bytes received so far for the header.
    @type _receivedHeaderSize: C{int}

    @ivar _handlingRequest: Whether a request is currently being processed.
    @type _handlingRequest: L{bool}

    @ivar _dataBuffer: Any data that has been received from the connection
        while processing an outstanding request.
    @type _dataBuffer: L{list} of L{bytes}

    @ivar _producer: Either the transport, if it provides
        L{interfaces.IPushProducer}, or a null implementation of
        L{interfaces.IPushProducer}. Used to attempt to prevent the transport
        from producing excess data when we're responding to a request.
    @type _producer: L{interfaces.IPushProducer}
    """

    maxHeaders = 500
    totalHeadersSize = 16384

    length = 0
    persistent = 1
    __header = ''
    __first_line = 1
    __content = None

    # set in instances or subclasses
    requestFactory = Request

    _savedTimeOut = None
    _receivedHeaderCount = 0
    _receivedHeaderSize = 0

    def __init__(self):
        # the request queue
        self.requests = []
        self._handlingRequest = False
        self._dataBuffer = []
        self._transferDecoder = None


    def connectionMade(self):
        self.setTimeout(self.timeOut)
        self._producer = interfaces.IPushProducer(
            self.transport, _NoPushProducer()
        )


    def lineReceived(self, line):
        """
        Called for each line from request until the end of headers when
        it enters binary mode.
        """
        self.resetTimeout()

        self._receivedHeaderSize += len(line)
        if (self._receivedHeaderSize > self.totalHeadersSize):
            self._respondToBadRequestAndDisconnect()
            return

        # If we're currently handling a request, buffer this data. We shouldn't
        # have received it (we've paused the transport), but let's be cautious.
        if self._handlingRequest:
            self._dataBuffer.append(line)
            self._dataBuffer.append(b'\r\n')
            return

        if self.__first_line:
            # if this connection is not persistent, drop any data which
            # the client (illegally) sent after the last request.
            if not self.persistent:
                self.dataReceived = self.lineReceived = lambda *args: None
                return

            # IE sends an extraneous empty line (\r\n) after a POST request;
            # eat up such a line, but only ONCE
            if not line and self.__first_line == 1:
                self.__first_line = 2
                return

            # create a new Request object
            if INonQueuedRequestFactory.providedBy(self.requestFactory):
                request = self.requestFactory(self)
            else:
                request = self.requestFactory(self, len(self.requests))
            self.requests.append(request)

            self.__first_line = 0

            parts = line.split()
            if len(parts) != 3:
                self._respondToBadRequestAndDisconnect()
                return
            command, request, version = parts
            try:
                command.decode("ascii")
            except UnicodeDecodeError:
                self._respondToBadRequestAndDisconnect()
                return

            self._command = command
            self._path = request
            self._version = version
        elif line == b'':
            # End of headers.
            if self.__header:
                ok = self.headerReceived(self.__header)
                # If the last header we got is invalid, we MUST NOT proceed
                # with processing. We'll have sent a 400 anyway, so just stop.
                if not ok:
                    return
            self.__header = ''
            self.allHeadersReceived()
            if self.length == 0:
                self.allContentReceived()
            else:
                self.setRawMode()
        elif line[0] in b' \t':
            # Continuation of a multi line header.
            self.__header = self.__header + '\n' + line
        # Regular header line.
        # Processing of header line is delayed to allow accumulating multi
        # line headers.
        else:
            if self.__header:
                self.headerReceived(self.__header)
            self.__header = line


    def _finishRequestBody(self, data):
        self.allContentReceived()
        self._dataBuffer.append(data)


    def headerReceived(self, line):
        """
        Do pre-processing (for content-length) and store this header away.
        Enforce the per-request header limit.

        @type line: C{bytes}
        @param line: A line from the header section of a request, excluding the
            line delimiter.

        @return: A flag indicating whether the header was valid.
        @rtype: L{bool}
        """
        try:
            header, data = line.split(b':', 1)
        except ValueError:
            self._respondToBadRequestAndDisconnect()
            return False

        header = header.lower()
        data = data.strip()
        if header == b'content-length':
            try:
                self.length = int(data)
            except ValueError:
                self._respondToBadRequestAndDisconnect()
                self.length = None
                return False
            self._transferDecoder = _IdentityTransferDecoder(
                self.length, self.requests[-1].handleContentChunk, self._finishRequestBody)
        elif header == b'transfer-encoding' and data.lower() == b'chunked':
            # XXX Rather poorly tested code block, apparently only exercised by
            # test_chunkedEncoding
            self.length = None
            self._transferDecoder = _ChunkedTransferDecoder(
                self.requests[-1].handleContentChunk, self._finishRequestBody)
        reqHeaders = self.requests[-1].requestHeaders
        values = reqHeaders.getRawHeaders(header)
        if values is not None:
            values.append(data)
        else:
            reqHeaders.setRawHeaders(header, [data])

        self._receivedHeaderCount += 1
        if self._receivedHeaderCount > self.maxHeaders:
            self._respondToBadRequestAndDisconnect()
            return False

        return True


    def allContentReceived(self):
        command = self._command
        path = self._path
        version = self._version

        # reset ALL state variables, so we don't interfere with next request
        self.length = 0
        self._receivedHeaderCount = 0
        self._receivedHeaderSize = 0
        self.__first_line = 1
        self._transferDecoder = None
        del self._command, self._path, self._version

        # Disable the idle timeout, in case this request takes a long
        # time to finish generating output.
        if self.timeOut:
            self._savedTimeOut = self.setTimeout(None)

        # Pause the producer if we can. If we can't, that's ok, we'll buffer.
        self._producer.pauseProducing()
        self._handlingRequest = True

        req = self.requests[-1]
        req.requestReceived(command, path, version)


    def rawDataReceived(self, data):
        self.resetTimeout()

        # If we're currently handling a request, buffer this data. We shouldn't
        # have received it (we've paused the transport), but let's be cautious.
        if self._handlingRequest:
            self._dataBuffer.append(data)
            return

        try:
            self._transferDecoder.dataReceived(data)
        except _MalformedChunkedDataError:
            self._respondToBadRequestAndDisconnect()


    def allHeadersReceived(self):
        req = self.requests[-1]
        req.parseCookies()
        self.persistent = self.checkPersistence(req, self._version)
        req.gotLength(self.length)
        # Handle 'Expect: 100-continue' with automated 100 response code,
        # a simplistic implementation of RFC 2686 8.2.3:
        expectContinue = req.requestHeaders.getRawHeaders(b'expect')
        if (expectContinue and expectContinue[0].lower() == b'100-continue' and
            self._version == b'HTTP/1.1'):
            self._send100Continue()


    def checkPersistence(self, request, version):
        """
        Check if the channel should close or not.

        @param request: The request most recently received over this channel
            against which checks will be made to determine if this connection
            can remain open after a matching response is returned.

        @type version: C{bytes}
        @param version: The version of the request.

        @rtype: C{bool}
        @return: A flag which, if C{True}, indicates that this connection may
            remain open to receive another request; if C{False}, the connection
            must be closed in order to indicate the completion of the response
            to C{request}.
        """
        connection = request.requestHeaders.getRawHeaders(b'connection')
        if connection:
            tokens = [t.lower() for t in connection[0].split(b' ')]
        else:
            tokens = []

        # Once any HTTP 0.9 or HTTP 1.0 request is received, the connection is
        # no longer allowed to be persistent.  At this point in processing the
        # request, we don't yet know if it will be possible to set a
        # Content-Length in the response.  If it is not, then the connection
        # will have to be closed to end an HTTP 0.9 or HTTP 1.0 response.

        # If the checkPersistence call happened later, after the Content-Length
        # has been determined (or determined not to be set), it would probably
        # be possible to have persistent connections with HTTP 0.9 and HTTP 1.0.
        # This may not be worth the effort, though.  Just use HTTP 1.1, okay?

        if version == b"HTTP/1.1":
            if b'close' in tokens:
                request.responseHeaders.setRawHeaders(b'connection', [b'close'])
                return False
            else:
                return True
        else:
            return False


    def requestDone(self, request):
        """
        Called by first request in queue when it is done.
        """
        if request != self.requests[0]: raise TypeError
        del self.requests[0]

        self._producer.resumeProducing()

        if self.persistent:
            self._handlingRequest = False

            if self._savedTimeOut:
                self.setTimeout(self._savedTimeOut)

            # Receive our buffered data, if any.
            data = b''.join(self._dataBuffer)
            self._dataBuffer = []
            self.setLineMode(data)
        else:
            self.transport.loseConnection()


    def timeoutConnection(self):
        log.msg("Timing out client: %s" % str(self.transport.getPeer()))
        policies.TimeoutMixin.timeoutConnection(self)


    def connectionLost(self, reason):
        self.setTimeout(None)
        for request in self.requests:
            request.connectionLost(reason)


    def isSecure(self):
        """
        Return L{True} if this channel is using a secure transport.

        Normally this method returns L{True} if this instance is using a
        transport that implements L{interfaces.ISSLTransport}.

        @returns: L{True} if this request is secure
        @rtype: C{bool}
        """
        if interfaces.ISSLTransport(self.transport, None) is not None:
            return True
        return False


    def writeHeaders(self, version, code, reason, headers):
        """
        Called by L{Request} objects to write a complete set of HTTP headers to
        a transport.

        @param version: The HTTP version in use.
        @type version: L{bytes}

        @param code: The HTTP status code to write.
        @type code: L{bytes}

        @param reason: The HTTP reason phrase to write.
        @type reason: L{bytes}

        @param headers: The headers to write to the transport.
        @type headers: L{twisted.web.http_headers.Headers}
        """
        responseLine = version + b" " + code + b" " + reason + b"\r\n"
        headerSequence = [responseLine]
        headerSequence.extend(
            name + b': ' + value + b"\r\n" for name, value in headers
        )
        headerSequence.append(b"\r\n")
        self.transport.writeSequence(headerSequence)


    def write(self, data):
        """
        Called by L{Request} objects to write response data.

        @param data: The data chunk to write to the stream.
        @type data: L{bytes}

        @return: L{None}
        """
        self.transport.write(data)


    def writeSequence(self, iovec):
        """
        Write a list of strings to the HTTP response.

        @param iovec: A list of byte strings to write to the stream.
        @type data: L{list} of L{bytes}

        @return: L{None}
        """
        self.transport.writeSequence(iovec)


    def getPeer(self):
        """
        Get the remote address of this connection.

        @return: An L{IAddress} provider.
        """
        return self.transport.getPeer()


    def getHost(self):
        """
        Get the local address of this connection.

        @return: An L{IAddress} provider.
        """
        return self.transport.getHost()


    def loseConnection(self):
        """
        Closes the connection. Will write any data that is pending to be sent
        on the network, but if this response has not yet been written to the
        network will not write anything.

        @return: L{None}
        """
        return self.transport.loseConnection()


    def registerProducer(self, producer, streaming):
        """
        Register to receive data from a producer.

        This sets self to be a consumer for a producer.  When this object runs
        out of data (as when a send(2) call on a socket succeeds in moving the
        last data from a userspace buffer into a kernelspace buffer), it will
        ask the producer to resumeProducing().

        For L{IPullProducer} providers, C{resumeProducing} will be called once
        each time data is required.

        For L{IPushProducer} providers, C{pauseProducing} will be called
        whenever the write buffer fills up and C{resumeProducing} will only be
        called when it empties.

        @type producer: L{IProducer} provider
        @param producer: The L{IProducer} that will be producing data.

        @type streaming: L{bool}
        @param streaming: C{True} if C{producer} provides L{IPushProducer},
        C{False} if C{producer} provides L{IPullProducer}.

        @raise RuntimeError: If a producer is already registered.

        @return: L{None}
        """
        return self.transport.registerProducer(producer, streaming)


    def unregisterProducer(self):
        """
        Stop consuming data from a producer, without disconnecting.

        @return: L{None}
        """
        return self.transport.unregisterProducer()


    def _send100Continue(self):
        """
        Sends a 100 Continue response, used to signal to clients that further
        processing will be performed.
        """
        self.transport.write(b"HTTP/1.1 100 Continue\r\n\r\n")


    def _respondToBadRequestAndDisconnect(self):
        """
        This is a quick and dirty way of responding to bad requests.

        As described by HTTP standard we should be patient and accept the
        whole request from the client before sending a polite bad request
        response, even in the case when clients send tons of data.

        @param transport: Transport handling connection to the client.
        @type transport: L{interfaces.ITransport}
        """
        self.transport.write(b"HTTP/1.1 400 Bad Request\r\n\r\n")
        self.transport.loseConnection()



def _escape(s):
    """
    Return a string like python repr, but always escaped as if surrounding
    quotes were double quotes.

    @param s: The string to escape.
    @type s: L{bytes} or L{unicode}

    @return: An escaped string.
    @rtype: L{unicode}
    """
    if not isinstance(s, bytes):
        s = s.encode("ascii")

    r = repr(s)
    if not isinstance(r, unicode):
        r = r.decode("ascii")
    if r.startswith(u"b"):
        r = r[1:]
    if r.startswith(u"'"):
        return r[1:-1].replace(u'"', u'\\"').replace(u"\\'", u"'")
    return r[1:-1]



@provider(IAccessLogFormatter)
def combinedLogFormatter(timestamp, request):
    """
    @return: A combined log formatted log line for the given request.

    @see: L{IAccessLogFormatter}
    """
    referrer = _escape(request.getHeader(b"referer") or b"-")
    agent = _escape(request.getHeader(b"user-agent") or b"-")
    line = (
        u'"%(ip)s" - - %(timestamp)s "%(method)s %(uri)s %(protocol)s" '
        u'%(code)d %(length)s "%(referrer)s" "%(agent)s"' % dict(
            ip=_escape(request.getClientIP() or b"-"),
            timestamp=timestamp,
            method=_escape(request.method),
            uri=_escape(request.uri),
            protocol=_escape(request.clientproto),
            code=request.code,
            length=request.sentLength or u"-",
            referrer=referrer,
            agent=agent,
            ))
    return line



class _XForwardedForRequest(proxyForInterface(IRequest, "_request")):
    """
    Add a layer on top of another request that only uses the value of an
    X-Forwarded-For header as the result of C{getClientIP}.
    """
    def getClientIP(self):
        """
        @return: The client address (the first address) in the value of the
            I{X-Forwarded-For header}.  If the header is not present, return
            C{b"-"}.
        """
        return self._request.requestHeaders.getRawHeaders(
            b"x-forwarded-for", [b"-"])[0].split(b",")[0].strip()

    # These are missing from the interface.  Forward them manually.
    @property
    def clientproto(self):
        """
        @return: The protocol version in the request.
        @rtype: L{bytes}
        """
        return self._request.clientproto

    @property
    def code(self):
        """
        @return: The response code for the request.
        @rtype: L{int}
        """
        return self._request.code

    @property
    def sentLength(self):
        """
        @return: The number of bytes sent in the response body.
        @rtype: L{int}
        """
        return self._request.sentLength



@provider(IAccessLogFormatter)
def proxiedLogFormatter(timestamp, request):
    """
    @return: A combined log formatted log line for the given request but use
        the value of the I{X-Forwarded-For} header as the value for the client
        IP address.

    @see: L{IAccessLogFormatter}
    """
    return combinedLogFormatter(timestamp, _XForwardedForRequest(request))



class _GenericHTTPChannelProtocol(proxyForInterface(IProtocol, "_channel")):
    """
    A proxy object that wraps one of the HTTP protocol objects, and switches
    between them depending on TLS negotiated protocol.

    @ivar _negotiatedProtocol: The protocol negotiated with ALPN or NPN, if
        any.
    @type _negotiatedProtocol: Either a bytestring containing the ALPN token
        for the negotiated protocol, or L{None} if no protocol has yet been
        negotiated.

    @ivar _channel: The object capable of behaving like a L{HTTPChannel} that
        is backing this object. By default this is a L{HTTPChannel}, but if a
        HTTP protocol upgrade takes place this may be a different channel
        object. Must implement L{IProtocol}.
    @type _channel: L{HTTPChannel}

    @ivar _requestFactory: A callable to use to build L{IRequest} objects.
    @type _requestFactory: L{IRequest}

    @ivar _site: A reference to the creating L{twisted.web.server.Site} object.
    @type _site: L{twisted.web.server.Site}

    @ivar _factory: A reference to the creating L{HTTPFactory} object.
    @type _factory: L{HTTPFactory}

    @ivar _timeOut: A timeout value to pass to the backing channel.
    @type _timeOut: L{int} or L{None}
    """
    _negotiatedProtocol = None
    _requestFactory = Request
    _factory = None
    _site = None
    _timeOut = None


    @property
    def factory(self):
        """
        @see: L{_genericHTTPChannelProtocolFactory}
        """
        return self._channel.factory


    @factory.setter
    def factory(self, value):
        self._factory = value
        self._channel.factory = value


    @property
    def requestFactory(self):
        return self._channel.requestFactory


    @requestFactory.setter
    def requestFactory(self, value):
        self._requestFactory = value
        self._channel.requestFactory = value


    @property
    def site(self):
        return self._channel.site


    @site.setter
    def site(self, value):
        self._site = value
        self._channel.site = value


    @property
    def timeOut(self):
        return self._channel.timeOut


    @timeOut.setter
    def timeOut(self, value):
        self._timeOut = value
        self._channel.timeOut = value


    def dataReceived(self, data):
        """
        An override of L{IProtocol.dataReceived} that checks what protocol we're
        using.
        """
        if self._negotiatedProtocol is None:
            try:
                negotiatedProtocol = self._channel.transport.negotiatedProtocol
            except AttributeError:
                # Plaintext HTTP, always HTTP/1.1
                negotiatedProtocol = b'http/1.1'

            if negotiatedProtocol is None:
                negotiatedProtocol = b'http/1.1'

            if negotiatedProtocol == b'h2':
                if not H2_ENABLED:
                    raise ValueError("Neogitated HTTP/2 without support.")

                transport = self._channel.transport
                self._channel = H2Connection()
                self._channel.requestFactory = self._requestFactory
                self._channel.site = self._site
                self._channel.factory = self._factory
                self._channel.timeOut = self._timeOut
                self._channel.makeConnection(transport)
            else:
                # Only HTTP/2 and HTTP/1.1 are supported right now.
                assert negotiatedProtocol == b'http/1.1', \
                       "Unsupported protocol negotiated"

            self._negotiatedProtocol = negotiatedProtocol

        return self._channel.dataReceived(data)



def _genericHTTPChannelProtocolFactory(self):
    """
    Returns an appropriately initialized _GenericHTTPChannelProtocol.
    """
    return _GenericHTTPChannelProtocol(HTTPChannel())



class HTTPFactory(protocol.ServerFactory):
    """
    Factory for HTTP server.

    @ivar _logDateTime: A cached datetime string for log messages, updated by
        C{_logDateTimeCall}.
    @type _logDateTime: C{str}

    @ivar _logDateTimeCall: A delayed call for the next update to the cached
        log datetime string.
    @type _logDateTimeCall: L{IDelayedCall} provided

    @ivar _logFormatter: See the C{logFormatter} parameter to L{__init__}

    @ivar _nativeize: A flag that indicates whether the log file being written
        to wants native strings (C{True}) or bytes (C{False}).  This is only to
        support writing to L{twisted.python.log} which, unfortunately, works
        with native strings.

    @ivar _reactor: An L{IReactorTime} provider used to compute logging
        timestamps.
    """

    protocol = _genericHTTPChannelProtocolFactory

    logPath = None

    timeOut = 60 * 60 * 12

    def __init__(self, logPath=None, timeout=60*60*12, logFormatter=None,
                 reactor=None):
        """
        @param logFormatter: An object to format requests into log lines for
            the access log.
        @type logFormatter: L{IAccessLogFormatter} provider

        @param reactor: A L{IReactorTime} provider used to compute logging
            timestamps.
        """
        if not reactor:
            from twisted.internet import reactor
        self._reactor = reactor

        if logPath is not None:
            logPath = os.path.abspath(logPath)
        self.logPath = logPath
        self.timeOut = timeout
        if logFormatter is None:
            logFormatter = combinedLogFormatter
        self._logFormatter = logFormatter

        # For storing the cached log datetime and the callback to update it
        self._logDateTime = None
        self._logDateTimeCall = None


    def _updateLogDateTime(self):
        """
        Update log datetime periodically, so we aren't always recalculating it.
        """
        self._logDateTime = datetimeToLogString(self._reactor.seconds())
        self._logDateTimeCall = self._reactor.callLater(1, self._updateLogDateTime)


    def buildProtocol(self, addr):
        p = protocol.ServerFactory.buildProtocol(self, addr)
        # timeOut needs to be on the Protocol instance cause
        # TimeoutMixin expects it there
        p.timeOut = self.timeOut
        return p


    def startFactory(self):
        """
        Set up request logging if necessary.
        """
        if self._logDateTimeCall is None:
            self._updateLogDateTime()

        if self.logPath:
            self._nativeize = False
            self.logFile = self._openLogFile(self.logPath)
        else:
            self._nativeize = True
            self.logFile = log.logfile


    def stopFactory(self):
        if hasattr(self, "logFile"):
            if self.logFile != log.logfile:
                self.logFile.close()
            del self.logFile

        if self._logDateTimeCall is not None and self._logDateTimeCall.active():
            self._logDateTimeCall.cancel()
            self._logDateTimeCall = None


    def _openLogFile(self, path):
        """
        Override in subclasses, e.g. to use L{twisted.python.logfile}.
        """
        f = open(path, "ab", 1)
        return f


    def log(self, request):
        """
        Write a line representing C{request} to the access log file.

        @param request: The request object about which to log.
        @type request: L{Request}
        """
        try:
            logFile = self.logFile
        except AttributeError:
            pass
        else:
            line = self._logFormatter(self._logDateTime, request) + u"\n"
            if self._nativeize:
                line = nativeString(line)
            else:
                line = line.encode("utf-8")
            logFile.write(line)
