from os.path import join

from twisted.trial import unittest
from twisted.internet import defer

from scrapy.commands.shell import guess_scheme
from scrapy.utils.testsite import SiteTest
from scrapy.utils.testproc import ProcessTest

from tests import tests_datadir


class ShellURLTest(unittest.TestCase):

    def test_file_uri_relative001(self):
        # FIXME: 'index.html' is interpreted as a domain name
        #        is this correct?
        url = guess_scheme('index.html')
        assert url.startswith('http://')

    def test_file_uri_relative002(self):
        url = guess_scheme('./index.html')
        assert url.startswith('file://')

    def test_file_uri_relative003(self):
        url = guess_scheme('../data/index.html')
        assert url.startswith('file://')

    def test_file_uri_relative004(self):
        url = guess_scheme('subdir/index.html')
        assert url.startswith('file://')

    def test_file_uri_absolute001(self):
        """Absolute file paths get prepended with "file://" scheme"""
        iurl = '/home/user/www/index.html'
        url = guess_scheme(iurl)
        self.assertEquals(url, 'file://'+iurl)

    def test_file_uri_scheme(self):
        """Output File URI does not change if "file://" scheme is set"""
        iurl = 'file:///home/user/www/index.html'
        url = guess_scheme(iurl)
        self.assertEquals(url, iurl)

    def test_file_uri_windows(self):
        raise unittest.SkipTest("Windows filepath are not supported for scrapy shell")
        url = guess_scheme('C:\absolute\path\to\a\file.html')
        assert url.startswith('file://')

    def test_http_url_001(self):
        url = guess_scheme('index.html')
        assert url.startswith('http://')

    def test_http_url_002(self):
        url = guess_scheme('example.com')
        assert url.startswith('http://')

    def test_http_url_003(self):
        url = guess_scheme('www.example.com')
        assert url.startswith('http://')

    def test_http_url_004(self):
        url = guess_scheme('www.example.com/index')
        assert url.startswith('http://')

    def test_http_url_005(self):
        url = guess_scheme('www.example.com/index.html')
        assert url.startswith('http://')

    def test_http_url_scheme(self):
        """An full HTTP URL is unaltered"""
        iurl = 'http://www.example.com/index.html'
        url = guess_scheme(iurl)
        self.assertEquals(url, iurl)


class ShellTest(ProcessTest, SiteTest, unittest.TestCase):

    command = 'shell'

    @defer.inlineCallbacks
    def test_empty(self):
        _, out, _ = yield self.execute(['-c', 'item'])
        assert b'{}' in out

    @defer.inlineCallbacks
    def test_response_body(self):
        _, out, _ = yield self.execute([self.url('/text'), '-c', 'response.body'])
        assert b'Works' in out

    @defer.inlineCallbacks
    def test_response_type_text(self):
        _, out, _ = yield self.execute([self.url('/text'), '-c', 'type(response)'])
        assert b'TextResponse' in out

    @defer.inlineCallbacks
    def test_response_type_html(self):
        _, out, _ = yield self.execute([self.url('/html'), '-c', 'type(response)'])
        assert b'HtmlResponse' in out

    @defer.inlineCallbacks
    def test_response_selector_html(self):
        xpath = 'response.xpath("//p[@class=\'one\']/text()").extract()[0]'
        _, out, _ = yield self.execute([self.url('/html'), '-c', xpath])
        self.assertEqual(out.strip(), b'Works')

    @defer.inlineCallbacks
    def test_response_encoding_gb18030(self):
        _, out, _ = yield self.execute([self.url('/enc-gb18030'), '-c', 'response.encoding'])
        self.assertEqual(out.strip(), b'gb18030')

    @defer.inlineCallbacks
    def test_redirect(self):
        _, out, _ = yield self.execute([self.url('/redirect'), '-c', 'response.url'])
        assert out.strip().endswith(b'/redirected')

    @defer.inlineCallbacks
    def test_request_replace(self):
        url = self.url('/text')
        code = "fetch('{0}') or fetch(response.request.replace(method='POST'))"
        errcode, out, _ = yield self.execute(['-c', code.format(url)])
        self.assertEqual(errcode, 0, out)

    @defer.inlineCallbacks
    def test_local_file(self):
        filepath = join(tests_datadir, 'test_site/index.html')
        _, out, _ = yield self.execute([filepath, '-c', 'item'])
        assert b'{}' in out

    @defer.inlineCallbacks
    def test_local_nofile(self):
        filepath = 'file:///tests/sample_data/test_site/nothinghere.html'
        errcode, out, err = yield self.execute([filepath, '-c', 'item'],
                                       check_code=False)
        self.assertEqual(errcode, 1, out or err)
        self.assertIn(b'No such file or directory', err)

    @defer.inlineCallbacks
    def test_dns_failures(self):
        url = 'www.somedomainthatdoesntexi.st'
        errcode, out, err = yield self.execute([url, '-c', 'item'],
                                       check_code=False)
        self.assertEqual(errcode, 1, out or err)
        self.assertIn(b'DNS lookup failed', err)
