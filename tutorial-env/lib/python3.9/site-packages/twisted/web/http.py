# -*- test-case-name: twisted.web.test.test_http -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
HyperText Transfer Protocol implementation.

This is the basic server-side protocol implementation used by the Twisted
Web server.  It can parse HTTP 1.0 requests and supports many HTTP 1.1
features as well.  Additionally, some functionality implemented here is
also useful for HTTP clients (such as the chunked encoding parser).

@var CACHED: A marker value to be returned from cache-related request methods
    to indicate to the caller that a cached response will be usable and no
    response body should be generated.

@var FOUND: An HTTP response code indicating a temporary redirect.

@var NOT_MODIFIED: An HTTP response code indicating that a requested
    pre-condition (for example, the condition represented by an
    I{If-Modified-Since} header is present in the request) has succeeded.  This
    indicates a response body cached by the client can be used.

@var PRECONDITION_FAILED: An HTTP response code indicating that a requested
    pre-condition (for example, the condition represented by an I{If-None-Match}
    header is present in the request) has failed.  This should typically
    indicate that the server has not taken the requested action.

@var maxChunkSizeLineLength: Maximum allowable length of the CRLF-terminated
    line that indicates the size of a chunk and the extensions associated with
    it, as in the HTTP 1.1 chunked I{Transfer-Encoding} (RFC 7230 section 4.1).
    This limits how much data may be buffered when decoding the line.
"""

__all__ = [
    "SWITCHING",
    "OK",
    "CREATED",
    "ACCEPTED",
    "NON_AUTHORITATIVE_INFORMATION",
    "NO_CONTENT",
    "RESET_CONTENT",
    "PARTIAL_CONTENT",
    "MULTI_STATUS",
    "MULTIPLE_CHOICE",
    "MOVED_PERMANENTLY",
    "FOUND",
    "SEE_OTHER",
    "NOT_MODIFIED",
    "USE_PROXY",
    "TEMPORARY_REDIRECT",
    "PERMANENT_REDIRECT",
    "BAD_REQUEST",
    "UNAUTHORIZED",
    "PAYMENT_REQUIRED",
    "FORBIDDEN",
    "NOT_FOUND",
    "NOT_ALLOWED",
    "NOT_ACCEPTABLE",
    "PROXY_AUTH_REQUIRED",
    "REQUEST_TIMEOUT",
    "CONFLICT",
    "GONE",
    "LENGTH_REQUIRED",
    "PRECONDITION_FAILED",
    "REQUEST_ENTITY_TOO_LARGE",
    "REQUEST_URI_TOO_LONG",
    "UNSUPPORTED_MEDIA_TYPE",
    "REQUESTED_RANGE_NOT_SATISFIABLE",
    "EXPECTATION_FAILED",
    "INTERNAL_SERVER_ERROR",
    "NOT_IMPLEMENTED",
    "BAD_GATEWAY",
    "SERVICE_UNAVAILABLE",
    "GATEWAY_TIMEOUT",
    "HTTP_VERSION_NOT_SUPPORTED",
    "INSUFFICIENT_STORAGE_SPACE",
    "NOT_EXTENDED",
    "RESPONSES",
    "CACHED",
    "urlparse",
    "parse_qs",
    "datetimeToString",
    "datetimeToLogString",
    "timegm",
    "stringToDatetime",
    "toChunk",
    "fromChunk",
    "parseContentRange",
    "StringTransport",
    "HTTPClient",
    "NO_BODY_CODES",
    "Request",
    "PotentialDataLoss",
    "HTTPChannel",
    "HTTPFactory",
]


import base64
import binascii
import calendar
import cgi
import math
import os
import re
import tempfile
import time
import warnings
from io import BytesIO
from typing import AnyStr, Callable, Optional, Tuple
from urllib.parse import (
    ParseResultBytes,
    unquote_to_bytes as unquote,
    urlparse as _urlparse,
)

from zope.interface import Attribute, Interface, implementer, provider

from incremental import Version

from twisted.internet import address, interfaces, protocol
from twisted.internet._producer_helpers import _PullToPush
from twisted.internet.defer import Deferred
from twisted.internet.interfaces import IProtocol
from twisted.logger import Logger
from twisted.protocols import basic, policies
from twisted.python import log
from twisted.python.compat import _PY37PLUS, nativeString, networkString
from twisted.python.components import proxyForInterface
from twisted.python.deprecate import deprecated
from twisted.python.failure import Failure

# twisted imports
from twisted.web._responses import (
    ACCEPTED,
    BAD_GATEWAY,
    BAD_REQUEST,
    CONFLICT,
    CREATED,
    EXPECTATION_FAILED,
    FORBIDDEN,
    FOUND,
    GATEWAY_TIMEOUT,
    GONE,
    HTTP_VERSION_NOT_SUPPORTED,
    INSUFFICIENT_STORAGE_SPACE,
    INTERNAL_SERVER_ERROR,
    LENGTH_REQUIRED,
    MOVED_PERMANENTLY,
    MULTI_STATUS,
    MULTIPLE_CHOICE,
    NO_CONTENT,
    NON_AUTHORITATIVE_INFORMATION,
    NOT_ACCEPTABLE,
    NOT_ALLOWED,
    NOT_EXTENDED,
    NOT_FOUND,
    NOT_IMPLEMENTED,
    NOT_MODIFIED,
    OK,
    PARTIAL_CONTENT,
    PAYMENT_REQUIRED,
    PERMANENT_REDIRECT,
    PRECONDITION_FAILED,
    PROXY_AUTH_REQUIRED,
    REQUEST_ENTITY_TOO_LARGE,
    REQUEST_TIMEOUT,
    REQUEST_URI_TOO_LONG,
    REQUESTED_RANGE_NOT_SATISFIABLE,
    RESET_CONTENT,
    RESPONSES,
    SEE_OTHER,
    SERVICE_UNAVAILABLE,
    SWITCHING,
    TEMPORARY_REDIRECT,
    UNAUTHORIZED,
    UNSUPPORTED_MEDIA_TYPE,
    USE_PROXY,
)
from twisted.web.http_headers import Headers, _sanitizeLinearWhitespace
from twisted.web.iweb import IAccessLogFormatter, INonQueuedRequestFactory, IRequest

try:
    from twisted.web._http2 import H2Connection

    H2_ENABLED = True
except ImportError:
    H2_ENABLED = False


# A common request timeout -- 1 minute. This is roughly what nginx uses, and
# so it seems to be a good choice for us too.
_REQUEST_TIMEOUT = 1 * 60

protocol_version = "HTTP/1.1"

CACHED = """Magic constant returned by http.Request methods to set cache
validation headers when the request is conditional and the value fails
the condition."""

# backwards compatibility
responses = RESPONSES


# datetime parsing and formatting
weekdayname = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
monthname = [
    None,
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
]
weekdayname_lower = [name.lower() for name in weekdayname]
monthname_lower = [name and name.lower() for name in monthname]


def _parseHeader(line):
    # cgi.parse_header requires a str
    key, pdict = cgi.parse_header(line.decode("charmap"))

    # We want the key as bytes, and cgi.parse_multipart (which consumes
    # pdict) expects a dict of str keys but bytes values
    key = key.encode("charmap")
    pdict = {x: y.encode("charmap") for x, y in pdict.items()}
    return (key, pdict)


def urlparse(url):
    """
    Parse an URL into six components.

    This is similar to C{urlparse.urlparse}, but rejects C{str} input
    and always produces C{bytes} output.

    @type url: C{bytes}

    @raise TypeError: The given url was a C{str} string instead of a
        C{bytes}.

    @return: The scheme, net location, path, params, query string, and fragment
        of the URL - all as C{bytes}.
    @rtype: C{ParseResultBytes}
    """
    if isinstance(url, str):
        raise TypeError("url must be bytes, not unicode")
    scheme, netloc, path, params, query, fragment = _urlparse(url)
    if isinstance(scheme, str):
        scheme = scheme.encode("ascii")
        netloc = netloc.encode("ascii")
        path = path.encode("ascii")
        query = query.encode("ascii")
        fragment = fragment.encode("ascii")
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
    s = networkString(
        "%s, %02d %3s %4d %02d:%02d:%02d GMT"
        % (weekdayname[wd], day, monthname[month], year, hh, mm, ss)
    )
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
        day,
        monthname[month],
        year,
        hh,
        mm,
        ss,
    )
    return s


def timegm(year, month, day, hour, minute, second):
    """
    Convert time tuple in GMT to seconds since epoch, GMT
    """
    EPOCH = 1970
    if year < EPOCH:
        raise ValueError("Years prior to %d not supported" % (EPOCH,))
    assert 1 <= month <= 12
    days = 365 * (year - EPOCH) + calendar.leapdays(EPOCH, year)
    for i in range(1, month):
        days = days + calendar.mdays[i]
    if month > 2 and calendar.isleap(year):
        days = days + 1
    days = days + day - 1
    hours = days * 24 + hour
    minutes = hours * 60 + minute
    seconds = minutes * 60 + second
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
    elif (partlen == 3 or partlen == 4) and parts[1].find("-") != -1:
        # 2nd date format: Sunday, 06-Nov-94 08:49:37 GMT
        # (Note: "GMT" is literal, not a variable timezone)
        # (also handles without without "GMT")
        # Two digit year, yucko.
        day, month, year = parts[1].split("-")
        time = parts[2]
        year = int(year)
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
    hour, min, sec = map(int, time.split(":"))
    return int(timegm(year, month, day, hour, min, sec))


def toChunk(data):
    """
    Convert string to a chunk.

    @type data: C{bytes}

    @returns: a tuple of C{bytes} representing the chunked encoding of data
    """
    return (networkString(f"{len(data):x}"), b"\r\n", data, b"\r\n")


def _ishexdigits(b: bytes) -> bool:
    """
    Is the string case-insensitively hexidecimal?

    It must be composed of one or more characters in the ranges a-f, A-F
    and 0-9.
    """
    for c in b:
        if c not in b"0123456789abcdefABCDEF":
            return False
    return b != b""


def _hexint(b: bytes) -> int:
    """
    Decode a hexadecimal integer.

    Unlike L{int(b, 16)}, this raises L{ValueError} when the integer has
    a prefix like C{b'0x'}, C{b'+'}, or C{b'-'}, which is desirable when
    parsing network protocols.
    """
    if not _ishexdigits(b):
        raise ValueError(b)
    return int(b, 16)


def fromChunk(data: bytes) -> Tuple[bytes, bytes]:
    """
    Convert chunk to string.

    Note that this function is not specification compliant: it doesn't handle
    chunk extensions.

    @type data: C{bytes}

    @return: tuple of (result, remaining) - both C{bytes}.

    @raise ValueError: If the given data is not a correctly formatted chunked
        byte string.
    """
    prefix, rest = data.split(b"\r\n", 1)
    length = _hexint(prefix)
    if length < 0:
        raise ValueError("Chunk length must be >= 0, not %d" % (length,))
    if rest[length : length + 2] != b"\r\n":
        raise ValueError("chunk must end with CRLF")
    return rest[:length], rest[length + 2 :]


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


class _IDeprecatedHTTPChannelToRequestInterface(Interface):
    """
    The interface L{HTTPChannel} expects of L{Request}.
    """

    requestHeaders = Attribute(
        "A L{http_headers.Headers} instance giving all received HTTP request "
        "headers."
    )

    responseHeaders = Attribute(
        "A L{http_headers.Headers} instance holding all HTTP response "
        "headers to be sent."
    )

    def connectionLost(reason):
        """
        The underlying connection has been lost.

        @param reason: A failure instance indicating the reason why
            the connection was lost.
        @type reason: L{twisted.python.failure.Failure}
        """

    def gotLength(length):
        """
        Called when L{HTTPChannel} has determined the length, if any,
        of the incoming request's body.

        @param length: The length of the request's body.
        @type length: L{int} if the request declares its body's length
            and L{None} if it does not.
        """

    def handleContentChunk(data):
        """
        Deliver a received chunk of body data to the request.  Note
        this does not imply chunked transfer encoding.

        @param data: The received chunk.
        @type data: L{bytes}
        """

    def parseCookies():
        """
        Parse the request's cookies out of received headers.
        """

    def requestReceived(command, path, version):
        """
        Called when the entire request, including its body, has been
        received.

        @param command: The request's HTTP command.
        @type command: L{bytes}

        @param path: The request's path.  Note: this is actually what
            RFC7320 calls the URI.
        @type path: L{bytes}

        @param version: The request's HTTP version.
        @type version: L{bytes}
        """

    def __eq__(other: object) -> bool:
        """
        Determines if two requests are the same object.

        @param other: Another object whose identity will be compared
            to this instance's.

        @return: L{True} when the two are the same object and L{False}
            when not.
        """

    def __ne__(other: object) -> bool:
        """
        Determines if two requests are not the same object.

        @param other: Another object whose identity will be compared
            to this instance's.

        @return: L{True} when the two are not the same object and
            L{False} when they are.
        """

    def __hash__():
        """
        Generate a hash value for the request.

        @return: The request's hash value.
        @rtype: L{int}
        """


class StringTransport:
    """
    I am a BytesIO wrapper that conforms for the transport API. I support
    the `writeSequence' method.
    """

    def __init__(self):
        self.s = BytesIO()

    def writeSequence(self, seq):
        self.s.write(b"".join(seq))

    def __getattr__(self, attr):
        return getattr(self.__dict__["s"], attr)


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
    @type __buffer: A C{BytesIO} object.

    @ivar _header: Part or all of an HTTP request header.
    @type _header: C{bytes}
    """

    length = None
    firstLine = True
    __buffer = None
    _header = b""

    def sendCommand(self, command, path):
        self.transport.writeSequence([command, b" ", path, b" HTTP/1.0\r\n"])

    def sendHeader(self, name, value):
        if not isinstance(value, bytes):
            # XXX Deprecate this case
            value = networkString(str(value))
        santizedName = _sanitizeLinearWhitespace(name)
        santizedValue = _sanitizeLinearWhitespace(value)
        self.transport.writeSequence([santizedName, b": ", santizedValue, b"\r\n"])

    def endHeaders(self):
        self.transport.write(b"\r\n")

    def extractHeader(self, header):
        """
        Given a complete HTTP header, extract the field name and value and
        process the header.

        @param header: a complete HTTP request header of the form
            'field-name: value'.
        @type header: C{bytes}
        """
        key, val = header.split(b":", 1)
        val = val.lstrip()
        self.handleHeader(key, val)
        if key.lower() == b"content-length":
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
            self.__buffer = BytesIO()
            self.handleEndHeaders()
            self.setRawMode()
            return

        if line.startswith(b"\t") or line.startswith(b" "):
            # This line is part of a multiline header. According to RFC 822, in
            # "unfolding" multiline headers you do not strip the leading
            # whitespace on the continuing line.
            self._header = self._header + line
        elif self._header:
            # This line starts a new header, so process the previous one.
            self.extractHeader(self._header)
            self._header = line
        else:  # First header
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
            data, rest = data[: self.length], data[self.length :]
            self.length -= len(data)
        else:
            rest = b""
        self.handleResponsePart(data)
        if self.length == 0:
            self.handleResponseEnd()
            self.setLineMode(rest)


# response codes that must have empty bodies
NO_BODY_CODES = (204, 304)


# Sentinel object that detects people explicitly passing `queued` to Request.
_QUEUED_SENTINEL = object()


def _getContentFile(length):
    """
    Get a writeable file-like object to which request content can be written.
    """
    if length is not None and length < 100000:
        return BytesIO()
    return tempfile.TemporaryFile()


_hostHeaderExpression = re.compile(br"^\[?(?P<host>.*?)\]?(:\d+)?$")


@implementer(interfaces.IConsumer, _IDeprecatedHTTPChannelToRequestInterface)
class Request:
    """
    A HTTP request.

    Subclasses should override the process() method to determine how
    the request will be processed.

    @ivar method: The HTTP method that was used, e.g. C{b'GET'}.
    @type method: L{bytes}

    @ivar uri: The full encoded URI which was requested (including query
        arguments), e.g. C{b'/a/b%20/c?q=v'}.
    @type uri: L{bytes}

    @ivar path: The encoded path of the request URI (not including query
        arguments), e.g. C{b'/a/b%20/c'}.
    @type path: L{bytes}

    @ivar args: A mapping of decoded query argument names as L{bytes} to
        corresponding query argument values as L{list}s of L{bytes}.
        For example, for a URI with C{foo=bar&foo=baz&quux=spam}
        as its query part C{args} will be C{{b'foo': [b'bar', b'baz'],
        b'quux': [b'spam']}}.
    @type args: L{dict} of L{bytes} to L{list} of L{bytes}

    @ivar content: A file-like object giving the request body.  This may be
        a file on disk, an L{io.BytesIO}, or some other type.  The
        implementation is free to decide on a per-request basis.
    @type content: L{typing.BinaryIO}

    @ivar cookies: The cookies that will be sent in the response.
    @type cookies: L{list} of L{bytes}

    @type requestHeaders: L{http_headers.Headers}
    @ivar requestHeaders: All received HTTP request headers.

    @type responseHeaders: L{http_headers.Headers}
    @ivar responseHeaders: All HTTP response headers to be sent.

    @ivar notifications: A L{list} of L{Deferred}s which are waiting for
        notification that the response to this request has been finished
        (successfully or with an error).  Don't use this attribute directly,
        instead use the L{Request.notifyFinish} method.

    @ivar _disconnected: A flag which is C{False} until the connection over
        which this request was received is closed and which is C{True} after
        that.
    @type _disconnected: L{bool}

    @ivar _log: A logger instance for request related messages.
    @type _log: L{twisted.logger.Logger}
    """

    producer = None
    finished = 0
    code = OK
    code_message = RESPONSES[OK]
    method = b"(no method yet)"
    clientproto = b"(no clientproto yet)"
    uri = b"(no uri yet)"
    startedWriting = 0
    chunked = 0
    sentLength = 0  # content-length of response, or total bytes sent via chunking
    etag = None
    lastModified = None
    args = None
    path = None
    content = None
    _forceSSL = 0
    _disconnected = False
    _log = Logger()

    def __init__(self, channel, queued=_QUEUED_SENTINEL):
        """
        @param channel: the channel we're connected to.
        @param queued: (deprecated) are we in the request queue, or can we
            start writing to the transport?
        """
        self.notifications = []
        self.channel = channel

        # Cache the client and server information, we'll need this
        # later to be serialized and sent with the request so CGIs
        # will work remotely
        self.client = self.channel.getPeer()
        self.host = self.channel.getHost()

        self.requestHeaders: Headers = Headers()
        self.received_cookies = {}
        self.responseHeaders = Headers()
        self.cookies = []  # outgoing cookies
        self.transport = self.channel.transport

        if queued is _QUEUED_SENTINEL:
            queued = False

        self.queued = queued

    def _cleanup(self):
        """
        Called when have finished responding and are no longer queued.
        """
        if self.producer:
            self._log.failure(
                "",
                Failure(RuntimeError(f"Producer was not unregistered for {self.uri}")),
            )
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

    @deprecated(Version("Twisted", 16, 3, 0))
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
        self.content = _getContentFile(length)

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
                for cook in cookietxt.split(b";"):
                    cook = cook.lstrip()
                    try:
                        k, v = cook.split(b"=", 1)
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
        clength = self.content.tell()
        self.content.seek(0, 0)
        self.args = {}

        self.method, self.uri = command, path
        self.clientproto = version
        x = self.uri.split(b"?", 1)

        if len(x) == 1:
            self.path = self.uri
        else:
            self.path, argstring = x
            self.args = parse_qs(argstring, 1)

        # Argument processing
        args = self.args
        ctype = self.requestHeaders.getRawHeaders(b"content-type")
        if ctype is not None:
            ctype = ctype[0]

        if self.method == b"POST" and ctype and clength:
            mfd = b"multipart/form-data"
            key, pdict = _parseHeader(ctype)
            # This weird CONTENT-LENGTH param is required by
            # cgi.parse_multipart() in some versions of Python 3.7+, see
            # bpo-29979. It looks like this will be relaxed and backported, see
            # https://github.com/python/cpython/pull/8530.
            pdict["CONTENT-LENGTH"] = clength
            if key == b"application/x-www-form-urlencoded":
                args.update(parse_qs(self.content.read(), 1))
            elif key == mfd:
                try:
                    if _PY37PLUS:
                        cgiArgs = cgi.parse_multipart(
                            self.content,
                            pdict,
                            encoding="utf8",
                            errors="surrogateescape",
                        )
                    else:
                        cgiArgs = cgi.parse_multipart(self.content, pdict)

                    if _PY37PLUS:
                        # The parse_multipart function on Python 3.7+
                        # decodes the header bytes as iso-8859-1 and
                        # decodes the body bytes as utf8 with
                        # surrogateescape -- we want bytes
                        self.args.update(
                            {
                                x.encode("iso-8859-1"): [
                                    z.encode("utf8", "surrogateescape")
                                    if isinstance(z, str)
                                    else z
                                    for z in y
                                ]
                                for x, y in cgiArgs.items()
                                if isinstance(x, str)
                            }
                        )
                    else:
                        # The parse_multipart function on Python 3
                        # decodes the header bytes as iso-8859-1 and
                        # returns a str key -- we want bytes so encode
                        # it back
                        self.args.update(
                            {x.encode("iso-8859-1"): y for x, y in cgiArgs.items()}
                        )
                except Exception as e:
                    # It was a bad request, or we got a signal.
                    self.channel._respondToBadRequestAndDisconnect()
                    if isinstance(e, (TypeError, ValueError, KeyError)):
                        return
                    else:
                        # If it's not a userspace error from CGI, reraise
                        raise

            self.content.seek(0, 0)

        self.process()

    def __repr__(self) -> str:
        """
        Return a string description of the request including such information
        as the request method and request URI.

        @return: A string loosely describing this L{Request} object.
        @rtype: L{str}
        """
        return "<{} at 0x{:x} method={} uri={} clientproto={}>".format(
            self.__class__.__name__,
            id(self),
            nativeString(self.method),
            nativeString(self.uri),
            nativeString(self.clientproto),
        )

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
                "unregistered" % (producer, self.producer)
            )

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
    def getHeader(self, key: AnyStr) -> Optional[AnyStr]:
        """
        Get an HTTP request header.

        @type key: C{bytes} or C{str}
        @param key: The name of the header to get the value of.

        @rtype: C{bytes} or C{str} or L{None}
        @return: The value of the specified header, or L{None} if that header
            was not present in the request. The string type of the result
            matches the type of C{key}.
        """
        value = self.requestHeaders.getRawHeaders(key)
        if value is not None:
            return value[-1]
        return None

    def getCookie(self, key):
        """
        Get a cookie that was sent from the network.

        @type key: C{bytes}
        @param key: The name of the cookie to get.

        @rtype: C{bytes} or C{None}
        @returns: The value of the specified cookie, or L{None} if that cookie
            was not present in the request.
        """
        return self.received_cookies.get(key)

    def notifyFinish(self):
        """
        Notify when the response to this request has finished.

        @note: There are some caveats around the reliability of the delivery of
            this notification.

                1. If this L{Request}'s channel is paused, the notification
                   will not be delivered.  This can happen in one of two ways;
                   either you can call C{request.transport.pauseProducing}
                   yourself, or,

                2. In order to deliver this notification promptly when a client
                   disconnects, the reactor must continue reading from the
                   transport, so that it can tell when the underlying network
                   connection has gone away.  Twisted Web will only keep
                   reading up until a finite (small) maximum buffer size before
                   it gives up and pauses the transport itself.  If this
                   occurs, you will not discover that the connection has gone
                   away until a timeout fires or until the application attempts
                   to send some data via L{Request.write}.

                3. It is theoretically impossible to distinguish between
                   successfully I{sending} a response and the peer successfully
                   I{receiving} it.  There are several networking edge cases
                   where the L{Deferred}s returned by C{notifyFinish} will
                   indicate success, but the data will never be received.
                   There are also edge cases where the connection will appear
                   to fail, but in reality the response was delivered.  As a
                   result, the information provided by the result of the
                   L{Deferred}s returned by this method should be treated as a
                   guess; do not make critical decisions in your applications
                   based upon it.

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
                "use Request.notifyFinish to keep track of this."
            )
        if self.finished:
            warnings.warn("Warning! request.finish called twice.", stacklevel=2)
            return

        if not self.startedWriting:
            # write headers
            self.write(b"")

        if self.chunked:
            # write last chunk and closing CRLF
            self.channel.write(b"0\r\n\r\n")

        # log request
        if hasattr(self.channel, "factory") and self.channel.factory is not None:
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
            raise RuntimeError(
                "Request.write called on a request after " "Request.finish was called."
            )

        if self._disconnected:
            # Don't attempt to write any data to a disconnected client.
            # The RuntimeError exception will be thrown as usual when
            # request.finish is called
            return

        if not self.startedWriting:
            self.startedWriting = 1
            version = self.clientproto
            code = b"%d" % (self.code,)
            reason = self.code_message
            headers = []

            # if we don't have a content length, we send data in
            # chunked mode, so that we can support pipelining in
            # persistent connections.
            if (
                (version == b"HTTP/1.1")
                and (self.responseHeaders.getRawHeaders(b"content-length") is None)
                and self.method != b"HEAD"
                and self.code not in NO_BODY_CODES
            ):
                headers.append((b"Transfer-Encoding", b"chunked"))
                self.chunked = 1

            if self.lastModified is not None:
                if self.responseHeaders.hasHeader(b"last-modified"):
                    self._log.info(
                        "Warning: last-modified specified both in"
                        " header list and lastModified attribute."
                    )
                else:
                    self.responseHeaders.setRawHeaders(
                        b"last-modified", [datetimeToString(self.lastModified)]
                    )

            if self.etag is not None:
                self.responseHeaders.setRawHeaders(b"ETag", [self.etag])

            for name, values in self.responseHeaders.getAllRawHeaders():
                for value in values:
                    headers.append((name, value))

            for cookie in self.cookies:
                headers.append((b"Set-Cookie", cookie))

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

    def addCookie(
        self,
        k,
        v,
        expires=None,
        domain=None,
        path=None,
        max_age=None,
        comment=None,
        secure=None,
        httpOnly=False,
        sameSite=None,
    ):
        """
        Set an outgoing HTTP cookie.

        In general, you should consider using sessions instead of cookies, see
        L{twisted.web.server.Request.getSession} and the
        L{twisted.web.server.Session} class for details.

        @param k: cookie name
        @type k: L{bytes} or L{str}

        @param v: cookie value
        @type v: L{bytes} or L{str}

        @param expires: cookie expire attribute value in
            "Wdy, DD Mon YYYY HH:MM:SS GMT" format
        @type expires: L{bytes} or L{str}

        @param domain: cookie domain
        @type domain: L{bytes} or L{str}

        @param path: cookie path
        @type path: L{bytes} or L{str}

        @param max_age: cookie expiration in seconds from reception
        @type max_age: L{bytes} or L{str}

        @param comment: cookie comment
        @type comment: L{bytes} or L{str}

        @param secure: direct browser to send the cookie on encrypted
            connections only
        @type secure: L{bool}

        @param httpOnly: direct browser not to expose cookies through channels
            other than HTTP (and HTTPS) requests
        @type httpOnly: L{bool}

        @param sameSite: One of L{None} (default), C{'lax'} or C{'strict'}.
            Direct browsers not to send this cookie on cross-origin requests.
            Please see:
            U{https://tools.ietf.org/html/draft-west-first-party-cookies-07}
        @type sameSite: L{None}, L{bytes} or L{str}

        @raise ValueError: If the value for C{sameSite} is not supported.
        """

        def _ensureBytes(val):
            """
            Ensure that C{val} is bytes, encoding using UTF-8 if
            needed.

            @param val: L{bytes} or L{str}

            @return: L{bytes}
            """
            if val is None:
                # It's None, so we don't want to touch it
                return val

            if isinstance(val, bytes):
                return val
            else:
                return val.encode("utf8")

        def _sanitize(val):
            r"""
            Replace linear whitespace (C{\r}, C{\n}, C{\r\n}) and
            semicolons C{;} in C{val} with a single space.

            @param val: L{bytes}
            @return: L{bytes}
            """
            return _sanitizeLinearWhitespace(val).replace(b";", b" ")

        cookie = _sanitize(_ensureBytes(k)) + b"=" + _sanitize(_ensureBytes(v))
        if expires is not None:
            cookie = cookie + b"; Expires=" + _sanitize(_ensureBytes(expires))
        if domain is not None:
            cookie = cookie + b"; Domain=" + _sanitize(_ensureBytes(domain))
        if path is not None:
            cookie = cookie + b"; Path=" + _sanitize(_ensureBytes(path))
        if max_age is not None:
            cookie = cookie + b"; Max-Age=" + _sanitize(_ensureBytes(max_age))
        if comment is not None:
            cookie = cookie + b"; Comment=" + _sanitize(_ensureBytes(comment))
        if secure:
            cookie = cookie + b"; Secure"
        if httpOnly:
            cookie = cookie + b"; HttpOnly"
        if sameSite:
            sameSite = _ensureBytes(sameSite).lower()
            if sameSite not in [b"lax", b"strict"]:
                raise ValueError("Invalid value for sameSite: " + repr(sameSite))
            cookie += b"; SameSite=" + sameSite
        self.cookies.append(cookie)

    def setResponseCode(self, code, message=None):
        """
        Set the HTTP response code.

        @type code: L{int}
        @type message: L{bytes}
        """
        if not isinstance(code, int):
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

        @type name: L{bytes} or L{str}
        @param name: The name of the header for which to set the value.

        @type value: L{bytes} or L{str}
        @param value: The value to set for the named header. A L{str} will be
            UTF-8 encoded, which may not interoperable with other
            implementations. Avoid passing non-ASCII characters if possible.
        """
        self.responseHeaders.setRawHeaders(name, [value])

    def redirect(self, url):
        """
        Utility function that does a redirect.

        Set the response code to L{FOUND} and the I{Location} header to the
        given URL.

        The request should have C{finish()} called after this.

        @param url: I{Location} header value.
        @type url: L{bytes} or L{str}
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
        @return: If I am a I{If-Modified-Since} conditional request and
            the time given is not newer than the condition, I return
            L{http.CACHED<CACHED>} to indicate that you should write no
            body.  Otherwise, I return a false value.
        """
        # time.time() may be a float, but the HTTP-date strings are
        # only good for whole seconds.
        when = int(math.ceil(when))
        if (not self.lastModified) or (self.lastModified < when):
            self.lastModified = when

        modifiedSince = self.getHeader(b"if-modified-since")
        if modifiedSince:
            firstPart = modifiedSince.split(b";", 1)[0]
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
            if (etag in tags) or (b"*" in tags):
                self.setResponseCode(
                    ((self.method in (b"HEAD", b"GET")) and NOT_MODIFIED)
                    or PRECONDITION_FAILED
                )
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
        Get the hostname that the HTTP client passed in to the request.

        @see: L{IRequest.getRequestHostname}

        @returns: the requested hostname

        @rtype: C{bytes}
        """
        host = self.getHeader(b"host")
        if host is not None:
            match = _hostHeaderExpression.match(host)
            if match is not None:
                return match.group("host")
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
        self._forceSSL = ssl  # set first so isSecure will work
        if self.isSecure():
            default = 443
        else:
            default = 80
        if port == default:
            hostHeader = host
        else:
            hostHeader = b"%b:%d" % (host, port)
        self.requestHeaders.setRawHeaders(b"host", [hostHeader])
        self.host = address.IPv4Address("TCP", host, port)

    @deprecated(Version("Twisted", 18, 4, 0), replacement="getClientAddress")
    def getClientIP(self):
        """
        Return the IP address of the client who submitted this request.

        This method is B{deprecated}.  Use L{getClientAddress} instead.

        @returns: the client IP address
        @rtype: C{str}
        """
        if isinstance(self.client, (address.IPv4Address, address.IPv6Address)):
            return self.client.host
        else:
            return None

    def getClientAddress(self):
        """
        Return the address of the client who submitted this request.

        This may not be a network address (e.g., a server listening on
        a UNIX domain socket will cause this to return
        L{UNIXAddress}).  Callers must check the type of the returned
        address.

        @since: 18.4

        @return: the client's address.
        @rtype: L{IAddress}
        """
        return self.client

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
        channel = getattr(self, "channel", None)
        if channel is None:
            return False
        return channel.isSecure()

    def _authorize(self):
        # Authorization, (mostly) per the RFC
        try:
            authh = self.getHeader(b"Authorization")
            if not authh:
                self.user = self.password = b""
                return
            bas, upw = authh.split()
            if bas.lower() != b"basic":
                raise ValueError()
            upw = base64.b64decode(upw)
            self.user, self.password = upw.split(b":", 1)
        except (binascii.Error, ValueError):
            self.user = self.password = b""
        except BaseException:
            self._log.failure("")
            self.user = self.password = b""

    def getUser(self):
        """
        Return the HTTP user sent with this request, if any.

        If no user was supplied, return the empty string.

        @returns: the HTTP user, if any
        @rtype: C{bytes}
        """
        try:
            return self.user
        except BaseException:
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
        except BaseException:
            pass
        self._authorize()
        return self.password

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
        if self.channel is not None:
            self.channel.loseConnection()

    def __eq__(self, other: object) -> bool:
        """
        Determines if two requests are the same object.

        @param other: Another object whose identity will be compared
            to this instance's.

        @return: L{True} when the two are the same object and L{False}
            when not.
        @rtype: L{bool}
        """
        # When other is not an instance of request, return
        # NotImplemented so that Python uses other.__eq__ to perform
        # the comparison.  This ensures that a Request proxy generated
        # by proxyForInterface compares equal to an actual Request
        # instanceby turning request != proxy into proxy != request.
        if isinstance(other, Request):
            return self is other
        return NotImplemented

    def __hash__(self):
        """
        A C{Request} is hashable so that it can be used as a mapping key.

        @return: A C{int} based on the instance's identity.
        """
        return id(self)


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
    C{_ChunkedTransferDecoder} raises L{_MalformedChunkedDataError} from its
    C{dataReceived} method when it encounters malformed data. This exception
    indicates a client-side error. If this exception is raised, the connection
    should be dropped with a 400 error.
    """


class _IdentityTransferDecoder:
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
                "_IdentityTransferDecoder cannot decode data after finishing"
            )

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
            finishCallback(b"")
            raise PotentialDataLoss()
        elif self.contentLength != 0:
            raise _DataLoss()


maxChunkSizeLineLength = 1024


_chunkExtChars = (
    b"\t !\"#$%&'()*+,-./0123456789:;<=>?@"
    b"ABCDEFGHIJKLMNOPQRSTUVWXYZ[]^_`"
    b"abcdefghijklmnopqrstuvwxyz{|}~"
    b"\x80\x81\x82\x83\x84\x85\x86\x87\x88\x89\x8a\x8b\x8c\x8d\x8e\x8f"
    b"\x90\x91\x92\x93\x94\x95\x96\x97\x98\x99\x9a\x9b\x9c\x9d\x9e\x9f"
    b"\xa0\xa1\xa2\xa3\xa4\xa5\xa6\xa7\xa8\xa9\xaa\xab\xac\xad\xae\xaf"
    b"\xb0\xb1\xb2\xb3\xb4\xb5\xb6\xb7\xb8\xb9\xba\xbb\xbc\xbd\xbe\xbf"
    b"\xc0\xc1\xc2\xc3\xc4\xc5\xc6\xc7\xc8\xc9\xca\xcb\xcc\xcd\xce\xcf"
    b"\xd0\xd1\xd2\xd3\xd4\xd5\xd6\xd7\xd8\xd9\xda\xdb\xdc\xdd\xde\xdf"
    b"\xe0\xe1\xe2\xe3\xe4\xe5\xe6\xe7\xe8\xe9\xea\xeb\xec\xed\xee\xef"
    b"\xf0\xf1\xf2\xf3\xf4\xf5\xf6\xf7\xf8\xf9\xfa\xfb\xfc\xfd\xfe\xff"
)
"""
Characters that are valid in a chunk extension.

See RFC 7230 section 4.1.1::

     chunk-ext      = *( ";" chunk-ext-name [ "=" chunk-ext-val ] )

     chunk-ext-name = token
     chunk-ext-val  = token / quoted-string

And section 3.2.6::

     token          = 1*tchar

     tchar          = "!" / "#" / "$" / "%" / "&" / "'" / "*"
                    / "+" / "-" / "." / "^" / "_" / "`" / "|" / "~"
                    / DIGIT / ALPHA
                    ; any VCHAR, except delimiters

     quoted-string  = DQUOTE *( qdtext / quoted-pair ) DQUOTE
     qdtext         = HTAB / SP /%x21 / %x23-5B / %x5D-7E / obs-text
     obs-text       = %x80-FF

We don't check if chunk extensions are well-formed beyond validating that they
don't contain characters outside this range.
"""


class _ChunkedTransferDecoder:
    """
    Protocol for decoding I{chunked} Transfer-Encoding, as defined by RFC 7230,
    section 4.1.  This protocol can interpret the contents of a request or
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
        time application data is received. This callback is not reentrant.

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

    @ivar _buffer: Accumulated received data for the current state. At each
        state transition this is truncated at the front so that index 0 is
        where the next state shall begin.

    @ivar _start: While in the C{'CHUNK_LENGTH'} state, tracks the index into
        the buffer at which search for CRLF should resume. Resuming the search
        at this position avoids doing quadratic work if the chunk length line
        arrives over many calls to C{dataReceived}.

        Not used in any other state.
    """

    state = "CHUNK_LENGTH"

    def __init__(
        self,
        dataCallback: Callable[[bytes], None],
        finishCallback: Callable[[bytes], None],
    ) -> None:
        self.dataCallback = dataCallback
        self.finishCallback = finishCallback
        self._buffer = bytearray()
        self._start = 0

    def _dataReceived_CHUNK_LENGTH(self) -> bool:
        """
        Read the chunk size line, ignoring any extensions.

        @returns: C{True} once the line has been read and removed from
            C{self._buffer}.  C{False} when more data is required.

        @raises _MalformedChunkedDataError: when the chunk size cannot be
            decoded or the length of the line exceeds L{maxChunkSizeLineLength}.
        """
        eolIndex = self._buffer.find(b"\r\n", self._start)

        if eolIndex >= maxChunkSizeLineLength or (
            eolIndex == -1 and len(self._buffer) > maxChunkSizeLineLength
        ):
            raise _MalformedChunkedDataError(
                "Chunk size line exceeds maximum of {} bytes.".format(
                    maxChunkSizeLineLength
                )
            )

        if eolIndex == -1:
            # Restart the search upon receipt of more data at the start of the
            # new data, minus one in case the last character of the buffer is
            # CR.
            self._start = len(self._buffer) - 1
            return False

        endOfLengthIndex = self._buffer.find(b";", 0, eolIndex)
        if endOfLengthIndex == -1:
            endOfLengthIndex = eolIndex
        rawLength = self._buffer[0:endOfLengthIndex]
        try:
            length = _hexint(rawLength)
        except ValueError:
            raise _MalformedChunkedDataError("Chunk-size must be an integer.")

        ext = self._buffer[endOfLengthIndex + 1 : eolIndex]
        if ext and ext.translate(None, _chunkExtChars) != b"":
            raise _MalformedChunkedDataError(
                f"Invalid characters in chunk extensions: {ext!r}."
            )

        if length == 0:
            self.state = "TRAILER"
        else:
            self.state = "BODY"

        self.length = length
        del self._buffer[0 : eolIndex + 2]
        self._start = 0
        return True

    def _dataReceived_CRLF(self) -> bool:
        """
        Await the carriage return and line feed characters that are the end of
        chunk marker that follow the chunk data.

        @returns: C{True} when the CRLF have been read, otherwise C{False}.

        @raises _MalformedChunkedDataError: when anything other than CRLF are
            received.
        """
        if len(self._buffer) < 2:
            return False

        if not self._buffer.startswith(b"\r\n"):
            raise _MalformedChunkedDataError("Chunk did not end with CRLF")

        self.state = "CHUNK_LENGTH"
        del self._buffer[0:2]
        return True

    def _dataReceived_TRAILER(self) -> bool:
        """
        Await the carriage return and line feed characters that follow the
        terminal zero-length chunk. Then invoke C{finishCallback} and switch to
        state C{'FINISHED'}.

        @returns: C{False}, as there is either insufficient data to continue,
            or no data remains.

        @raises _MalformedChunkedDataError: when anything other than CRLF is
            received.
        """
        if len(self._buffer) < 2:
            return False

        if not self._buffer.startswith(b"\r\n"):
            raise _MalformedChunkedDataError("Chunk did not end with CRLF")

        data = memoryview(self._buffer)[2:].tobytes()
        del self._buffer[:]
        self.state = "FINISHED"
        self.finishCallback(data)
        return False

    def _dataReceived_BODY(self) -> bool:
        """
        Deliver any available chunk data to the C{dataCallback}. When all the
        remaining data for the chunk arrives, switch to state C{'CRLF'}.

        @returns: C{True} to continue processing of any buffered data.
        """
        if len(self._buffer) >= self.length:
            chunk = memoryview(self._buffer)[: self.length].tobytes()
            del self._buffer[: self.length]
            self.state = "CRLF"
            self.dataCallback(chunk)
        else:
            chunk = bytes(self._buffer)
            self.length -= len(chunk)
            del self._buffer[:]
            self.dataCallback(chunk)
        return True

    def _dataReceived_FINISHED(self) -> bool:
        """
        Once C{finishCallback} has been invoked receipt of additional data
        raises L{RuntimeError} because it represents a programming error in
        the caller.
        """
        raise RuntimeError(
            "_ChunkedTransferDecoder.dataReceived called after last "
            "chunk was processed"
        )

    def dataReceived(self, data: bytes) -> None:
        """
        Interpret data from a request or response body which uses the
        I{chunked} Transfer-Encoding.
        """
        self._buffer += data
        goOn = True
        while goOn and self._buffer:
            goOn = getattr(self, "_dataReceived_" + self.state)()

    def noMoreData(self) -> None:
        """
        Verify that all data has been received.  If it has not been, raise
        L{_DataLoss}.
        """
        if self.state != "FINISHED":
            raise _DataLoss(
                "Chunked decoder in %r state, still expecting more data to "
                "get to 'FINISHED' state." % (self.state,)
            )


@implementer(interfaces.IPushProducer)
class _NoPushProducer:
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

    def resumeProducing(self):
        """
        Resume producing data.

        This tells a producer to re-add itself to the main loop and produce
        more data for its consumer.
        """

    def registerProducer(self, producer, streaming):
        """
        Register to receive data from a producer.

        @param producer: The producer to register.
        @param streaming: Whether this is a streaming producer or not.
        """

    def unregisterProducer(self):
        """
        Stop consuming data from a producer, without disconnecting.
        """

    def stopProducing(self):
        """
        IProducer.stopProducing
        """


@implementer(interfaces.ITransport, interfaces.IPushProducer, interfaces.IConsumer)
class HTTPChannel(basic.LineReceiver, policies.TimeoutMixin):
    """
    A receiver for HTTP requests.

    The L{HTTPChannel} provides L{interfaces.ITransport} and
    L{interfaces.IConsumer} to the L{Request} objects it creates.  It also
    implements L{interfaces.IPushProducer} to C{self.transport}, allowing the
    transport to pause it.

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

    @ivar _networkProducer: Either the transport, if it provides
        L{interfaces.IPushProducer}, or a null implementation of
        L{interfaces.IPushProducer}.  Used to attempt to prevent the transport
        from producing excess data when we're responding to a request.
    @type _networkProducer: L{interfaces.IPushProducer}

    @ivar _requestProducer: If the L{Request} object or anything it calls
        registers itself as an L{interfaces.IProducer}, it will be stored here.
        This is used to create a producing pipeline: pause/resume producing
        methods will be propagated from the C{transport}, through the
        L{HTTPChannel} instance, to the c{_requestProducer}.

        The reason we proxy through the producing methods rather than the old
        behaviour (where we literally just set the L{Request} object as the
        producer on the transport) is because we want to be able to exert
        backpressure on the client to prevent it from sending in arbitrarily
        many requests without ever reading responses.  Essentially, if the
        client never reads our responses we will eventually stop reading its
        requests.

    @type _requestProducer: L{interfaces.IPushProducer}

    @ivar _requestProducerStreaming: A boolean that tracks whether the producer
        on the L{Request} side of this channel has registered itself as a
        L{interfaces.IPushProducer} or an L{interfaces.IPullProducer}.
    @type _requestProducerStreaming: L{bool} or L{None}

    @ivar _waitingForTransport: A boolean that tracks whether the transport has
        asked us to stop producing.  This is used to keep track of what we're
        waiting for: if the transport has asked us to stop producing then we
        don't want to unpause the transport until it asks us to produce again.
    @type _waitingForTransport: L{bool}

    @ivar abortTimeout: The number of seconds to wait after we attempt to shut
        the transport down cleanly to give up and forcibly terminate it.  This
        is only used when we time a connection out, to prevent errors causing
        the FD to get leaked.  If this is L{None}, we will wait forever.
    @type abortTimeout: L{int}

    @ivar _abortingCall: The L{twisted.internet.base.DelayedCall} that will be
        used to forcibly close the transport if it doesn't close cleanly.
    @type _abortingCall: L{twisted.internet.base.DelayedCall}

    @ivar _optimisticEagerReadSize: When a resource takes a long time to answer
        a request (via L{twisted.web.server.NOT_DONE_YET}, hopefully one day by
        a L{Deferred}), we would like to be able to let that resource know
        about the underlying transport disappearing as promptly as possible,
        via L{Request.notifyFinish}, and therefore via
        C{self.requests[...].connectionLost()} on this L{HTTPChannel}.

        However, in order to simplify application logic, we implement
        head-of-line blocking, and do not relay pipelined requests to the
        application until the previous request has been answered.  This means
        that said application cannot dispose of any entity-body that comes in
        from those subsequent requests, which may be arbitrarily large, and it
        may need to be buffered in memory.

        To implement this tradeoff between prompt notification when possible
        (in the most frequent case of non-pipelined requests) and correct
        behavior when not (say, if a client sends a very long-running GET
        request followed by a PUT request with a very large body) we will
        continue reading pipelined requests into C{self._dataBuffer} up to a
        given limit.

        C{_optimisticEagerReadSize} is the number of bytes we will accept from
        the client and buffer before pausing the transport.

        This behavior has been in place since Twisted 17.9.0 .

    @type _optimisticEagerReadSize: L{int}
    """

    maxHeaders = 500
    totalHeadersSize = 16384
    abortTimeout = 15

    length = 0
    persistent = 1
    __header = b""
    __first_line = 1
    __content = None

    # set in instances or subclasses
    requestFactory = Request

    _savedTimeOut = None
    _receivedHeaderCount = 0
    _receivedHeaderSize = 0
    _requestProducer = None
    _requestProducerStreaming = None
    _waitingForTransport = False
    _abortingCall = None
    _optimisticEagerReadSize = 0x4000
    _log = Logger()

    def __init__(self):
        # the request queue
        self.requests = []
        self._handlingRequest = False
        self._dataBuffer = []
        self._transferDecoder = None

    def connectionMade(self):
        self.setTimeout(self.timeOut)
        self._networkProducer = interfaces.IPushProducer(
            self.transport, _NoPushProducer()
        )
        self._networkProducer.registerProducer(self, True)

    def lineReceived(self, line):
        """
        Called for each line from request until the end of headers when
        it enters binary mode.
        """
        self.resetTimeout()

        self._receivedHeaderSize += len(line)
        if self._receivedHeaderSize > self.totalHeadersSize:
            self._respondToBadRequestAndDisconnect()
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
        elif line == b"":
            # End of headers.
            if self.__header:
                ok = self.headerReceived(self.__header)
                # If the last header we got is invalid, we MUST NOT proceed
                # with processing. We'll have sent a 400 anyway, so just stop.
                if not ok:
                    return
            self.__header = b""
            self.allHeadersReceived()
            if self.length == 0:
                self.allContentReceived()
            else:
                self.setRawMode()
        elif line[0] in b" \t":
            # Continuation of a multi line header.
            self.__header += b" " + line.lstrip(b" \t")
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

    def _maybeChooseTransferDecoder(self, header, data):
        """
        If the provided header is C{content-length} or
        C{transfer-encoding}, choose the appropriate decoder if any.

        Returns L{True} if the request can proceed and L{False} if not.
        """

        def fail():
            self._respondToBadRequestAndDisconnect()
            self.length = None
            return False

        # Can this header determine the length?
        if header == b"content-length":
            if not data.isdigit():
                return fail()
            try:
                length = int(data)
            except ValueError:
                return fail()
            newTransferDecoder = _IdentityTransferDecoder(
                length, self.requests[-1].handleContentChunk, self._finishRequestBody
            )
        elif header == b"transfer-encoding":
            # XXX Rather poorly tested code block, apparently only exercised by
            # test_chunkedEncoding
            if data.lower() == b"chunked":
                length = None
                newTransferDecoder = _ChunkedTransferDecoder(
                    self.requests[-1].handleContentChunk, self._finishRequestBody
                )
            elif data.lower() == b"identity":
                return True
            else:
                return fail()
        else:
            # It's not a length related header, so exit
            return True

        if self._transferDecoder is not None:
            return fail()
        else:
            self.length = length
            self._transferDecoder = newTransferDecoder
            return True

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
            header, data = line.split(b":", 1)
        except ValueError:
            self._respondToBadRequestAndDisconnect()
            return False

        if not header or header[-1:].isspace():
            self._respondToBadRequestAndDisconnect()
            return False

        header = header.lower()
        data = data.strip(b" \t")

        if not self._maybeChooseTransferDecoder(header, data):
            return False

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

        self._handlingRequest = True

        req = self.requests[-1]
        req.requestReceived(command, path, version)

    def dataReceived(self, data):
        """
        Data was received from the network.  Process it.
        """
        # If we're currently handling a request, buffer this data.
        if self._handlingRequest:
            self._dataBuffer.append(data)
            if (
                sum(map(len, self._dataBuffer)) > self._optimisticEagerReadSize
            ) and not self._waitingForTransport:
                # If we received more data than a small limit while processing
                # the head-of-line request, apply TCP backpressure to our peer
                # to get them to stop sending more request data until we're
                # ready.  See docstring for _optimisticEagerReadSize above.
                self._networkProducer.pauseProducing()
            return
        return basic.LineReceiver.dataReceived(self, data)

    def rawDataReceived(self, data):
        self.resetTimeout()

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
        expectContinue = req.requestHeaders.getRawHeaders(b"expect")
        if (
            expectContinue
            and expectContinue[0].lower() == b"100-continue"
            and self._version == b"HTTP/1.1"
        ):
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
        connection = request.requestHeaders.getRawHeaders(b"connection")
        if connection:
            tokens = [t.lower() for t in connection[0].split(b" ")]
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
            if b"close" in tokens:
                request.responseHeaders.setRawHeaders(b"connection", [b"close"])
                return False
            else:
                return True
        else:
            return False

    def requestDone(self, request):
        """
        Called by first request in queue when it is done.
        """
        if request != self.requests[0]:
            raise TypeError
        del self.requests[0]

        # We should only resume the producer if we're not waiting for the
        # transport.
        if not self._waitingForTransport:
            self._networkProducer.resumeProducing()

        if self.persistent:
            self._handlingRequest = False

            if self._savedTimeOut:
                self.setTimeout(self._savedTimeOut)

            # Receive our buffered data, if any.
            data = b"".join(self._dataBuffer)
            self._dataBuffer = []
            self.setLineMode(data)
        else:
            self.loseConnection()

    def timeoutConnection(self):
        self._log.info("Timing out client: {peer}", peer=str(self.transport.getPeer()))
        if self.abortTimeout is not None:
            # We use self.callLater because that's what TimeoutMixin does.
            self._abortingCall = self.callLater(
                self.abortTimeout, self.forceAbortClient
            )
        self.loseConnection()

    def forceAbortClient(self):
        """
        Called if C{abortTimeout} seconds have passed since the timeout fired,
        and the connection still hasn't gone away. This can really only happen
        on extremely bad connections or when clients are maliciously attempting
        to keep connections open.
        """
        self._log.info(
            "Forcibly timing out client: {peer}", peer=str(self.transport.getPeer())
        )
        # We want to lose track of the _abortingCall so that no-one tries to
        # cancel it.
        self._abortingCall = None
        self.transport.abortConnection()

    def connectionLost(self, reason):
        self.setTimeout(None)
        for request in self.requests:
            request.connectionLost(reason)

        # If we were going to force-close the transport, we don't have to now.
        if self._abortingCall is not None:
            self._abortingCall.cancel()
            self._abortingCall = None

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
        sanitizedHeaders = Headers()
        for name, value in headers:
            sanitizedHeaders.addRawHeader(name, value)

        responseLine = version + b" " + code + b" " + reason + b"\r\n"
        headerSequence = [responseLine]
        headerSequence.extend(
            name + b": " + value + b"\r\n"
            for name, values in sanitizedHeaders.getAllRawHeaders()
            for value in values
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
        @type iovec: L{list} of L{bytes}

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
        self._networkProducer.unregisterProducer()
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
        if self._requestProducer is not None:
            raise RuntimeError(
                "Cannot register producer %s, because producer %s was never "
                "unregistered." % (producer, self._requestProducer)
            )

        if not streaming:
            producer = _PullToPush(producer, self)

        self._requestProducer = producer
        self._requestProducerStreaming = streaming

        if not streaming:
            producer.startStreaming()

    def unregisterProducer(self):
        """
        Stop consuming data from a producer, without disconnecting.

        @return: L{None}
        """
        if self._requestProducer is None:
            return

        if not self._requestProducerStreaming:
            self._requestProducer.stopStreaming()

        self._requestProducer = None
        self._requestProducerStreaming = None

    def stopProducing(self):
        """
        Stop producing data.

        The HTTPChannel doesn't *actually* implement this, beacuse the
        assumption is that it will only be called just before C{loseConnection}
        is called. There's nothing sensible we can do other than call
        C{loseConnection} anyway.
        """
        if self._requestProducer is not None:
            self._requestProducer.stopProducing()

    def pauseProducing(self):
        """
        Pause producing data.

        This will be called by the transport when the send buffers have been
        filled up. We want to simultaneously pause the producing L{Request}
        object and also pause our transport.

        The logic behind pausing the transport is specifically to avoid issues
        like https://twistedmatrix.com/trac/ticket/8868. In this case, our
        inability to send does not prevent us handling more requests, which
        means we increasingly queue up more responses in our send buffer
        without end. The easiest way to handle this is to ensure that if we are
        unable to send our responses, we will not read further data from the
        connection until the client pulls some data out. This is a bit of a
        blunt instrument, but it's ok.

        Note that this potentially interacts with timeout handling in a
        positive way. Once the transport is paused the client may run into a
        timeout which will cause us to tear the connection down. That's a good
        thing!
        """
        self._waitingForTransport = True

        # The first step is to tell any producer we might currently have
        # registered to stop producing. If we can slow our applications down
        # we should.
        if self._requestProducer is not None:
            self._requestProducer.pauseProducing()

        # The next step here is to pause our own transport, as discussed in the
        # docstring.
        if not self._handlingRequest:
            self._networkProducer.pauseProducing()

    def resumeProducing(self):
        """
        Resume producing data.

        This will be called by the transport when the send buffer has dropped
        enough to actually send more data. When this happens we can unpause any
        outstanding L{Request} producers we have, and also unpause our
        transport.
        """
        self._waitingForTransport = False

        if self._requestProducer is not None:
            self._requestProducer.resumeProducing()

        # We only want to resume the network producer if we're not currently
        # waiting for a response to show up.
        if not self._handlingRequest:
            self._networkProducer.resumeProducing()

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
        """
        self.transport.write(b"HTTP/1.1 400 Bad Request\r\n\r\n")
        self.loseConnection()


def _escape(s):
    """
    Return a string like python repr, but always escaped as if surrounding
    quotes were double quotes.

    @param s: The string to escape.
    @type s: L{bytes} or L{str}

    @return: An escaped string.
    @rtype: L{str}
    """
    if not isinstance(s, bytes):
        s = s.encode("ascii")

    r = repr(s)
    if not isinstance(r, str):
        r = r.decode("ascii")
    if r.startswith("b"):
        r = r[1:]
    if r.startswith("'"):
        return r[1:-1].replace('"', '\\"').replace("\\'", "'")
    return r[1:-1]


@provider(IAccessLogFormatter)
def combinedLogFormatter(timestamp, request):
    """
    @return: A combined log formatted log line for the given request.

    @see: L{IAccessLogFormatter}
    """
    clientAddr = request.getClientAddress()
    if isinstance(
        clientAddr, (address.IPv4Address, address.IPv6Address, _XForwardedForAddress)
    ):
        ip = clientAddr.host
    else:
        ip = b"-"
    referrer = _escape(request.getHeader(b"referer") or b"-")
    agent = _escape(request.getHeader(b"user-agent") or b"-")
    line = (
        '"%(ip)s" - - %(timestamp)s "%(method)s %(uri)s %(protocol)s" '
        '%(code)d %(length)s "%(referrer)s" "%(agent)s"'
        % dict(
            ip=_escape(ip),
            timestamp=timestamp,
            method=_escape(request.method),
            uri=_escape(request.uri),
            protocol=_escape(request.clientproto),
            code=request.code,
            length=request.sentLength or "-",
            referrer=referrer,
            agent=agent,
        )
    )
    return line


@implementer(interfaces.IAddress)
class _XForwardedForAddress:
    """
    L{IAddress} which represents the client IP to log for a request, as gleaned
    from an X-Forwarded-For header.

    @ivar host: An IP address or C{b"-"}.
    @type host: L{bytes}

    @see: L{proxiedLogFormatter}
    """

    def __init__(self, host):
        self.host = host


class _XForwardedForRequest(proxyForInterface(IRequest, "_request")):  # type: ignore[misc]
    """
    Add a layer on top of another request that only uses the value of an
    X-Forwarded-For header as the result of C{getClientAddress}.
    """

    def getClientAddress(self):
        """
        The client address (the first address) in the value of the
        I{X-Forwarded-For header}.  If the header is not present, the IP is
        considered to be C{b"-"}.

        @return: L{_XForwardedForAddress} which wraps the client address as
            expected by L{combinedLogFormatter}.
        """
        host = (
            self._request.requestHeaders.getRawHeaders(b"x-forwarded-for", [b"-"])[0]
            .split(b",")[0]
            .strip()
        )
        return _XForwardedForAddress(host)

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


class _GenericHTTPChannelProtocol(proxyForInterface(IProtocol, "_channel")):  # type: ignore[misc]
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

    @ivar _callLater: A value for the C{callLater} callback.
    @type _callLater: L{callable}
    """

    _negotiatedProtocol = None
    _requestFactory = Request
    _factory = None
    _site = None
    _timeOut = None
    _callLater = None

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
        """
        A callable to use to build L{IRequest} objects.

        Retries the object from the current backing channel.
        """
        return self._channel.requestFactory

    @requestFactory.setter
    def requestFactory(self, value):
        """
        A callable to use to build L{IRequest} objects.

        Sets the object on the backing channel and also stores the value for
        propagation to any new channel.

        @param value: The new callable to use.
        @type value: A L{callable} returning L{IRequest}
        """
        self._requestFactory = value
        self._channel.requestFactory = value

    @property
    def site(self):
        """
        A reference to the creating L{twisted.web.server.Site} object.

        Returns the site object from the backing channel.
        """
        return self._channel.site

    @site.setter
    def site(self, value):
        """
        A reference to the creating L{twisted.web.server.Site} object.

        Sets the object on the backing channel and also stores the value for
        propagation to any new channel.

        @param value: The L{twisted.web.server.Site} object to set.
        @type value: L{twisted.web.server.Site}
        """
        self._site = value
        self._channel.site = value

    @property
    def timeOut(self):
        """
        The idle timeout for the backing channel.
        """
        return self._channel.timeOut

    @timeOut.setter
    def timeOut(self, value):
        """
        The idle timeout for the backing channel.

        Sets the idle timeout on both the backing channel and stores it for
        propagation to any new backing channel.

        @param value: The timeout to set.
        @type value: L{int} or L{float}
        """
        self._timeOut = value
        self._channel.timeOut = value

    @property
    def callLater(self):
        """
        A value for the C{callLater} callback. This callback is used by the
        L{twisted.protocols.policies.TimeoutMixin} to handle timeouts.
        """
        return self._channel.callLater

    @callLater.setter
    def callLater(self, value):
        """
        Sets the value for the C{callLater} callback. This callback is used by
        the L{twisted.protocols.policies.TimeoutMixin} to handle timeouts.

        @param value: The new callback to use.
        @type value: L{callable}
        """
        self._callLater = value
        self._channel.callLater = value

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
                negotiatedProtocol = b"http/1.1"

            if negotiatedProtocol is None:
                negotiatedProtocol = b"http/1.1"

            if negotiatedProtocol == b"h2":
                if not H2_ENABLED:
                    raise ValueError("Negotiated HTTP/2 without support.")

                # We need to make sure that the HTTPChannel is unregistered
                # from the transport so that the H2Connection can register
                # itself if possible.
                networkProducer = self._channel._networkProducer
                networkProducer.unregisterProducer()

                # Cancel the old channel's timeout.
                self._channel.setTimeout(None)

                transport = self._channel.transport
                self._channel = H2Connection()
                self._channel.requestFactory = self._requestFactory
                self._channel.site = self._site
                self._channel.factory = self._factory
                self._channel.timeOut = self._timeOut
                self._channel.callLater = self._callLater
                self._channel.makeConnection(transport)

                # Register the H2Connection as the transport's
                # producer, so that the transport can apply back
                # pressure.
                networkProducer.registerProducer(self._channel, True)
            else:
                # Only HTTP/2 and HTTP/1.1 are supported right now.
                assert (
                    negotiatedProtocol == b"http/1.1"
                ), "Unsupported protocol negotiated"

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

    @ivar reactor: An L{IReactorTime} provider used to manage connection
        timeouts and compute logging timestamps.
    """

    # We need to ignore the mypy error here, because
    # _genericHTTPChannelProtocolFactory is a callable which returns a proxy
    # to a Protocol, instead of a concrete Protocol object, as expected in
    # the protocol.Factory interface
    protocol = _genericHTTPChannelProtocolFactory  # type: ignore[assignment]

    logPath = None

    timeOut = _REQUEST_TIMEOUT

    def __init__(
        self, logPath=None, timeout=_REQUEST_TIMEOUT, logFormatter=None, reactor=None
    ):
        """
        @param logPath: File path to which access log messages will be written
            or C{None} to disable logging.
        @type logPath: L{str} or L{bytes}

        @param timeout: The initial value of L{timeOut}, which defines the idle
            connection timeout in seconds, or C{None} to disable the idle
            timeout.
        @type timeout: L{float}

        @param logFormatter: An object to format requests into log lines for
            the access log.  L{combinedLogFormatter} when C{None} is passed.
        @type logFormatter: L{IAccessLogFormatter} provider

        @param reactor: An L{IReactorTime} provider used to manage connection
            timeouts and compute logging timestamps. Defaults to the global
            reactor.
        """
        if not reactor:
            from twisted.internet import reactor
        self.reactor = reactor

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
        self._logDateTime = datetimeToLogString(self.reactor.seconds())
        self._logDateTimeCall = self.reactor.callLater(1, self._updateLogDateTime)

    def buildProtocol(self, addr):
        p = protocol.ServerFactory.buildProtocol(self, addr)

        # This is a bit of a hack to ensure that the HTTPChannel timeouts
        # occur on the same reactor as the one we're using here. This could
        # ideally be resolved by passing the reactor more generally to the
        # HTTPChannel, but that won't work for the TimeoutMixin until we fix
        # https://twistedmatrix.com/trac/ticket/8488
        p.callLater = self.reactor.callLater

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
            self.logFile = self._openLogFile(self.logPath)
        else:
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
            line = self._logFormatter(self._logDateTime, request) + "\n"
            logFile.write(line.encode("utf8"))
