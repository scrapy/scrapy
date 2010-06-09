from twisted.internet import defer
from twisted.trial import unittest

from scrapy.http import Request
from scrapy.http import HtmlResponse
from scrapy.utils.python import equal_attributes

from scrapy.contrib_exp.crawlspider.reqext import SgmlRequestExtractor
from scrapy.contrib_exp.crawlspider.reqgen import RequestGenerator
from scrapy.contrib_exp.crawlspider.reqproc import Canonicalize
from scrapy.contrib_exp.crawlspider.reqproc import FilterDomain
from scrapy.contrib_exp.crawlspider.reqproc import FilterUrl
from scrapy.contrib_exp.crawlspider.reqproc import FilterDupes

class RequestGeneratorTest(unittest.TestCase):

    def setUp(self):
        url = 'http://example.org/somepage/index.html'
        html = """<html><head><title>Page title<title>
        <body><p><a href="item/12.html">Item 12</a></p>
        <p><a href="/about.html">About us</a></p>
        <img src="/logo.png" alt="Company logo (not a link)" />
        <p><a href="../othercat.html">Other category</a></p>
        <p><a href="/" /></p></body></html>"""

        self.response = HtmlResponse(url, body=html)
        self.deferred = defer.Deferred()
        self.requests = [
            Request('http://example.org/somepage/item/12.html',
                    meta={'link_text': 'Item 12'}),
            Request('http://example.org/about.html',
                    meta={'link_text': 'About us'}),
            Request('http://example.org/othercat.html',
                    meta={'link_text': 'Other category'}),
            Request('http://example.org/',
                    meta={'link_text': ''}),
            ]

    def _equal_requests_list(self, list1, list2):
        list1 = list(list1)
        list2 = list(list2)
        if not len(list1) == len(list2):
            return False

        for (req1, req2) in zip(list1, list2):
            if not equal_attributes(req1, req2, ['url']):
                return False
        return True

    def test_basic(self):
        reqgen = RequestGenerator([], [], callback=self.deferred)
        # returns generator
        requests = reqgen.generate_requests(self.response)
        self.failUnlessEqual(list(requests), [])

    def test_request_extractor(self):
        extractors = [
            SgmlRequestExtractor()
            ]

        # extract all requests
        reqgen = RequestGenerator(extractors, [], callback=self.deferred)
        requests = reqgen.generate_requests(self.response)
        self.failUnless(self._equal_requests_list(requests, self.requests))

    def test_request_processor(self):
        extractors = [
            SgmlRequestExtractor()
            ]

        processors = [
            Canonicalize(),
            FilterDupes(),
            ]

        reqgen = RequestGenerator(extractors, processors, callback=self.deferred)
        requests = reqgen.generate_requests(self.response)
        self.failUnless(self._equal_requests_list(requests, self.requests))

        # filter domain
        processors = [
            Canonicalize(),
            FilterDupes(),
            FilterDomain(deny='example.org'),
            ]

        reqgen = RequestGenerator(extractors, processors, callback=self.deferred)
        requests = reqgen.generate_requests(self.response)
        self.failUnlessEqual(list(requests), [])

        # filter url
        processors = [
            Canonicalize(),
            FilterDupes(),
            FilterUrl(deny=(r'about', r'othercat')),
            ]

        reqgen = RequestGenerator(extractors, processors, callback=self.deferred)
        requests = reqgen.generate_requests(self.response)

        self.failUnless(self._equal_requests_list(requests, [
                Request('http://example.org/somepage/item/12.html',
                        meta={'link_text': 'Item 12'}),
                Request('http://example.org/',
                        meta={'link_text': ''}),
                ]))

        processors = [
            Canonicalize(),
            FilterDupes(),
            FilterUrl(allow=r'/somepage/'),
            ]

        reqgen = RequestGenerator(extractors, processors, callback=self.deferred)
        requests = reqgen.generate_requests(self.response)

        self.failUnless(self._equal_requests_list(requests, [
                Request('http://example.org/somepage/item/12.html',
                        meta={'link_text': 'Item 12'}),
                ]))

 
 
        
