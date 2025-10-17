from __future__ import annotations

from pathlib import Path

from twisted.web import resource
from twisted.web.static import Data, File
from twisted.web.util import Redirect

from tests import tests_datadir

from .http_base import BaseMockServer, main_factory
from .http_resources import (
    ArbitraryLengthPayloadResource,
    BrokenChunkedResource,
    BrokenDownloadResource,
    ChunkedResource,
    Compress,
    ContentLengthHeaderResource,
    Delay,
    Drop,
    DuplicateHeaderResource,
    Echo,
    EmptyContentTypeHeaderResource,
    Follow,
    ForeverTakingResource,
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
)


class Root(resource.Resource):
    def __init__(self):
        super().__init__()
        self.putChild(b"status", Status())
        self.putChild(b"follow", Follow())
        self.putChild(b"delay", Delay())
        self.putChild(b"partial", Partial())
        self.putChild(b"drop", Drop())
        self.putChild(b"raw", Raw())
        self.putChild(b"echo", Echo())
        self.putChild(b"payload", PayloadResource())
        self.putChild(b"alpayload", ArbitraryLengthPayloadResource())
        self.putChild(b"static", File(str(Path(tests_datadir, "test_site/"))))
        self.putChild(b"redirect-to", RedirectTo())
        self.putChild(b"text", Data(b"Works", "text/plain"))
        self.putChild(
            b"html",
            Data(
                b"<body><p class='one'>Works</p><p class='two'>World</p></body>",
                "text/html",
            ),
        )
        self.putChild(
            b"enc-gb18030",
            Data(b"<p>gb18030 encoding</p>", "text/html; charset=gb18030"),
        )
        self.putChild(b"redirect", Redirect(b"/redirected"))
        self.putChild(
            b"redirect-no-meta-refresh", NoMetaRefreshRedirect(b"/redirected")
        )
        self.putChild(b"redirected", Data(b"Redirected here", "text/plain"))
        numbers = [str(x).encode("utf8") for x in range(2**18)]
        self.putChild(b"numbers", Data(b"".join(numbers), "text/plain"))
        self.putChild(b"wait", ForeverTakingResource())
        self.putChild(b"hang-after-headers", ForeverTakingResource(write=True))
        self.putChild(b"host", HostHeaderResource())
        self.putChild(b"broken", BrokenDownloadResource())
        self.putChild(b"chunked", ChunkedResource())
        self.putChild(b"broken-chunked", BrokenChunkedResource())
        self.putChild(b"contentlength", ContentLengthHeaderResource())
        self.putChild(b"nocontenttype", EmptyContentTypeHeaderResource())
        self.putChild(b"largechunkedfile", LargeChunkedFileResource())
        self.putChild(b"compress", Compress())
        self.putChild(b"duplicate-header", DuplicateHeaderResource())
        self.putChild(b"response-headers", ResponseHeadersResource())
        self.putChild(b"set-cookie", SetCookie())

    def getChild(self, name, request):
        return self

    def render(self, request):
        return b"Scrapy mock HTTP server\n"


class MockServer(BaseMockServer):
    module_name = "tests.mockserver.http"


main = main_factory(Root)


if __name__ == "__main__":
    main()
