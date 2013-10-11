import re
from twisted.trial import unittest
from twisted.internet import defer

from scrapy.utils.testsite import SiteTest
from scrapy.utils.testproc import ProcessTest
from scrapy.utils.url import parse_url

class ProbeTest(ProcessTest, SiteTest, unittest.TestCase):

    command = 'probe' 
    
    @defer.inlineCallbacks
    def test_output(self):
        url = self.url('/probe');
        _, out, _ = yield self.execute([url, 'QWERTY'])
        expect = "Found set of working headers:\n{'" \
            "Accept-Language': ['en-US,en;q=0.8,pt;q=0.6,es;q=0.4,fr;q=0.2'], "\
            "'Accept-Encoding': ['x-gzip,gzip,deflate'], "\
            "'Connection': ['keep-alive'], "\
            "'Accept': ['application/xml,application/xhtml+xml,text/html;q=0.9,"\
                "text/plain;q=0.8,*/*;q=0.5'], "\
            "'User-Agent': ['Mozilla/4.0 (compatible; MSIE 5.5; Windows NT)'], "\
            "'Accept-Charset': ['ISO-8859-1'], "\
            "'Host': ['" + parse_url(url).netloc + "'], "\
            "'Cache-Control': ['no-cache']}"
        self.assertEqual(out.strip(), expect)
    
    @defer.inlineCallbacks
    def test_no_result(self):
        _, out, _ = yield self.execute([self.url('/probe'), 'QWERTeY'])
        self.assertEqual(out.strip(), "Set of working headers not found.")

