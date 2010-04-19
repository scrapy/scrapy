from twisted.trial import unittest

from scrapy.http import Request
from scrapy.http import Response

from scrapy.contrib_exp.crawlspider.matchers import BaseMatcher
from scrapy.contrib_exp.crawlspider.matchers import UrlMatcher
from scrapy.contrib_exp.crawlspider.matchers import UrlRegexMatcher
from scrapy.contrib_exp.crawlspider.matchers import UrlListMatcher

import re

class MatchersTest(unittest.TestCase):

    def setUp(self):
        pass

    def test_base_matcher(self):
        matcher = BaseMatcher()

        request = Request('http://example.com')
        response = Response('http://example.com')

        self.assertTrue(matcher.matches_request(request))
        self.assertTrue(matcher.matches_response(response))

    def test_url_matcher(self):
        matcher = UrlMatcher('http://example.com')

        request = Request('http://example.com')
        response = Response('http://example.com')

        self.failUnless(matcher.matches_request(request))
        self.failUnless(matcher.matches_request(response))

        request = Request('http://example2.com')
        response = Response('http://example2.com')

        self.failIf(matcher.matches_request(request))
        self.failIf(matcher.matches_request(response))

    def test_url_regex_matcher(self):
        matcher = UrlRegexMatcher(r'sample')
        urls = (
            'http://example.com/sample1.html',
            'http://example.com/sample2.html',
            'http://example.com/sample3.html',
            'http://example.com/sample4.html',
            )
        for url in urls:
            request, response = Request(url), Response(url)
            self.failUnless(matcher.matches_request(request))
            self.failUnless(matcher.matches_response(response))

        matcher = UrlRegexMatcher(r'sample_fail')
        for url in urls:
            request, response = Request(url), Response(url)
            self.failIf(matcher.matches_request(request))
            self.failIf(matcher.matches_response(response))

        matcher = UrlRegexMatcher(r'SAMPLE\d+', re.IGNORECASE)
        for url in urls:
            request, response = Request(url), Response(url)
            self.failUnless(matcher.matches_request(request))
            self.failUnless(matcher.matches_response(response))

    def test_url_list_matcher(self):
        urls = (
            'http://example.com/sample1.html',
            'http://example.com/sample2.html',
            'http://example.com/sample3.html',
            'http://example.com/sample4.html',
            )
        urls2 = (
            'http://example.com/sample5.html',
            'http://example.com/sample6.html',
            'http://example.com/sample7.html',
            'http://example.com/sample8.html',
            'http://example.com/',
            )
        matcher = UrlListMatcher(urls)

        # match urls
        for url in urls:
            request, response = Request(url), Response(url)
            self.failUnless(matcher.matches_request(request))
            self.failUnless(matcher.matches_response(response))

        # non-match urls
        for url in urls2:
            request, response = Request(url), Response(url)
            self.failIf(matcher.matches_request(request))
            self.failIf(matcher.matches_response(response))

