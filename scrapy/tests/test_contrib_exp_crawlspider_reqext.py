from twisted.trial import unittest

from scrapy.http import Request
from scrapy.http import HtmlResponse
from scrapy.tests import get_testdata

from scrapy.contrib_exp.crawlspider.reqext import BaseSgmlRequestExtractor
from scrapy.contrib_exp.crawlspider.reqext import SgmlRequestExtractor
from scrapy.contrib_exp.crawlspider.reqext import XPathRequestExtractor

class AbstractRequestExtractorTest(unittest.TestCase):

    def _requests_equals(self, list1, list2):
        """Compares request's urls and link_text"""
        for (r1, r2) in zip(list1, list2):
            if r1.url != r2.url:
                return False
            if r1.meta['link_text'] != r2.meta['link_text']:
                return False
        # all equal
        return True


class RequestExtractorTest(AbstractRequestExtractorTest):

    def test_basic(self):
        base_url = 'http://example.org/somepage/index.html'
        html = """<html><head><title>Page title<title>
        <body><p><a href="item/12.html">Item 12</a></p>
        <p><a href="/about.html">About us</a></p>
        <img src="/logo.png" alt="Company logo (not a link)" />
        <p><a href="../othercat.html">Other category</a></p>
        <p><a href="/" /></p></body></html>"""
        requests = [
            Request('http://example.org/somepage/item/12.html',
                    meta={'link_text': 'Item 12'}),
            Request('http://example.org/about.html',
                    meta={'link_text': 'About us'}),
            Request('http://example.org/othercat.html',
                    meta={'link_text': 'Other category'}),
            Request('http://example.org/',
                    meta={'link_text': ''}),
            ]

        response = HtmlResponse(base_url, body=html)
        reqx = BaseSgmlRequestExtractor() # default: tag=a, attr=href

        self.failUnless(
            self._requests_equals(requests, reqx.extract_requests(response))
            )

    def test_base_url(self):
        reqx = BaseSgmlRequestExtractor()

        html = """<html><head><title>Page title<title>
        <base href="http://otherdomain.com/base/" />
        <body><p><a href="item/12.html">Item 12</a></p>
        </body></html>"""
        response = HtmlResponse("https://example.org/p/index.html", body=html)
        reqs = reqx.extract_requests(response)
        self.failUnless(self._requests_equals( \
            [Request('http://otherdomain.com/base/item/12.html', \
                    meta={'link_text': 'Item 12'})], reqs), reqs)

        # base url is an absolute path and relative to host
        html = """<html><head><title>Page title<title>
        <base href="/" />
        <body><p><a href="item/12.html">Item 12</a></p>
        </body></html>"""
        response = HtmlResponse("https://example.org/p/index.html", body=html)
        reqs = reqx.extract_requests(response)
        self.failUnless(self._requests_equals( \
            [Request('https://example.org/item/12.html', \
                    meta={'link_text': 'Item 12'})], reqs), reqs)

        # base url has no scheme
        html = """<html><head><title>Page title<title>
        <base href="//noscheme.com/base/" />
        <body><p><a href="item/12.html">Item 12</a></p>
        </body></html>"""
        response = HtmlResponse("https://example.org/p/index.html", body=html)
        reqs = reqx.extract_requests(response)
        self.failUnless(self._requests_equals( \
            [Request('https://noscheme.com/base/item/12.html', \
                    meta={'link_text': 'Item 12'})], reqs), reqs)

    def test_extraction_encoding(self):
        #TODO: use own fixtures
        body = get_testdata('link_extractor', 'linkextractor_noenc.html')
        response_utf8 = HtmlResponse(url='http://example.com/utf8', body=body,
                        headers={'Content-Type': ['text/html; charset=utf-8']})
        response_noenc = HtmlResponse(url='http://example.com/noenc',
                            body=body)
        body = get_testdata('link_extractor', 'linkextractor_latin1.html')
        response_latin1 = HtmlResponse(url='http://example.com/latin1',
                            body=body)

        reqx = BaseSgmlRequestExtractor()
        self.failUnless(
            self._requests_equals(
                reqx.extract_requests(response_utf8),
                [ Request(url='http://example.com/sample_%C3%B1.html',
                          meta={'link_text': ''}),
                  Request(url='http://example.com/sample_%E2%82%AC.html',
                          meta={'link_text':
                                'sample \xe2\x82\xac text'.decode('utf-8')}) ]
                )
            )

        self.failUnless(
            self._requests_equals(
                reqx.extract_requests(response_noenc),
                [ Request(url='http://example.com/sample_%C3%B1.html',
                          meta={'link_text': ''}),
                  Request(url='http://example.com/sample_%E2%82%AC.html',
                          meta={'link_text':
                                'sample \xe2\x82\xac text'.decode('utf-8')}) ]
                )
            )

        self.failUnless(
            self._requests_equals(
                reqx.extract_requests(response_latin1),
                [ Request(url='http://example.com/sample_%F1.html',
                          meta={'link_text': ''}),
                  Request(url='http://example.com/sample_%E1.html',
                          meta={'link_text':
                                'sample \xe1 text'.decode('latin1')}) ]
                )
            )


class SgmlRequestExtractorTest(AbstractRequestExtractorTest):
    pass


class XPathRequestExtractorTest(AbstractRequestExtractorTest):

    def setUp(self):
        # TODO: use own fixtures
        body = get_testdata('link_extractor', 'sgml_linkextractor.html')
        self.response = HtmlResponse(url='http://example.com/index', body=body)


    def test_restrict_xpaths(self):
        reqx = XPathRequestExtractor('//div[@id="subwrapper"]')
        self.failUnless(
            self._requests_equals(
                reqx.extract_requests(self.response),
                [ Request(url='http://example.com/sample1.html',
                          meta={'link_text': ''}),
                  Request(url='http://example.com/sample2.html',
                          meta={'link_text': 'sample 2'}) ]
                )
            )

