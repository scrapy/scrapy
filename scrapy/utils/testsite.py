import warnings
from urllib.parse import urljoin

from twisted.web import resource, server, static, util

from scrapy.exceptions import ScrapyDeprecationWarning

warnings.warn(
    "The scrapy.utils.testsite module is deprecated.",
    ScrapyDeprecationWarning,
)


class SiteTest:
    def setUp(self):
        from twisted.internet import reactor

        super().setUp()
        self.site = reactor.listenTCP(0, test_site(), interface="127.0.0.1")
        self.baseurl = f"http://localhost:{self.site.getHost().port}/"

    def tearDown(self):
        super().tearDown()
        self.site.stopListening()

    def url(self, path: str) -> str:
        return urljoin(self.baseurl, path)


class NoMetaRefreshRedirect(util.Redirect):
    def render(self, request: server.Request) -> bytes:
        content = util.Redirect.render(self, request)
        return content.replace(
            b'http-equiv="refresh"', b'http-no-equiv="do-not-refresh-me"'
        )


def test_site():
    r = resource.Resource()
    r.putChild(b"text", static.Data(b"Works", "text/plain"))
    r.putChild(
        b"html",
        static.Data(
            b"<body><p class='one'>Works</p><p class='two'>World</p></body>",
            "text/html",
        ),
    )
    r.putChild(
        b"enc-gb18030",
        static.Data(b"<p>gb18030 encoding</p>", "text/html; charset=gb18030"),
    )
    r.putChild(b"redirect", util.Redirect(b"/redirected"))
    r.putChild(b"redirect-no-meta-refresh", NoMetaRefreshRedirect(b"/redirected"))
    r.putChild(b"redirected", static.Data(b"Redirected here", "text/plain"))
    return server.Site(r)


if __name__ == "__main__":
    from twisted.internet import reactor  # pylint: disable=ungrouped-imports

    port = reactor.listenTCP(0, test_site(), interface="127.0.0.1")
    print(f"http://localhost:{port.getHost().port}/")
    reactor.run()
