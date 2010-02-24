from twisted.trial import unittest

from scrapy.http import Request
from scrapy.http import HtmlResponse
from scrapy.item import BaseItem
from scrapy.utils.spider import iterate_spider_output

# basics
from scrapy.contrib_exp.crawlspider import CrawlSpider
from scrapy.contrib_exp.crawlspider import Rule

# matchers
from scrapy.contrib_exp.crawlspider.matchers import BaseMatcher
from scrapy.contrib_exp.crawlspider.matchers import UrlRegexMatcher
from scrapy.contrib_exp.crawlspider.matchers import UrlListMatcher

# extractors
from scrapy.contrib_exp.crawlspider.reqext import SgmlRequestExtractor

# processors
from scrapy.contrib_exp.crawlspider.reqproc import Canonicalize
from scrapy.contrib_exp.crawlspider.reqproc import FilterDupes


# mock items
class Item1(BaseItem):
    pass

class Item2(BaseItem):
    pass

class Item3(BaseItem):
    pass


class CrawlSpiderTest(unittest.TestCase):

    def spider_factory(self, rules=[],
                       extractors=[], processors=[],
                       start_urls=[]):
        # mock spider
        class Spider(CrawlSpider):
            def parse_item1(self, response):
                return Item1()
            
            def parse_item2(self, response):
                return Item2()

            def parse_item3(self, response):
                return Item3()

            def parse_request1(self, response):
                return Request('http://example.org/request1')

            def parse_request2(self, response):
                return Request('http://example.org/request2')

        Spider.start_urls = start_urls
        Spider.rules = rules
        Spider.request_extractors = extractors
        Spider.request_processors = processors

        return Spider()

    def test_start_url_auto_rule(self):
        spider = self.spider_factory()
        # zero spider rules
        self.failUnlessEqual(len(spider.rules), 0)
        self.failUnlessEqual(len(spider._rulesman._rules), 0)

        spider = self.spider_factory(start_urls=['http://example.org'])

        self.failUnlessEqual(len(spider.rules), 0)
        self.failUnlessEqual(len(spider._rulesman._rules), 1)

    def test_start_url_matcher(self):
        url = 'http://example.org'
        spider = self.spider_factory(start_urls=[url])

        response = HtmlResponse(url)

        rule = spider._rulesman.get_rule_from_response(response)
        self.failUnless(isinstance(rule.matcher, UrlListMatcher))

        response = HtmlResponse(url + '/item.html')

        rule = spider._rulesman.get_rule_from_response(response)
        self.failUnless(rule is None)

        # TODO: remove this block
        # in previous version get_rule returns rule from response.request
        response.request = Request(url)
        rule = spider._rulesman.get_rule_from_response(response.request)
        self.failUnless(isinstance(rule.matcher, UrlListMatcher))
        self.failUnlessEqual(rule.follow, True)

    def test_parse_callback(self):
        response = HtmlResponse('http://example.org')
        rules = (
            Rule(BaseMatcher(), 'parse_item1'),
            )
        spider = self.spider_factory(rules)

        result = list(spider.parse(response))
        self.failUnlessEqual(len(result), 1)
        self.failUnless(isinstance(result[0], Item1))

    def test_crawling_start_url(self):
        url = 'http://example.org/'
        html = """<html><head><title>Page title<title>
        <body><p><a href="item/12.html">Item 12</a></p>
        <p><a href="/about.html">About us</a></p>
        <img src="/logo.png" alt="Company logo (not a link)" />
        <p><a href="../othercat.html">Other category</a></p>
        <p><a href="/" /></p></body></html>"""
        response = HtmlResponse(url, body=html)

        extractors = (SgmlRequestExtractor(), )
        spider = self.spider_factory(start_urls=[url],
                                     extractors=extractors)
        result = list(spider.parse(response))

        # 1 request extracted: example.org/ 
        # because requests returns only matching
        self.failUnlessEqual(len(result), 1)

        # we will add catch-all rule to extract all
        callback = lambda x: None
        rules = [Rule(r'\.html$', callback=callback)]
        spider = self.spider_factory(rules, start_urls=[url],
                                     extractors=extractors)
        result = list(spider.parse(response))

        # 4 requests extracted
        # 3 of .html pattern
        # 1 of start url patter
        self.failUnlessEqual(len(result), 4)

    def test_crawling_simple_rule(self):
        url = 'http://example.org/somepage/index.html'
        html = """<html><head><title>Page title<title>
        <body><p><a href="item/12.html">Item 12</a></p>
        <p><a href="/about.html">About us</a></p>
        <img src="/logo.png" alt="Company logo (not a link)" />
        <p><a href="../othercat.html">Other category</a></p>
        <p><a href="/" /></p></body></html>"""

        response = HtmlResponse(url, body=html)

        rules = (
            # first response callback
            Rule(r'index\.html', 'parse_item1'),
            )
        spider = self.spider_factory(rules)
        result = list(spider.parse(response))

        # should return Item1
        self.failUnlessEqual(len(result), 1)
        self.failUnless(isinstance(result[0], Item1))

        # test request generation
        rules = (
            # first response without callback and follow flag
            Rule(r'index\.html', follow=True),
            Rule(r'(\.html|/)$', 'parse_item1'),
            )
        spider = self.spider_factory(rules)
        result = list(spider.parse(response))

        # 0 because spider does not have extractors
        self.failUnlessEqual(len(result), 0)

        extractors = (SgmlRequestExtractor(), )

        # instance spider with extractor
        spider = self.spider_factory(rules, extractors)
        result = list(spider.parse(response))
        # 4 requests extracted
        self.failUnlessEqual(len(result), 4)

    def test_crawling_multiple_rules(self):
        html = """<html><head><title>Page title<title>
        <body><p><a href="item/12.html">Item 12</a></p>
        <p><a href="/about.html">About us</a></p>
        <img src="/logo.png" alt="Company logo (not a link)" />
        <p><a href="../othercat.html">Other category</a></p>
        <p><a href="/" /></p></body></html>"""

        response = HtmlResponse('http://example.org/index.html', body=html)
        response1 = HtmlResponse('http://example.org/1.html')
        response2 = HtmlResponse('http://example.org/othercat.html')

        rules = (
            Rule(r'\d+\.html$', 'parse_item1'),
            Rule(r'othercat\.html$', 'parse_item2'),
            # follow-only rules
            Rule(r'index\.html', 'parse_item3', follow=True)
            )
        extractors = [SgmlRequestExtractor()]
        spider = self.spider_factory(rules, extractors)

        result = list(spider.parse(response))
        # 1 Item 2 Requests
        self.failUnlessEqual(len(result), 3)
        # parse_item3
        self.failUnless(isinstance(result[0], Item3))
        only_requests = lambda r: isinstance(r, Request)
        requests = filter(only_requests, result[1:])
        self.failUnlessEqual(len(requests), 2)
        self.failUnless(all(requests))

        result1 = list(spider.parse(response1))
        # parse_item1
        self.failUnlessEqual(len(result1), 1)
        self.failUnless(isinstance(result1[0], Item1))

        result2 = list(spider.parse(response2))
        # parse_item2
        self.failUnlessEqual(len(result2), 1)
        self.failUnless(isinstance(result2[0], Item2))


