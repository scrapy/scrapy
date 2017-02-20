import os
import six
import contextlib
import shutil
try:
    from unittest import mock
except ImportError:
    import mock
import shutil

from twisted.trial import unittest
from twisted.protocols.policies import WrappingFactory
from twisted.python.filepath import FilePath
from twisted.internet import reactor, defer, error
from twisted.web import server, static, util, resource
from twisted.web.test.test_webclient import ForeverTakingResource, \
        NoLengthResource, HostHeaderResource, \
        PayloadResource, BrokenDownloadResource
from twisted.cred import portal, checkers, credentials
from w3lib.url import path_to_file_uri

from scrapy.core.downloader.handlers import DownloadHandlers
from scrapy.core.downloader.handlers.file import FileDownloadHandler
from scrapy.core.downloader.handlers.http import HTTPDownloadHandler, HttpDownloadHandler
from scrapy.core.downloader.handlers.http10 import HTTP10DownloadHandler
from scrapy.core.downloader.handlers.http11 import HTTP11DownloadHandler
from scrapy.core.downloader.handlers.s3 import S3DownloadHandler

from scrapy.spiders import Spider
from scrapy.http import Request
from scrapy.http.response.text import TextResponse
from scrapy.settings import Settings
from scrapy.utils.test import get_crawler, skip_if_no_boto
from scrapy.utils.python import to_bytes
from scrapy.exceptions import NotConfigured

from tests.mockserver import MockServer, ssl_context_factory
from tests.spiders import SingleRequestSpider

class DummyDH(object):

    def __init__(self, crawler):
        pass


class OffDH(object):

    def __init__(self, crawler):
        raise NotConfigured


class LoadTestCase(unittest.TestCase):

    def test_enabled_handler(self):
        handlers = {'scheme': 'tests.test_downloader_handlers.DummyDH'}
        crawler = get_crawler(settings_dict={'DOWNLOAD_HANDLERS': handlers})
        dh = DownloadHandlers(crawler)
        self.assertIn('scheme', dh._schemes)
        for scheme in handlers: # force load handlers
            dh._get_handler(scheme)
        self.assertIn('scheme', dh._handlers)
        self.assertNotIn('scheme', dh._notconfigured)

    def test_not_configured_handler(self):
        handlers = {'scheme': 'tests.test_downloader_handlers.OffDH'}
        crawler = get_crawler(settings_dict={'DOWNLOAD_HANDLERS': handlers})
        dh = DownloadHandlers(crawler)
        self.assertIn('scheme', dh._schemes)
        for scheme in handlers: # force load handlers
            dh._get_handler(scheme)
        self.assertNotIn('scheme', dh._handlers)
        self.assertIn('scheme', dh._notconfigured)

    def test_disabled_handler(self):
        handlers = {'scheme': None}
        crawler = get_crawler(settings_dict={'DOWNLOAD_HANDLERS': handlers})
        dh = DownloadHandlers(crawler)
        self.assertNotIn('scheme', dh._schemes)
        for scheme in handlers: # force load handlers
            dh._get_handler(scheme)
        self.assertNotIn('scheme', dh._handlers)
        self.assertIn('scheme', dh._notconfigured)


class FileTestCase(unittest.TestCase):

    def setUp(self):
        self.tmpname = self.mktemp()
        with open(self.tmpname + '^', 'w') as f:
            f.write('0123456789')
        self.download_request = FileDownloadHandler(Settings()).download_request

    def tearDown(self):
        os.unlink(self.tmpname + '^')

    def test_download(self):
        def _test(response):
            self.assertEquals(response.url, request.url)
            self.assertEquals(response.status, 200)
            self.assertEquals(response.body, b'0123456789')

        request = Request(path_to_file_uri(self.tmpname + '^'))
        assert request.url.upper().endswith('%5E')
        return self.download_request(request, Spider('foo')).addCallback(_test)

    def test_non_existent(self):
        request = Request('file://%s' % self.mktemp())
        d = self.download_request(request, Spider('foo'))
        return self.assertFailure(d, IOError)


class ContentLengthHeaderResource(resource.Resource):
    """
    A testing resource which renders itself as the value of the Content-Length
    header from the request.
    """
    def render(self, request):
        return request.requestHeaders.getRawHeaders(b"content-length")[0]


class EmptyContentTypeHeaderResource(resource.Resource):
    """
    A testing resource which renders itself as the value of request body
    without content-type header in response.
    """
    def render(self, request):
        request.setHeader("content-type", "")
        return request.content.read()


class HttpTestCase(unittest.TestCase):

    scheme = 'http'
    download_handler_cls = HTTPDownloadHandler

    # only used for HTTPS tests
    keyfile = 'keys/cert.pem'
    certfile = 'keys/cert.pem'

    def setUp(self):
        self.tmpname = self.mktemp()
        os.mkdir(self.tmpname)
        FilePath(self.tmpname).child("file").setContent(b"0123456789")
        r = static.File(self.tmpname)
        r.putChild(b"redirect", util.Redirect(b"/file"))
        r.putChild(b"wait", ForeverTakingResource())
        r.putChild(b"hang-after-headers", ForeverTakingResource(write=True))
        r.putChild(b"nolength", NoLengthResource())
        r.putChild(b"host", HostHeaderResource())
        r.putChild(b"payload", PayloadResource())
        r.putChild(b"broken", BrokenDownloadResource())
        r.putChild(b"contentlength", ContentLengthHeaderResource())
        r.putChild(b"nocontenttype", EmptyContentTypeHeaderResource())
        self.site = server.Site(r, timeout=None)
        self.wrapper = WrappingFactory(self.site)
        self.host = 'localhost'
        if self.scheme == 'https':
            self.port = reactor.listenSSL(
                0, self.wrapper, ssl_context_factory(self.keyfile, self.certfile),
                interface=self.host)
        else:
            self.port = reactor.listenTCP(0, self.wrapper, interface=self.host)
        self.portno = self.port.getHost().port
        self.download_handler = self.download_handler_cls(Settings())
        self.download_request = self.download_handler.download_request

    @defer.inlineCallbacks
    def tearDown(self):
        yield self.port.stopListening()
        if hasattr(self.download_handler, 'close'):
            yield self.download_handler.close()
        shutil.rmtree(self.tmpname)

    def getURL(self, path):
        return "%s://%s:%d/%s" % (self.scheme, self.host, self.portno, path)

    def test_download(self):
        request = Request(self.getURL('file'))
        d = self.download_request(request, Spider('foo'))
        d.addCallback(lambda r: r.body)
        d.addCallback(self.assertEquals, b"0123456789")
        return d

    def test_download_head(self):
        request = Request(self.getURL('file'), method='HEAD')
        d = self.download_request(request, Spider('foo'))
        d.addCallback(lambda r: r.body)
        d.addCallback(self.assertEquals, b'')
        return d

    def test_redirect_status(self):
        request = Request(self.getURL('redirect'))
        d = self.download_request(request, Spider('foo'))
        d.addCallback(lambda r: r.status)
        d.addCallback(self.assertEquals, 302)
        return d

    def test_redirect_status_head(self):
        request = Request(self.getURL('redirect'), method='HEAD')
        d = self.download_request(request, Spider('foo'))
        d.addCallback(lambda r: r.status)
        d.addCallback(self.assertEquals, 302)
        return d

    @defer.inlineCallbacks
    def test_timeout_download_from_spider_nodata_rcvd(self):
        # client connects but no data is received
        spider = Spider('foo')
        meta = {'download_timeout': 0.2}
        request = Request(self.getURL('wait'), meta=meta)
        d = self.download_request(request, spider)
        yield self.assertFailure(d, defer.TimeoutError, error.TimeoutError)

    @defer.inlineCallbacks
    def test_timeout_download_from_spider_server_hangs(self):
        # client connects, server send headers and some body bytes but hangs
        spider = Spider('foo')
        meta = {'download_timeout': 0.2}
        request = Request(self.getURL('hang-after-headers'), meta=meta)
        d = self.download_request(request, spider)
        yield self.assertFailure(d, defer.TimeoutError, error.TimeoutError)

    def test_host_header_not_in_request_headers(self):
        def _test(response):
            self.assertEquals(
                response.body, to_bytes('%s:%d' % (self.host, self.portno)))
            self.assertEquals(request.headers, {})

        request = Request(self.getURL('host'))
        return self.download_request(request, Spider('foo')).addCallback(_test)

    def test_host_header_seted_in_request_headers(self):
        def _test(response):
            self.assertEquals(response.body, b'example.com')
            self.assertEquals(request.headers.get('Host'), b'example.com')

        request = Request(self.getURL('host'), headers={'Host': 'example.com'})
        return self.download_request(request, Spider('foo')).addCallback(_test)

        d = self.download_request(request, Spider('foo'))
        d.addCallback(lambda r: r.body)
        d.addCallback(self.assertEquals, b'example.com')
        return d

    def test_content_length_zero_bodyless_post_request_headers(self):
        """Tests if "Content-Length: 0" is sent for bodyless POST requests.

        This is not strictly required by HTTP RFCs but can cause trouble
        for some web servers.
        See:
        https://github.com/scrapy/scrapy/issues/823
        https://issues.apache.org/jira/browse/TS-2902
        https://github.com/kennethreitz/requests/issues/405
        https://bugs.python.org/issue14721
        """
        def _test(response):
            self.assertEquals(response.body, b'0')

        request = Request(self.getURL('contentlength'), method='POST', headers={'Host': 'example.com'})
        return self.download_request(request, Spider('foo')).addCallback(_test)

    def test_payload(self):
        body = b'1'*100 # PayloadResource requires body length to be 100
        request = Request(self.getURL('payload'), method='POST', body=body)
        d = self.download_request(request, Spider('foo'))
        d.addCallback(lambda r: r.body)
        d.addCallback(self.assertEquals, body)
        return d


class DeprecatedHttpTestCase(HttpTestCase):
    """HTTP 1.0 test case"""
    download_handler_cls = HttpDownloadHandler


class Http10TestCase(HttpTestCase):
    """HTTP 1.0 test case"""
    download_handler_cls = HTTP10DownloadHandler


class Https10TestCase(Http10TestCase):
    scheme = 'https'


class Http11TestCase(HttpTestCase):
    """HTTP 1.1 test case"""
    download_handler_cls = HTTP11DownloadHandler

    def test_download_without_maxsize_limit(self):
        request = Request(self.getURL('file'))
        d = self.download_request(request, Spider('foo'))
        d.addCallback(lambda r: r.body)
        d.addCallback(self.assertEquals, b"0123456789")
        return d

    def test_response_class_choosing_request(self):
        """Tests choosing of correct response type
         in case of Content-Type is empty but body contains text.
        """
        body = b'Some plain text\ndata with tabs\t and null bytes\0'

        def _test_type(response):
            self.assertEquals(type(response), TextResponse)

        request = Request(self.getURL('nocontenttype'), body=body)
        d = self.download_request(request, Spider('foo'))
        d.addCallback(_test_type)
        return d

    @defer.inlineCallbacks
    def test_download_with_maxsize(self):
        request = Request(self.getURL('file'))

        # 10 is minimal size for this request and the limit is only counted on
        # response body. (regardless of headers)
        d = self.download_request(request, Spider('foo', download_maxsize=10))
        d.addCallback(lambda r: r.body)
        d.addCallback(self.assertEquals, b"0123456789")
        yield d

        d = self.download_request(request, Spider('foo', download_maxsize=9))
        yield self.assertFailure(d, defer.CancelledError, error.ConnectionAborted)

    @defer.inlineCallbacks
    def test_download_with_maxsize_per_req(self):
        meta = {'download_maxsize': 2}
        request = Request(self.getURL('file'), meta=meta)
        d = self.download_request(request, Spider('foo'))
        yield self.assertFailure(d, defer.CancelledError, error.ConnectionAborted)

    @defer.inlineCallbacks
    def test_download_with_small_maxsize_per_spider(self):
        request = Request(self.getURL('file'))
        d = self.download_request(request, Spider('foo', download_maxsize=2))
        yield self.assertFailure(d, defer.CancelledError, error.ConnectionAborted)

    def test_download_with_large_maxsize_per_spider(self):
        request = Request(self.getURL('file'))
        d = self.download_request(request, Spider('foo', download_maxsize=100))
        d.addCallback(lambda r: r.body)
        d.addCallback(self.assertEquals, b"0123456789")
        return d


class Https11TestCase(Http11TestCase):
    scheme = 'https'


class Https11WrongHostnameTestCase(Http11TestCase):
    scheme = 'https'

    # above tests use a server certificate for "localhost",
    # client connection to "localhost" too.
    # here we test that even if the server certificate is for another domain,
    # "www.example.com" in this case,
    # the tests still pass
    keyfile = 'keys/example-com.key.pem'
    certfile = 'keys/example-com.cert.pem'


class Https11InvalidDNSId(Https11TestCase):
    """Connect to HTTPS hosts with IP while certificate uses domain names IDs."""

    def setUp(self):
        super(Https11InvalidDNSId, self).setUp()
        self.host = '127.0.0.1'


class Http11MockServerTestCase(unittest.TestCase):
    """HTTP 1.1 test case with MockServer"""

    def setUp(self):
        self.mockserver = MockServer()
        self.mockserver.__enter__()

    def tearDown(self):
        self.mockserver.__exit__(None, None, None)

    @defer.inlineCallbacks
    def test_download_with_content_length(self):
        crawler = get_crawler(SingleRequestSpider)
        # http://localhost:8998/partial set Content-Length to 1024, use download_maxsize= 1000 to avoid
        # download it
        yield crawler.crawl(seed=Request(url='http://localhost:8998/partial', meta={'download_maxsize': 1000}))
        failure = crawler.spider.meta['failure']
        self.assertIsInstance(failure.value, defer.CancelledError)

    @defer.inlineCallbacks
    def test_download(self):
        crawler = get_crawler(SingleRequestSpider)
        yield crawler.crawl(seed=Request(url='http://localhost:8998'))
        failure = crawler.spider.meta.get('failure')
        self.assertTrue(failure == None)
        reason = crawler.spider.meta['close_reason']
        self.assertTrue(reason, 'finished')

    @defer.inlineCallbacks
    def test_download_gzip_response(self):
        crawler = get_crawler(SingleRequestSpider)
        body = b'1' * 100  # PayloadResource requires body length to be 100
        request = Request('http://localhost:8998/payload', method='POST',
                          body=body, meta={'download_maxsize': 50})
        yield crawler.crawl(seed=request)
        failure = crawler.spider.meta['failure']
        # download_maxsize < 100, hence the CancelledError
        self.assertIsInstance(failure.value, defer.CancelledError)

        if six.PY2:
            request.headers.setdefault(b'Accept-Encoding', b'gzip,deflate')
            request = request.replace(url='http://localhost:8998/xpayload')
            yield crawler.crawl(seed=request)
            # download_maxsize = 50 is enough for the gzipped response
            failure = crawler.spider.meta.get('failure')
            self.assertTrue(failure == None)
            reason = crawler.spider.meta['close_reason']
            self.assertTrue(reason, 'finished')
        else:
            # See issue https://twistedmatrix.com/trac/ticket/8175
            raise unittest.SkipTest("xpayload only enabled for PY2")


class UriResource(resource.Resource):
    """Return the full uri that was requested"""

    def getChild(self, path, request):
        return self

    def render(self, request):
        # Note: this is an ugly hack for CONNECT request timeout test.
        #       Returning some data here fail SSL/TLS handshake
        # ToDo: implement proper HTTPS proxy tests, not faking them.
        if request.method != b'CONNECT':
            return request.uri
        else:
            return b''


class HttpProxyTestCase(unittest.TestCase):
    download_handler_cls = HTTPDownloadHandler

    def setUp(self):
        site = server.Site(UriResource(), timeout=None)
        wrapper = WrappingFactory(site)
        self.port = reactor.listenTCP(0, wrapper, interface='127.0.0.1')
        self.portno = self.port.getHost().port
        self.download_handler = self.download_handler_cls(Settings())
        self.download_request = self.download_handler.download_request

    @defer.inlineCallbacks
    def tearDown(self):
        yield self.port.stopListening()
        if hasattr(self.download_handler, 'close'):
            yield self.download_handler.close()

    def getURL(self, path):
        return "http://127.0.0.1:%d/%s" % (self.portno, path)

    def test_download_with_proxy(self):
        def _test(response):
            self.assertEquals(response.status, 200)
            self.assertEquals(response.url, request.url)
            self.assertEquals(response.body, b'http://example.com')

        http_proxy = self.getURL('')
        request = Request('http://example.com', meta={'proxy': http_proxy})
        return self.download_request(request, Spider('foo')).addCallback(_test)

    def test_download_with_proxy_https_noconnect(self):
        def _test(response):
            self.assertEquals(response.status, 200)
            self.assertEquals(response.url, request.url)
            self.assertEquals(response.body, b'https://example.com')

        http_proxy = '%s?noconnect' % self.getURL('')
        request = Request('https://example.com', meta={'proxy': http_proxy})
        return self.download_request(request, Spider('foo')).addCallback(_test)

    def test_download_without_proxy(self):
        def _test(response):
            self.assertEquals(response.status, 200)
            self.assertEquals(response.url, request.url)
            self.assertEquals(response.body, b'/path/to/resource')

        request = Request(self.getURL('path/to/resource'))
        return self.download_request(request, Spider('foo')).addCallback(_test)


class DeprecatedHttpProxyTestCase(unittest.TestCase):
    """Old deprecated reference to http10 downloader handler"""
    download_handler_cls = HttpDownloadHandler


class Http10ProxyTestCase(HttpProxyTestCase):
    download_handler_cls = HTTP10DownloadHandler


class Http11ProxyTestCase(HttpProxyTestCase):
    download_handler_cls = HTTP11DownloadHandler

    @defer.inlineCallbacks
    def test_download_with_proxy_https_timeout(self):
        """ Test TunnelingTCP4ClientEndpoint """
        http_proxy = self.getURL('')
        domain = 'https://no-such-domain.nosuch'
        request = Request(
            domain, meta={'proxy': http_proxy, 'download_timeout': 0.2})
        d = self.download_request(request, Spider('foo'))
        timeout = yield self.assertFailure(d, error.TimeoutError)
        self.assertIn(domain, timeout.osError)


class HttpDownloadHandlerMock(object):
    def __init__(self, settings):
        pass

    def download_request(self, request, spider):
        return request


class S3AnonTestCase(unittest.TestCase):

    def setUp(self):
        skip_if_no_boto()
        self.s3reqh = S3DownloadHandler(Settings(),
                httpdownloadhandler=HttpDownloadHandlerMock,
                #anon=True, # is implicit
        )
        self.download_request = self.s3reqh.download_request
        self.spider = Spider('foo')

    def test_anon_request(self):
        req = Request('s3://aws-publicdatasets/')
        httpreq = self.download_request(req, self.spider)
        self.assertEqual(hasattr(self.s3reqh, 'anon'), True)
        self.assertEqual(self.s3reqh.anon, True)
        self.assertEqual(
            httpreq.url, 'http://aws-publicdatasets.s3.amazonaws.com/')


class S3TestCase(unittest.TestCase):
    download_handler_cls = S3DownloadHandler

    # test use same example keys than amazon developer guide
    # http://s3.amazonaws.com/awsdocs/S3/20060301/s3-dg-20060301.pdf
    # and the tests described here are the examples from that manual

    AWS_ACCESS_KEY_ID = '0PN5J17HBGZHT7JJ3X82'
    AWS_SECRET_ACCESS_KEY = 'uV3F3YluFJax1cknvbcGwgjvx4QpvB+leU8dUj2o'

    def setUp(self):
        skip_if_no_boto()
        s3reqh = S3DownloadHandler(Settings(), self.AWS_ACCESS_KEY_ID,
                self.AWS_SECRET_ACCESS_KEY,
                httpdownloadhandler=HttpDownloadHandlerMock)
        self.download_request = s3reqh.download_request
        self.spider = Spider('foo')

    @contextlib.contextmanager
    def _mocked_date(self, date):
        try:
            import botocore.auth
        except ImportError:
            yield
        else:
            # We need to mock botocore.auth.formatdate, because otherwise
            # botocore overrides Date header with current date and time
            # and Authorization header is different each time
            with mock.patch('botocore.auth.formatdate') as mock_formatdate:
                mock_formatdate.return_value = date
                yield

    def test_extra_kw(self):
        try:
            S3DownloadHandler(Settings(), extra_kw=True)
        except Exception as e:
            self.assertIsInstance(e, (TypeError, NotConfigured))
        else:
            assert False

    def test_request_signing1(self):
        # gets an object from the johnsmith bucket.
        date ='Tue, 27 Mar 2007 19:36:42 +0000'
        req = Request('s3://johnsmith/photos/puppy.jpg', headers={'Date': date})
        with self._mocked_date(date):
            httpreq = self.download_request(req, self.spider)
        self.assertEqual(httpreq.headers['Authorization'], \
                b'AWS 0PN5J17HBGZHT7JJ3X82:xXjDGYUmKxnwqr5KXNPGldn5LbA=')

    def test_request_signing2(self):
        # puts an object into the johnsmith bucket.
        date = 'Tue, 27 Mar 2007 21:15:45 +0000'
        req = Request('s3://johnsmith/photos/puppy.jpg', method='PUT', headers={
            'Content-Type': 'image/jpeg',
            'Date': date,
            'Content-Length': '94328',
            })
        with self._mocked_date(date):
            httpreq = self.download_request(req, self.spider)
        self.assertEqual(httpreq.headers['Authorization'], \
                b'AWS 0PN5J17HBGZHT7JJ3X82:hcicpDDvL9SsO6AkvxqmIWkmOuQ=')

    def test_request_signing3(self):
        # lists the content of the johnsmith bucket.
        date = 'Tue, 27 Mar 2007 19:42:41 +0000'
        req = Request('s3://johnsmith/?prefix=photos&max-keys=50&marker=puppy', \
                method='GET', headers={
                    'User-Agent': 'Mozilla/5.0',
                    'Date': date,
                    })
        with self._mocked_date(date):
            httpreq = self.download_request(req, self.spider)
        self.assertEqual(httpreq.headers['Authorization'], \
                b'AWS 0PN5J17HBGZHT7JJ3X82:jsRt/rhG+Vtp88HrYL706QhE4w4=')

    def test_request_signing4(self):
        # fetches the access control policy sub-resource for the 'johnsmith' bucket.
        date = 'Tue, 27 Mar 2007 19:44:46 +0000'
        req = Request('s3://johnsmith/?acl',
            method='GET', headers={'Date': date})
        with self._mocked_date(date):
            httpreq = self.download_request(req, self.spider)
        self.assertEqual(httpreq.headers['Authorization'], \
                b'AWS 0PN5J17HBGZHT7JJ3X82:thdUi9VAkzhkniLj96JIrOPGi0g=')

    def test_request_signing5(self):
        try: import botocore
        except ImportError: pass
        else:
            raise unittest.SkipTest(
                'botocore does not support overriding date with x-amz-date')
        # deletes an object from the 'johnsmith' bucket using the
        # path-style and Date alternative.
        date = 'Tue, 27 Mar 2007 21:20:27 +0000'
        req = Request('s3://johnsmith/photos/puppy.jpg', \
                method='DELETE', headers={
                    'Date': date,
                    'x-amz-date': 'Tue, 27 Mar 2007 21:20:26 +0000',
                    })
        with self._mocked_date(date):
            httpreq = self.download_request(req, self.spider)
        # botocore does not override Date with x-amz-date
        self.assertEqual(httpreq.headers['Authorization'],
                b'AWS 0PN5J17HBGZHT7JJ3X82:k3nL7gH3+PadhTEVn5Ip83xlYzk=')

    def test_request_signing6(self):
        # uploads an object to a CNAME style virtual hosted bucket with metadata.
        date = 'Tue, 27 Mar 2007 21:06:08 +0000'
        req = Request('s3://static.johnsmith.net:8080/db-backup.dat.gz', \
                method='PUT', headers={
                    'User-Agent': 'curl/7.15.5',
                    'Host': 'static.johnsmith.net:8080',
                    'Date': date,
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
        with self._mocked_date(date):
            httpreq = self.download_request(req, self.spider)
        self.assertEqual(httpreq.headers['Authorization'], \
                b'AWS 0PN5J17HBGZHT7JJ3X82:C0FlOtU8Ylb9KDTpZqYkZPX91iI=')

    def test_request_signing7(self):
        # ensure that spaces are quoted properly before signing
        date = 'Tue, 27 Mar 2007 19:42:41 +0000'
        req = Request(
            ("s3://johnsmith/photos/my puppy.jpg"
             "?response-content-disposition=my puppy.jpg"),
            method='GET',
            headers={'Date': date},
            )
        with self._mocked_date(date):
            httpreq = self.download_request(req, self.spider)
        self.assertEqual(
            httpreq.headers['Authorization'],
            b'AWS 0PN5J17HBGZHT7JJ3X82:+CfvG8EZ3YccOrRVMXNaK2eKZmM=')


class BaseFTPTestCase(unittest.TestCase):

    username = "scrapy"
    password = "passwd"
    req_meta = {"ftp_user": username, "ftp_password": password}

    if six.PY3:
        skip = "Twisted missing ftp support for PY3"

    def setUp(self):
        from twisted.protocols.ftp import FTPRealm, FTPFactory
        from scrapy.core.downloader.handlers.ftp import FTPDownloadHandler

        # setup dirs and test file
        self.directory = self.mktemp()
        os.mkdir(self.directory)
        userdir = os.path.join(self.directory, self.username)
        os.mkdir(userdir)
        fp = FilePath(userdir)
        fp.child('file.txt').setContent("I have the power!")
        fp.child('file with spaces.txt').setContent("Moooooooooo power!")

        # setup server
        realm = FTPRealm(anonymousRoot=self.directory, userHome=self.directory)
        p = portal.Portal(realm)
        users_checker = checkers.InMemoryUsernamePasswordDatabaseDontUse()
        users_checker.addUser(self.username, self.password)
        p.registerChecker(users_checker, credentials.IUsernamePassword)
        self.factory = FTPFactory(portal=p)
        self.port = reactor.listenTCP(0, self.factory, interface="127.0.0.1")
        self.portNum = self.port.getHost().port
        self.download_handler = FTPDownloadHandler(Settings())
        self.addCleanup(self.port.stopListening)

    def tearDown(self):
        shutil.rmtree(self.directory)

    def _add_test_callbacks(self, deferred, callback=None, errback=None):
        def _clean(data):
            self.download_handler.client.transport.loseConnection()
            return data
        deferred.addCallback(_clean)
        if callback:
            deferred.addCallback(callback)
        if errback:
            deferred.addErrback(errback)
        return deferred

    def test_ftp_download_success(self):
        request = Request(url="ftp://127.0.0.1:%s/file.txt" % self.portNum,
                          meta=self.req_meta)
        d = self.download_handler.download_request(request, None)

        def _test(r):
            self.assertEqual(r.status, 200)
            self.assertEqual(r.body, 'I have the power!')
            self.assertEqual(r.headers, {'Local Filename': [''], 'Size': ['17']})
        return self._add_test_callbacks(d, _test)

    def test_ftp_download_path_with_spaces(self):
        request = Request(
            url="ftp://127.0.0.1:%s/file with spaces.txt" % self.portNum,
            meta=self.req_meta
        )
        d = self.download_handler.download_request(request, None)

        def _test(r):
            self.assertEqual(r.status, 200)
            self.assertEqual(r.body, 'Moooooooooo power!')
            self.assertEqual(r.headers, {'Local Filename': [''], 'Size': ['18']})
        return self._add_test_callbacks(d, _test)

    def test_ftp_download_notexist(self):
        request = Request(url="ftp://127.0.0.1:%s/notexist.txt" % self.portNum,
                          meta=self.req_meta)
        d = self.download_handler.download_request(request, None)

        def _test(r):
            self.assertEqual(r.status, 404)
        return self._add_test_callbacks(d, _test)

    def test_ftp_local_filename(self):
        local_fname = "/tmp/file.txt"
        meta = {"ftp_local_filename": local_fname}
        meta.update(self.req_meta)
        request = Request(url="ftp://127.0.0.1:%s/file.txt" % self.portNum,
                          meta=meta)
        d = self.download_handler.download_request(request, None)

        def _test(r):
            self.assertEqual(r.body, local_fname)
            self.assertEqual(r.headers, {'Local Filename': ['/tmp/file.txt'], 'Size': ['17']})
            self.assertTrue(os.path.exists(local_fname))
            with open(local_fname) as f:
                self.assertEqual(f.read(), "I have the power!")
            os.remove(local_fname)
        return self._add_test_callbacks(d, _test)


class FTPTestCase(BaseFTPTestCase):

    def test_invalid_credentials(self):
        from twisted.protocols.ftp import ConnectionLost

        meta = dict(self.req_meta)
        meta.update({"ftp_password": 'invalid'})
        request = Request(url="ftp://127.0.0.1:%s/file.txt" % self.portNum,
                          meta=meta)
        d = self.download_handler.download_request(request, None)

        def _test(r):
            self.assertEqual(r.type, ConnectionLost)
        return self._add_test_callbacks(d, errback=_test)


class AnonymousFTPTestCase(BaseFTPTestCase):

    username = "anonymous"
    req_meta = {}

    def setUp(self):
        from twisted.protocols.ftp import FTPRealm, FTPFactory
        from scrapy.core.downloader.handlers.ftp import FTPDownloadHandler

        # setup dir and test file
        self.directory = self.mktemp()
        os.mkdir(self.directory)

        fp = FilePath(self.directory)
        fp.child('file.txt').setContent("I have the power!")
        fp.child('file with spaces.txt').setContent("Moooooooooo power!")

        # setup server for anonymous access
        realm = FTPRealm(anonymousRoot=self.directory)
        p = portal.Portal(realm)
        p.registerChecker(checkers.AllowAnonymousAccess(),
                          credentials.IAnonymous)

        self.factory = FTPFactory(portal=p,
                                  userAnonymous=self.username)
        self.port = reactor.listenTCP(0, self.factory, interface="127.0.0.1")
        self.portNum = self.port.getHost().port
        self.download_handler = FTPDownloadHandler(Settings())
        self.addCleanup(self.port.stopListening)

    def tearDown(self):
        shutil.rmtree(self.directory)
