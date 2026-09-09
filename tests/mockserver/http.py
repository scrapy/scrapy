from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from twisted.web.static import Data, File
from twisted.web.util import Redirect

from tests import tests_datadir

from .http_base import BaseMockServer, main_factory
from .http_resources import (
    ArbitraryLengthPayloadResource,
    BadHeader,
    BaseResource,
    Books,
    BrokenChunkedResource,
    BrokenDownloadResource,
    ChunkedResource,
    ClientIPResource,
    Compress,
    ContentLengthHeaderResource,
    Delay,
    Drop,
    DuplicateHeaderResource,
    Echo,
    EmptyContentTypeHeaderResource,
    Follow,
    ForeverTakingResource,
    H2DataAndReset,
    H2GoAway,
    H2NoSupport,
    H2Push,
    H2Raw,
    H2ResetStream,
    HostHeaderResource,
    LargeChunkedFileResource,
    NoMetaRefreshRedirect,
    Partial,
    PayloadResource,
    Raw,
    RedirectTo,
    ResponseHeadersResource,
    SetCookie,
    Status,
    UriResource,
    put_child,
)

if TYPE_CHECKING:
    from twisted.web.server import Request


class Root(BaseResource):
    def __init__(self) -> None:
        super().__init__()
        put_child(self, b"status", Status())
        put_child(self, b"follow", Follow())
        put_child(self, b"books", Books())
        put_child(self, b"delay", Delay())
        put_child(self, b"partial", Partial())
        put_child(self, b"drop", Drop())
        put_child(self, b"raw", Raw())
        put_child(self, b"bad-header", BadHeader())
        put_child(self, b"echo", Echo())
        put_child(self, b"payload", PayloadResource())
        put_child(self, b"alpayload", ArbitraryLengthPayloadResource())
        put_child(self, b"static", File(str(Path(tests_datadir, "test_site/"))))
        put_child(self, b"redirect-to", RedirectTo())
        put_child(self, b"text", Data(b"Works", "text/plain"))
        put_child(
            self,
            b"html",
            Data(
                b"<body><p class='one'>Works</p><p class='two'>World</p></body>",
                "text/html",
            ),
        )
        put_child(
            self,
            b"enc-gb18030",
            Data(b"<p>gb18030 encoding</p>", "text/html; charset=gb18030"),
        )
        put_child(self, b"redirect", Redirect(b"/redirected"))
        put_child(
            self, b"redirect-no-meta-refresh", NoMetaRefreshRedirect(b"/redirected")
        )
        put_child(self, b"redirected", Data(b"Redirected here", "text/plain"))
        numbers = [str(x).encode("utf8") for x in range(2**18)]
        put_child(self, b"numbers", Data(b"".join(numbers), "text/plain"))
        put_child(self, b"wait", ForeverTakingResource())
        put_child(self, b"hang-after-headers", ForeverTakingResource(write=True))
        put_child(self, b"host", HostHeaderResource())
        put_child(self, b"client-ip", ClientIPResource())
        put_child(self, b"broken", BrokenDownloadResource())
        put_child(self, b"chunked", ChunkedResource())
        put_child(self, b"broken-chunked", BrokenChunkedResource())
        put_child(self, b"contentlength", ContentLengthHeaderResource())
        put_child(self, b"nocontenttype", EmptyContentTypeHeaderResource())
        put_child(self, b"largechunkedfile", LargeChunkedFileResource())
        put_child(self, b"compress", Compress())
        put_child(self, b"duplicate-header", DuplicateHeaderResource())
        put_child(self, b"response-headers", ResponseHeadersResource())
        put_child(self, b"set-cookie", SetCookie())
        put_child(self, b"uri", UriResource())
        put_child(self, b"h2-reset-stream", H2ResetStream())
        put_child(self, b"h2-data-and-reset", H2DataAndReset())
        put_child(self, b"h2-goaway", H2GoAway())
        put_child(self, b"h2-raw", H2Raw())
        put_child(self, b"h2-no-support", H2NoSupport())
        put_child(self, b"h2-push", H2Push())

    def getChild(self, path: bytes, request: Request) -> Root:
        return self

    def render(self, request: Request) -> bytes:
        return b"Scrapy mock HTTP server\n"


class MockServer(BaseMockServer):
    module_name = "tests.mockserver.http"


main = main_factory(Root)


if __name__ == "__main__":
    main()
