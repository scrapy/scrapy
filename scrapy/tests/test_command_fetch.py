from twisted.trial import unittest
from twisted.internet import defer

from scrapy.utils.testsite import SiteTest
from scrapy.utils.testproc import ProcessTest


class FetchTest(ProcessTest, SiteTest, unittest.TestCase):

    command = 'fetch'

    @defer.inlineCallbacks
    def test_output(self):
        _, out, _ = yield self.execute([self.url('/text')])
        self.assertEqual(out.strip(), 'Works')

    @defer.inlineCallbacks
    def test_headers(self):
        _, out, _ = yield self.execute([self.url('/text'), '--headers'])
        out = out.replace('\r', '') # required on win32
        assert 'Server: TwistedWeb' in out
        assert 'Content-Type: text/plain' in out

    @defer.inlineCallbacks
    def test_post(self):
        _, out, _ = yield self.execute([self.url('/post'), '--data', 'Name=test'])
        out = out.replace('\r', '') # required on win32
        expect = '<html><body>You submitted: test</body></html>'
        self.assertEqual(out.strip(), expect)

    @defer.inlineCallbacks
    def test_post_content_type(self):
        _, out, _ = yield self.execute([self.url('/post'), '--data', 'Name=test', \
                                        '--data-content-type', 'application/x-www-form-urlencoded'])
        out = out.replace('\r', '') # required on win32
        expect = '<html><body>You submitted: test</body></html>'
        self.assertEqual(out.strip(), expect)

    @defer.inlineCallbacks
    def test_post_content_type_headers(self):
        _, out, _ = yield self.execute([self.url('/text'), '--data', 'Name=test', \
                                        '--data-content-type', 'application/xml', \
                                        '--headers'])
        out = out.replace('\r', '') # required on win32
        assert 'Content-Type: application/xml' in out

    @defer.inlineCallbacks
    def test_data_binary(self):
        _, out, _ = yield self.execute([self.url('/post'), '--data-binary', \
                                        'scrapy/tests/sample_data/data'])
        out = out.replace('\r', '') # required on win32
        expect = '<html><body>You submitted: Test</body></html>'
        self.assertEqual(out.strip(), expect)

    @defer.inlineCallbacks
    def test_data_urlencode(self):
        _, out, _ = yield self.execute([self.url('/post'), '--data-urlencode', \
                                        'Name=Test@=test'])
        out = out.replace('\r', '') # required on win32
        expect = '<html><body>You submitted: Test@=test</body></html>'
        self.assertEqual(out.strip(), expect)
