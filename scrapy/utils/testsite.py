from __future__ import print_function
from six.moves.urllib.parse import urljoin

from twisted.internet import reactor
from twisted.web import server, resource, static, util


class SiteTest(object):

    def setUp(self):
        super(SiteTest, self).setUp()
        self.site = reactor.listenTCP(0, test_site(), interface="127.0.0.1")
        self.baseurl = "http://localhost:%d/" % self.site.getHost().port

    def tearDown(self):
        super(SiteTest, self).tearDown()
        self.site.stopListening()

    def url(self, path):
        return urljoin(self.baseurl, path)


def test_site():
    r = resource.Resource()
    r.putChild(b"text", static.Data(b"Works", "text/plain"))
    r.putChild(b"html", static.Data(b"<body><p class='one'>Works</p><p class='two'>World</p></body>", "text/html"))
    r.putChild(b"enc-gb18030", static.Data(b"<p>gb18030 encoding</p>", "text/html; charset=gb18030"))
    r.putChild(b"redirect", util.Redirect(b"/redirected"))
    r.putChild(b"redirected", static.Data(b"Redirected here", "text/plain"))
    return server.Site(r)


if __name__ == '__main__':
    port = reactor.listenTCP(0, test_site(), interface="127.0.0.1")
    print("http://localhost:%d/" % port.getHost().port)
    reactor.run()
