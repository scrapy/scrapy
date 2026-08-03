from __future__ import annotations

import gzip
import json
import random
from typing import TYPE_CHECKING, Any, ParamSpec, TypeVar
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

    def __init__(self) -> None:
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
