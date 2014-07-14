from __future__ import print_function
from six.moves.urllib.parse import urljoin

from twisted.internet import reactor
from twisted.web import server, resource, static, util

class SiteTest(object):

    def setUp(self):
        self.site = reactor.listenTCP(0, test_site(), interface="127.0.0.1")
        self.baseurl = "http://localhost:%d/" % self.site.getHost().port

    def tearDown(self):
        self.site.stopListening()

    def url(self, path):
        return urljoin(self.baseurl, path)

def test_site():
    r = resource.Resource()
    r.putChild("text", static.Data("Works", "text/plain"))
    r.putChild("html", static.Data("<body><p class='one'>Works</p><p class='two'>World</p></body>", "text/html"))
    r.putChild("enc-gb18030", static.Data("<p>gb18030 encoding</p>", "text/html; charset=gb18030"))
    r.putChild("redirect", util.Redirect("/redirected"))
    r.putChild("redirected", static.Data("Redirected here", "text/plain"))
    return server.Site(r)
    

if __name__ == '__main__':
    port = reactor.listenTCP(0, test_site(), interface="127.0.0.1")
    print("http://localhost:%d/" % port.getHost().port)
    reactor.run()
