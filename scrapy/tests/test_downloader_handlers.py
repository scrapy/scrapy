import os

from twisted.trial import unittest
from twisted.protocols.policies import WrappingFactory
from twisted.python.filepath import FilePath
from twisted.internet import reactor, defer
from twisted.web import server, static, util, resource
from twisted.web.test.test_webclient import ForeverTakingResource, \
        NoLengthResource, HostHeaderResource, \
        PayloadResource, BrokenDownloadResource
from w3lib.url import path_to_file_uri

from scrapy.core.downloader.handlers.file import FileDownloadHandler
from scrapy.core.downloader.handlers.http import HttpDownloadHandler
from scrapy.core.downloader.handlers.s3 import S3DownloadHandler
from scrapy.spider import BaseSpider
from scrapy.http import Request
from scrapy import optional_features


class FileTestCase(unittest.TestCase):

    def setUp(self):
        self.tmpname = self.mktemp()
        fd = open(self.tmpname + '^', 'w')
        fd.write('0123456789')
        fd.close()
        self.download_request = FileDownloadHandler().download_request

    def test_download(self):
        def _test(response):
            self.assertEquals(response.url, request.url)
            self.assertEquals(response.status, 200)
            self.assertEquals(response.body, '0123456789')

        request = Request(path_to_file_uri(self.tmpname + '^'))
        assert request.url.upper().endswith('%5E')
        return self.download_request(request, BaseSpider('foo')).addCallback(_test)

    def test_non_existent(self):
        request = Request('file://%s' % self.mktemp())
        d = self.download_request(request, BaseSpider('foo'))
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
        self.download_request = HttpDownloadHandler().download_request

    def tearDown(self):
        return self.port.stopListening()

    def getURL(self, path):
        return "http://127.0.0.1:%d/%s" % (self.portno, path)

    def test_download(self):
        request = Request(self.getURL('file'))
        d = self.download_request(request, BaseSpider('foo'))
        d.addCallback(lambda r: r.body)
        d.addCallback(self.assertEquals, "0123456789")
        return d

    def test_download_head(self):
        request = Request(self.getURL('file'), method='HEAD')
        d = self.download_request(request, BaseSpider('foo'))
        d.addCallback(lambda r: r.body)
        d.addCallback(self.assertEquals, '')
        return d

    def test_redirect_status(self):
        request = Request(self.getURL('redirect'))
        d = self.download_request(request, BaseSpider('foo'))
        d.addCallback(lambda r: r.status)
        d.addCallback(self.assertEquals, 302)
        return d

    def test_redirect_status_head(self):
        request = Request(self.getURL('redirect'), method='HEAD')
        d = self.download_request(request, BaseSpider('foo'))
        d.addCallback(lambda r: r.status)
        d.addCallback(self.assertEquals, 302)
        return d

    def test_timeout_download_from_spider(self):
        request = Request(self.getURL('wait'), meta=dict(download_timeout=0.000001))
        d = self.download_request(request, BaseSpider('foo'))
        return self.assertFailure(d, defer.TimeoutError)

    def test_host_header_not_in_request_headers(self):
        def _test(response):
            self.assertEquals(response.body, '127.0.0.1:%d' % self.portno)
            self.assertEquals(request.headers, {})

        request = Request(self.getURL('host'))
        return self.download_request(request, BaseSpider('foo')).addCallback(_test)

    def test_host_header_seted_in_request_headers(self):
        def _test(response):
            self.assertEquals(response.body, 'example.com')
            self.assertEquals(request.headers.get('Host'), 'example.com')

        request = Request(self.getURL('host'), headers={'Host': 'example.com'})
        return self.download_request(request, BaseSpider('foo')).addCallback(_test)

        d = self.download_request(request, BaseSpider('foo'))
        d.addCallback(lambda r: r.body)
        d.addCallback(self.assertEquals, 'example.com')
        return d

    def test_payload(self):
        body = '1'*100 # PayloadResource requires body length to be 100
        request = Request(self.getURL('payload'), method='POST', body=body)
        d = self.download_request(request, BaseSpider('foo'))
        d.addCallback(lambda r: r.body)
        d.addCallback(self.assertEquals, body)
        return d


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
        self.download_request = HttpDownloadHandler().download_request

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
        return self.download_request(request, BaseSpider('foo')).addCallback(_test)

    def test_download_without_proxy(self):
        def _test(response):
            self.assertEquals(response.status, 200)
            self.assertEquals(response.url, request.url)
            self.assertEquals(response.body, '/path/to/resource')

        request = Request(self.getURL('path/to/resource'))
        return self.download_request(request, BaseSpider('foo')).addCallback(_test)


class HttpDownloadHandlerMock(object):
    def download_request(self, request, spider):
        return request

class S3TestCase(unittest.TestCase):
    skip = 'boto' not in optional_features and 'missing boto library'

    # test use same example keys than amazon developer guide
    # http://s3.amazonaws.com/awsdocs/S3/20060301/s3-dg-20060301.pdf
    # and the tests described here are the examples from that manual

    AWS_ACCESS_KEY_ID = '0PN5J17HBGZHT7JJ3X82'
    AWS_SECRET_ACCESS_KEY = 'uV3F3YluFJax1cknvbcGwgjvx4QpvB+leU8dUj2o'

    def setUp(self):
        s3reqh = S3DownloadHandler(self.AWS_ACCESS_KEY_ID, \
                self.AWS_SECRET_ACCESS_KEY, \
                httpdownloadhandler=HttpDownloadHandlerMock)
        self.download_request = s3reqh.download_request
        self.spider = BaseSpider('foo')

    def test_request_signing1(self):
        # gets an object from the johnsmith bucket.
        req = Request('s3://johnsmith/photos/puppy.jpg',
                headers={'Date': 'Tue, 27 Mar 2007 19:36:42 +0000'})
        httpreq = self.download_request(req, self.spider)
        self.assertEqual(httpreq.headers['Authorization'], \
                'AWS 0PN5J17HBGZHT7JJ3X82:xXjDGYUmKxnwqr5KXNPGldn5LbA=')

    def test_request_signing2(self):
        # puts an object into the johnsmith bucket.
        req = Request('s3://johnsmith/photos/puppy.jpg', method='PUT', headers={
            'Content-Type': 'image/jpeg',
            'Date': 'Tue, 27 Mar 2007 21:15:45 +0000',
            'Content-Length': '94328',
            })
        httpreq = self.download_request(req, self.spider)
        self.assertEqual(httpreq.headers['Authorization'], \
                'AWS 0PN5J17HBGZHT7JJ3X82:hcicpDDvL9SsO6AkvxqmIWkmOuQ=')

    def test_request_signing3(self):
        # lists the content of the johnsmith bucket.
        req = Request('s3://johnsmith/?prefix=photos&max-keys=50&marker=puppy', \
                method='GET', headers={
                    'User-Agent': 'Mozilla/5.0',
                    'Date': 'Tue, 27 Mar 2007 19:42:41 +0000',
                    })
        httpreq = self.download_request(req, self.spider)
        self.assertEqual(httpreq.headers['Authorization'], \
                'AWS 0PN5J17HBGZHT7JJ3X82:jsRt/rhG+Vtp88HrYL706QhE4w4=')

    def test_request_signing4(self):
        # fetches the access control policy sub-resource for the 'johnsmith' bucket.
        req = Request('s3://johnsmith/?acl', \
                method='GET', headers={'Date': 'Tue, 27 Mar 2007 19:44:46 +0000'})
        httpreq = self.download_request(req, self.spider)
        self.assertEqual(httpreq.headers['Authorization'], \
                'AWS 0PN5J17HBGZHT7JJ3X82:thdUi9VAkzhkniLj96JIrOPGi0g=')

    def test_request_signing5(self):
        # deletes an object from the 'johnsmith' bucket using the 
        # path-style and Date alternative.
        req = Request('s3://johnsmith/photos/puppy.jpg', \
                method='DELETE', headers={
                    'Date': 'Tue, 27 Mar 2007 21:20:27 +0000',
                    'x-amz-date': 'Tue, 27 Mar 2007 21:20:26 +0000',
                    })
        httpreq = self.download_request(req, self.spider)
        self.assertEqual(httpreq.headers['Authorization'], \
                'AWS 0PN5J17HBGZHT7JJ3X82:k3nL7gH3+PadhTEVn5Ip83xlYzk=')

    def test_request_signing6(self):
        # uploads an object to a CNAME style virtual hosted bucket with metadata.
        req = Request('s3://static.johnsmith.net:8080/db-backup.dat.gz', \
                method='PUT', headers={
                    'User-Agent': 'curl/7.15.5',
                    'Host': 'static.johnsmith.net:8080',
                    'Date': 'Tue, 27 Mar 2007 21:06:08 +0000',
                    'x-amz-acl': 'public-read',
                    'content-type': 'application/x-download',
                    'Content-MD5': '4gJE4saaMU4BqNR0kLY+lw==',
                    'X-Amz-Meta-ReviewedBy': 'joe@johnsmith.net,jane@johnsmith.net',
                    'X-Amz-Meta-FileChecksum': '0x02661779',
                    'X-Amz-Meta-ChecksumAlgorithm': 'crc32',
                    'Content-Disposition': 'attachment; filename=database.dat',
                    'Content-Encoding': 'gzip',
                    'Content-Length': '5913339',
                    })
        httpreq = self.download_request(req, self.spider)
        self.assertEqual(httpreq.headers['Authorization'], \
                'AWS 0PN5J17HBGZHT7JJ3X82:C0FlOtU8Ylb9KDTpZqYkZPX91iI=')
