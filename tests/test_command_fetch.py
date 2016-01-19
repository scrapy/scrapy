from twisted.trial import unittest
from twisted.internet import defer

from scrapy.utils.testsite import SiteTest
from scrapy.utils.testproc import ProcessTest


class FetchTest(ProcessTest, SiteTest, unittest.TestCase):

    command = 'fetch'

    @defer.inlineCallbacks
    def test_output(self):
        _, out, _ = yield self.execute([self.url('/text')])
        self.assertEqual(out.strip(), b'Works')

    @defer.inlineCallbacks
    def test_headers(self):
        _, out, _ = yield self.execute([self.url('/text'), '--headers'])
        out = out.replace(b'\r', b'') # required on win32
        assert b'Server: TwistedWeb' in out, out
        assert b'Content-Type: text/plain' in out
