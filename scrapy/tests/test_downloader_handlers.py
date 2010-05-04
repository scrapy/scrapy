import os

from twisted.trial import unittest
from twisted.protocols.policies import WrappingFactory
from twisted.python.filepath import FilePath
from twisted.internet import reactor, defer
from twisted.web import server, static, util, resource
from twisted.web.test.test_webclient import ForeverTakingResource, \
        NoLengthResource, HostHeaderResource, \
        PayloadResource, BrokenDownloadResource

from scrapy.core.downloader.webclient import PartialDownloadError
from scrapy.core.downloader.handlers.file import download_file
from scrapy.core.downloader.handlers.http import download_http
from scrapy.spider import BaseSpider
from scrapy.http import Request


class FileTestCase(unittest.TestCase):

    def setUp(self):
        self.tmpname = self.mktemp()
        fd = open(self.tmpname + '^', 'w')
        fd.write('0123456789')
        fd.close()

    def test_download(self):
        def _test(response):
            self.assertEquals(response.url, request.url)
            self.assertEquals(response.status, 200)
            self.assertEquals(response.body, '0123456789')

        request = Request('file://%s' % self.tmpname + '^')
        assert request.url.upper().endswith('%5E')
        return download_file(request, BaseSpider('foo')).addCallback(_test)

    def test_non_existent(self):
        request = Request('file://%s' % self.mktemp())
        d = download_file(request, BaseSpider('foo'))
        return self.assertFailure(d, IOError)


class HttpTestCase(unittest.TestCase):

    def setUp(self):
        name = self.mktemp()
        os.mkdir(name)
        FilePath(name).child("file").setContent("0123456789")
        r = static.File(name)
        r.putChild("redirect", util.Redirect("/file"))
        r.putChild("wait", ForeverTakingResource())
        r.putChild("nolength", NoLengthResource())
        r.putChild("host", HostHeaderResource())
        r.putChild("payload", PayloadResource())
        r.putChild("broken", BrokenDownloadResource())
        self.site = server.Site(r, timeout=None)
        self.wrapper = WrappingFactory(self.site)
        self.port = reactor.listenTCP(0, self.wrapper, interface='127.0.0.1')
        self.portno = self.port.getHost().port

    def tearDown(self):
        return self.port.stopListening()

    def getURL(self, path):
        return "http://127.0.0.1:%d/%s" % (self.portno, path)

    def test_download(self):
        request = Request(self.getURL('file'))
        d = download_http(request, BaseSpider('foo'))
        d.addCallback(lambda r: r.body)
        d.addCallback(self.assertEquals, "0123456789")
        return d

    def test_download_head(self):
        request = Request(self.getURL('file'), method='HEAD')
        d = download_http(request, BaseSpider('foo'))
        d.addCallback(lambda r: r.body)
        d.addCallback(self.assertEquals, '')
        return d

    def test_redirect_status(self):
        request = Request(self.getURL('redirect'))
        d = download_http(request, BaseSpider('foo'))
        d.addCallback(lambda r: r.status)
        d.addCallback(self.assertEquals, 302)
        return d

    def test_redirect_status_head(self):
        request = Request(self.getURL('redirect'), method='HEAD')
        d = download_http(request, BaseSpider('foo'))
        d.addCallback(lambda r: r.status)
        d.addCallback(self.assertEquals, 302)
        return d

    def test_timeout_download_from_spider(self):
        spider = BaseSpider('foo')
        spider.download_timeout = 0.000001
        request = Request(self.getURL('wait'))
        d = download_http(request, spider)
        return self.assertFailure(d, defer.TimeoutError)

    def test_host_header_not_in_request_headers(self):
        def _test(response):
            self.assertEquals(response.body, '127.0.0.1:%d' % self.portno)
            self.assertEquals(request.headers, {})

        request = Request(self.getURL('host'))
        return download_http(request, BaseSpider('foo')).addCallback(_test)

    def test_host_header_seted_in_request_headers(self):
        def _test(response):
            self.assertEquals(response.body, 'example.com')
            self.assertEquals(request.headers.get('Host'), 'example.com')

        request = Request(self.getURL('host'), headers={'Host': 'example.com'})
        return download_http(request, BaseSpider('foo')).addCallback(_test)

        d = download_http(request, BaseSpider('foo'))
        d.addCallback(lambda r: r.body)
        d.addCallback(self.assertEquals, 'example.com')
        return d

    def test_payload(self):
        body = '1'*100 # PayloadResource requires body length to be 100
        request = Request(self.getURL('payload'), method='POST', body=body)
        d = download_http(request, BaseSpider('foo'))
        d.addCallback(lambda r: r.body)
        d.addCallback(self.assertEquals, body)
        return d

    def test_broken_download(self):
        request = Request(self.getURL('broken'))
        d = download_http(request, BaseSpider('foo'))
        return self.assertFailure(d, PartialDownloadError)


class UriResource(resource.Resource):
    """Return the full uri that was requested"""

    def getChild(self, path, request):
        return self

    def render(self, request):
        return request.uri


class HttpProxyTestCase(unittest.TestCase):

    def setUp(self):
        site = server.Site(UriResource(), timeout=None)
        wrapper = WrappingFactory(site)
        self.port = reactor.listenTCP(0, wrapper, interface='127.0.0.1')
        self.portno = self.port.getHost().port

    def tearDown(self):
        return self.port.stopListening()

    def getURL(self, path):
        return "http://127.0.0.1:%d/%s" % (self.portno, path)

    def test_download_with_proxy(self):
        def _test(response):
            self.assertEquals(response.status, 200)
            self.assertEquals(response.url, request.url)
            self.assertEquals(response.body, 'https://example.com')

        http_proxy = self.getURL('')
        request = Request('https://example.com', meta={'proxy': http_proxy})
        return download_http(request, BaseSpider('foo')).addCallback(_test)

    def test_download_without_proxy(self):
        def _test(response):
            self.assertEquals(response.status, 200)
            self.assertEquals(response.url, request.url)
            self.assertEquals(response.body, '/path/to/resource')

        request = Request(self.getURL('path/to/resource'))
        return download_http(request, BaseSpider('foo')).addCallback(_test)
