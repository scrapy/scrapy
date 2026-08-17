from __future__ import annotations

import gzip
import itertools
import json
import random
from typing import TYPE_CHECKING, Any, ClassVar, ParamSpec, TypeVar, cast
from urllib.parse import urlencode

from twisted.internet.task import deferLater
from twisted.web import resource, server
from twisted.web.server import NOT_DONE_YET
from twisted.web.util import Redirect, redirectTo

from scrapy.utils.python import to_bytes, to_unicode

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from twisted.internet.defer import Deferred
    from twisted.python.failure import Failure
    from twisted.web._http2 import H2Connection, H2Stream
    from twisted.web.http import Request as HTTPRequest
    from twisted.web.server import Request


_T = TypeVar("_T")
_P = ParamSpec("_P")


def getarg(
    request: Request,
    name: bytes,
    default: Any = None,
    type_: Callable[[bytes], Any] | None = None,
) -> Any:
    if name in request.args:
        value = request.args[name][0]
        if type_ is not None:
            value = type_(value)
        return value
    return default


def close_connection(request: Request) -> None:
    # We have to force a disconnection for HTTP/1.1 clients. Otherwise
    # client keeps the connection open waiting for more data.
    request.channel.loseConnection()
    request.finish()


def put_child(parent: resource.Resource, path: bytes, child: resource.Resource) -> None:
    # zope.interface has no type hints, so mypy cannot tell that Resource
    # instances provide the IResource interface that putChild() expects.
    parent.putChild(path, child)  # type: ignore[arg-type]


class BaseResource(resource.Resource):
    """Base class for mockserver resources, with type hints."""

    # Only needed to give subclasses a typed __init__ to call.
    def __init__(self) -> None:  # pylint: disable=useless-parent-delegation
        super().__init__()  # type: ignore[no-untyped-call]


# most of the following resources are copied from twisted.web.test.test_webclient
class ForeverTakingResource(BaseResource):
    """
    L{ForeverTakingResource} is a resource which never finishes responding
    to requests.
    """

    def __init__(self, write: bool = False):
        super().__init__()
        self._write = write

    def render(self, request: Request) -> int:
        if self._write:
            request.write(b"some bytes")
        return server.NOT_DONE_YET


class HostHeaderResource(BaseResource):
    """
    A testing resource which renders itself as the value of the host header
    from the request.
    """

    def render(self, request: Request) -> bytes:
        headers = request.requestHeaders.getRawHeaders(b"host")
        assert headers
        return headers[0]


class ClientIPResource(BaseResource):
    """
    A testing resource which renders itself as the request client IP address.
    """

    def render(self, request: Request) -> bytes:
        client_address = request.getClientAddress()
        if client_address is None or client_address.host is None:
            return b""
        return to_bytes(client_address.host)


class PayloadResource(BaseResource):
    """
    A testing resource which renders itself as the contents of the request body
    as long as the request body is 100 bytes long, otherwise which renders
    itself as C{"ERROR"}.
    """

    def render(self, request: Request) -> bytes:
        assert request.content
        data: bytes = request.content.read()
        content_length = request.requestHeaders.getRawHeaders(b"content-length")
        assert content_length
        if len(data) != 100 or int(content_length[0]) != 100:
            return b"ERROR"
        return data


class LeafResource(BaseResource):
    isLeaf = True

    def deferRequest(
        self,
        request: HTTPRequest,
        delay: float,
        f: Callable[_P, _T],
        *a: _P.args,
        **kw: _P.kwargs,
    ) -> Deferred[_T]:
        from twisted.internet import reactor

        def _cancelrequest(_: Failure) -> None:
            # silence CancelledError
            d.addErrback(lambda _: None)
            d.cancel()

        d = deferLater(reactor, delay, f, *a, **kw)
        request.notifyFinish().addErrback(_cancelrequest)
        return d


class Follow(LeafResource):
    def render(self, request: Request) -> int:
        total = getarg(request, b"total", 100, type_=int)
        show = getarg(request, b"show", 1, type_=int)
        order = getarg(request, b"order", b"desc")
        maxlatency = getarg(request, b"maxlatency", 0, type_=float)
        n = getarg(request, b"n", total, type_=int)
        nlist: Sequence[int]
        if order == b"rand":
            nlist = [random.randint(1, total) for _ in range(show)]
        else:  # order == "desc"
            nlist = range(n, max(n - show, 0), -1)

        lag = random.random() * maxlatency
        self.deferRequest(request, lag, self.renderRequest, request, nlist)
        return NOT_DONE_YET

    def renderRequest(self, request: Request, nlist: Sequence[int]) -> None:
        s = """<html> <head></head> <body>"""
        args = request.args.copy()
        for nl in nlist:
            args[b"n"] = [to_bytes(str(nl))]
            argstr = urlencode(args, doseq=True)
            s += f"<a href='/follow?{argstr}'>follow {nl}</a><br>"
        s += """</body>"""
        request.write(to_bytes(s))
        request.finish()


class Delay(LeafResource):
    def render_GET(self, request: Request) -> int:
        n = getarg(request, b"n", 1, type_=float)
        b = getarg(request, b"b", 1, type_=int)
        if b:
            # send headers now and delay body
            request.write(b"")
        self.deferRequest(request, n, self._delayedRender, request, n)
        return NOT_DONE_YET

    def _delayedRender(self, request: Request, n: float) -> None:
        request.write(to_bytes(f"Response delayed for {n:.3f} seconds\n"))
        request.finish()


class Status(LeafResource):
    def render_GET(self, request: Request) -> bytes:
        n = getarg(request, b"n", 200, type_=int)
        request.setResponseCode(n)
        return b""


class Raw(LeafResource):
    def render_GET(self, request: Request) -> int:
        request.startedWriting = 1
        self.deferRequest(request, 0, self._delayedRender, request)
        return NOT_DONE_YET

    render_POST = render_GET

    def _delayedRender(self, request: Request) -> None:
        raw = getarg(request, b"raw", b"HTTP 1.1 200 OK\n")
        request.startedWriting = 1
        request.write(raw)
        assert request.channel.transport is not None
        request.channel.transport.loseConnection()
        request.finish()


class BadHeader(LeafResource):
    """Sends a response with a bad header line, one with no colon in it, like
    some servers do, between two good ones.

    One of the good header lines is split into two lines, so that handling of
    such headers is also covered.
    """

    response = (
        b"HTTP/1.1 200 OK\r\n"
        b"Content-Length: 5\r\n"
        b"Content-Type: text/html\r\n"
        b"X-Folded-Header: one\r\n"
        b"\ttwo\r\n"
        b'<meta http-equiv="Content-Type" content="text/html; charset=utf-8" />\r\n'
        b"X-After-Bad-Header: works\r\n"
        b"\r\n"
        b"Works"
    )

    def render_GET(self, request: Request) -> int:
        request.startedWriting = 1
        self.deferRequest(request, 0, self._delayedRender, request)
        return NOT_DONE_YET

    def _delayedRender(self, request: Request) -> None:
        request.write(self.response)
        # Clients that stop parsing headers at the bad one don't get
        # Content-Length, so they need the connection to be closed to know that
        # the response body is over.
        close_connection(request)


class Echo(LeafResource):
    def render_GET(self, request: Request) -> bytes:
        assert request.content
        output = {
            "headers": {
                to_unicode(k): [to_unicode(v) for v in vs]
                for k, vs in request.requestHeaders.getAllRawHeaders()
            },
            "body": to_unicode(request.content.read()),
        }
        return to_bytes(json.dumps(output))

    render_POST = render_GET


class RedirectTo(LeafResource):
    def render(self, request: Request) -> bytes:
        goto = getarg(request, b"goto", b"/")
        # we force the body content, otherwise Twisted redirectTo()
        # returns HTML with <meta http-equiv="refresh"
        # zope.interface has no type hints, so mypy cannot tell that Request
        # provides the IRequest interface.
        redirectTo(goto, request)  # type: ignore[arg-type]
        return b"redirecting..."


class Partial(LeafResource):
    def render_GET(self, request: Request) -> int:
        request.setHeader(b"Content-Length", b"1024")
        self.deferRequest(request, 0, self._delayedRender, request)
        return NOT_DONE_YET

    def _delayedRender(self, request: Request) -> None:
        request.write(b"partial content\n")
        request.finish()


class Drop(Partial):
    def _delayedRender(self, request: Request) -> None:
        abort = getarg(request, b"abort", 0, type_=int)
        request.write(b"this connection will be dropped\n")
        tr = request.channel.transport
        try:
            if tr:
                if abort and hasattr(tr, "abortConnection"):
                    tr.abortConnection()
                else:
                    tr.loseConnection()
        finally:
            request.finish()


class ArbitraryLengthPayloadResource(LeafResource):
    def render(self, request: Request) -> bytes:
        assert request.content
        data: bytes = request.content.read()
        return data


class NoMetaRefreshRedirect(Redirect):
    def render(self, request: server.Request) -> bytes:
        content: bytes = Redirect.render(self, request)
        return content.replace(
            b'http-equiv="refresh"', b'http-no-equiv="do-not-refresh-me"'
        )


class ContentLengthHeaderResource(BaseResource):
    """
    A testing resource which renders itself as the value of the Content-Length
    header from the request.
    """

    def render(self, request: Request) -> bytes:
        headers = request.requestHeaders.getRawHeaders(b"content-length")
        assert headers
        return headers[0]


class ChunkedResource(BaseResource):
    def render(self, request: Request) -> int:
        from twisted.internet import reactor

        def response() -> None:
            request.write(b"chunked ")
            request.write(b"content\n")
            request.finish()

        reactor.callLater(0, response)
        return server.NOT_DONE_YET


class BrokenChunkedResource(BaseResource):
    def render(self, request: Request) -> int:
        from twisted.internet import reactor

        def response() -> None:
            request.write(b"chunked ")
            request.write(b"content\n")
            # Disable terminating chunk on finish.
            request.chunked = False
            close_connection(request)

        reactor.callLater(0, response)
        return server.NOT_DONE_YET


class BrokenDownloadResource(BaseResource):
    def render(self, request: Request) -> int:
        from twisted.internet import reactor

        def response() -> None:
            request.setHeader(b"Content-Length", b"20")
            request.write(b"partial")
            close_connection(request)

        reactor.callLater(0, response)
        return server.NOT_DONE_YET


class EmptyContentTypeHeaderResource(BaseResource):
    """
    A testing resource which renders itself as the value of request body
    without content-type header in response.
    """

    def render(self, request: Request) -> bytes:
        assert request.content
        request.setHeader("content-type", "")
        data: bytes = request.content.read()
        return data


class LargeChunkedFileResource(BaseResource):
    def render(self, request: Request) -> int:
        from twisted.internet import reactor

        def response() -> None:
            for _ in range(1024):
                request.write(b"x" * 1024)
            request.finish()

        reactor.callLater(0, response)
        return server.NOT_DONE_YET


class DuplicateHeaderResource(BaseResource):
    def render(self, request: Request) -> bytes:
        request.responseHeaders.setRawHeaders(b"Set-Cookie", [b"a=b", b"c=d"])
        return b""


class UriResource(BaseResource):
    """Return the full uri that was requested"""

    def getChild(self, path: bytes, request: Request) -> resource.Resource:
        return self

    def render(self, request: Request) -> bytes | int:
        # Note: this is an ugly hack for CONNECT request timeout test.
        #       Returning some data here fail SSL/TLS handshake
        # ToDo: implement proper HTTPS proxy tests, not faking them.
        if request.method != b"CONNECT":
            return request.uri
        assert request.transport is not None
        request.transport.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
        return NOT_DONE_YET


class ResponseHeadersResource(BaseResource):
    """Return a response with headers set from the JSON request body"""

    def render(self, request: Request) -> bytes:
        assert request.content
        body = json.loads(request.content.read().decode())
        for header_name, header_value in body.items():
            request.responseHeaders.setRawHeaders(header_name, [header_value])
        return json.dumps(body).encode("utf-8")


class Compress(BaseResource):
    """Compress the data sent in the request url params and set Content-Encoding header"""

    def render(self, request: Request) -> bytes:
        data = request.args[b"data"][0]

        accept_encoding_header = request.getHeader(b"accept-encoding")

        # include common encoding schemes here
        if accept_encoding_header == b"gzip":
            request.setHeader(b"Content-Encoding", b"gzip")
            return gzip.compress(data)

        # just set this to trigger a test failure if no valid accept-encoding header was set
        request.setResponseCode(500)
        return b"Did not receive a valid accept-encoding header"


class SetCookie(BaseResource):
    """Return a response with a Set-Cookie header for each request url parameter"""

    def render(self, request: Request) -> bytes:
        for cookie_name, cookie_values in request.args.items():
            for cookie_value in cookie_values:
                cookie = (cookie_name.decode() + "=" + cookie_value.decode()).encode()
                request.setHeader(b"Set-Cookie", cookie)
        return b""


_connection_ids = itertools.count()


class ConnectionId(LeafResource):
    """Return the identifier of the connection serving the request, after the
    number of seconds given in the ``delay`` argument.

    Two responses carrying the same identifier were served over the same
    connection, which lets tests tell connection reuse from reconnection.
    """

    def render_GET(self, request: Request) -> int | bytes:
        delay = getarg(request, b"delay", 0, type_=float)
        if not delay:
            return self._connection_id(request)
        self.deferRequest(request, delay, self._delayedRender, request)
        return NOT_DONE_YET

    def _delayedRender(self, request: Request) -> None:
        request.write(self._connection_id(request))
        request.finish()

    @staticmethod
    def _connection_id(request: Request) -> bytes:
        # under HTTP/2 the channel of a request is its stream, so the
        # connection has to be reached through it
        channel: Any = getattr(request.channel, "_conn", request.channel)
        if not hasattr(channel, "_mockserver_connection_id"):
            channel._mockserver_connection_id = next(_connection_ids)
        return to_bytes(str(channel._mockserver_connection_id))


def _h2_connection(request: Request) -> H2Connection:
    """Return the HTTP/2 connection that *request* was received on.

    Only works for requests received over HTTP/2.
    """
    stream = cast("H2Stream", request.channel)
    connection: H2Connection = stream._conn
    return connection


def _h2_write(request: Request, data: bytes) -> None:
    """Write raw data into the HTTP/2 connection that *request* was received
    on."""
    transport = _h2_connection(request).transport
    assert transport is not None
    transport.write(data)


def _h2_frame(
    frame_type: int, payload: bytes = b"", stream_id: int = 0, flags: int = 0
) -> bytes:
    """Return an HTTP/2 frame (RFC 9113 §4.1)."""
    return (
        len(payload).to_bytes(3, "big")
        + bytes((frame_type, flags))
        + stream_id.to_bytes(4, "big")
        + payload
    )


class H2ResetStream(LeafResource):
    """Reset the HTTP/2 stream of the request instead of answering it"""

    def render_GET(self, request: Request) -> int:
        cast("H2Stream", request.channel).abortConnection()
        return NOT_DONE_YET


class H2GoAway(LeafResource):
    """End the HTTP/2 connection of the request with a GOAWAY frame instead of
    answering it"""

    def render_GET(self, request: Request) -> int:
        connection = _h2_connection(request).conn
        connection.close_connection()
        _h2_write(request, connection.data_to_send())
        return NOT_DONE_YET


class H2DataAndReset(LeafResource):
    """Answer the request with response headers and then, within a single write,
    a data frame and a reset of its HTTP/2 stream"""

    def render_GET(self, request: Request) -> int:
        stream_id = cast("H2Stream", request.channel).streamID
        request.write(b"")  # sends the response headers
        self.deferRequest(
            request,
            0.1,
            _h2_write,
            request,
            _h2_frame(0x0, b"a" * 1024, stream_id=stream_id)
            # RST_STREAM with the NO_ERROR code
            + _h2_frame(0x3, bytes(4), stream_id=stream_id),
        )
        return NOT_DONE_YET


class H2Raw(LeafResource):
    """Write into the HTTP/2 connection of the request the raw data chosen with
    the raw url parameter, and then answer the request"""

    raw_data: ClassVar[dict[bytes, bytes]] = {
        # a DATA frame above the default maximum frame size of 16 KiB
        b"large-frame": _h2_frame(0x0, b"\0" * (2**14 + 1), stream_id=1),
        # a frame of a type that is not part of HTTP/2
        b"unknown-frame": _h2_frame(0xFF),
    }

    def render_GET(self, request: Request) -> bytes:
        raw = getarg(request, b"raw")
        _h2_write(request, self.raw_data[raw])
        return b"Works"


class H2NoSupport(LeafResource):
    """Answer as servers without HTTP/2 support answer the connection preface,
    with a 405 status line and nothing else"""

    def render_GET(self, request: Request) -> int:
        _h2_write(request, b"HTTP/2.0 405 Method Not Allowed\r\n\r\n")
        return NOT_DONE_YET


class H2Push(LeafResource):
    """Push an empty response into the HTTP/2 connection of the request, and
    then answer the request"""

    def render_GET(self, request: Request) -> bytes:
        stream_id = cast("H2Stream", request.channel).streamID
        authority = request.getHeader(b"host") or b""
        # HPACK (RFC 7541) indexed fields for ":method: GET", ":scheme: https"
        # and ":path: /", followed by a literal ":authority" field
        promised_request = b"\x82\x87\x84\x01" + bytes((len(authority),)) + authority
        # HPACK indexed field for ":status: 200"
        pushed_response = b"\x88"
        _h2_write(
            request,
            # PUSH_PROMISE with the END_HEADERS flag set
            _h2_frame(
                0x5,
                (2).to_bytes(4, "big") + promised_request,
                stream_id=stream_id,
                flags=0x4,
            )
            # HEADERS with the END_STREAM and END_HEADERS flags set
            + _h2_frame(0x1, pushed_response, stream_id=2, flags=0x5),
        )
        return b"Works"
