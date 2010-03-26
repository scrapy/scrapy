from twisted.trial import unittest

from scrapy.http import Request

from scrapy.contrib_exp.crawlspider.reqproc import Canonicalize
from scrapy.contrib_exp.crawlspider.reqproc import FilterDomain
from scrapy.contrib_exp.crawlspider.reqproc import FilterUrl
from scrapy.contrib_exp.crawlspider.reqproc import FilterDupes

import copy

class RequestProcessorsTest(unittest.TestCase):

    def test_canonicalize_requests(self):
        urls = [
            'http://example.com/do?&b=1&a=2&c=3',
            'http://example.com/do?123,&q=a space',
            ]
        urls_after = [
            'http://example.com/do?a=2&b=1&c=3',
            'http://example.com/do?123%2C=&q=a+space',
            ]

        proc = Canonicalize()
        results = [req.url for req in proc(Request(url) for url in urls)]
        self.failUnlessEquals(results, urls_after)

    def test_unique_requests(self):
        urls = [
            'http://example.com/sample1.html',
            'http://example.com/sample2.html',
            'http://example.com/sample3.html',
            'http://example.com/sample1.html',
            'http://example.com/sample2.html',
            ]
        urls_unique = [
            'http://example.com/sample1.html',
            'http://example.com/sample2.html',
            'http://example.com/sample3.html',
            ]

        proc = FilterDupes()
        results = [req.url for req in proc(Request(url) for url in urls)]
        self.failUnlessEquals(results, urls_unique)

        # Check custom attributes
        requests = [
            Request('http://example.com', method='GET'),
            Request('http://example.com', method='POST'),
            ]
        proc = FilterDupes('url', 'method')
        self.failUnlessEqual(len(list(proc(requests))), 2)

        proc = FilterDupes('url')
        self.failUnlessEqual(len(list(proc(requests))), 1)

    def test_filter_domain(self):
        urls = [
            'http://blah1.com/index',
            'http://blah2.com/index',
            'http://blah1.com/section',
            'http://blah2.com/section',
            ]

        proc = FilterDomain(allow=('blah1.com'), deny=('blah2.com'))
        filtered = [req.url for req in proc(Request(url) for url in urls)]
        self.failUnlessEquals(filtered, [
                    'http://blah1.com/index',
                    'http://blah1.com/section',
                ])

        proc = FilterDomain(deny=('blah1.com', 'blah2.com'))
        filtered = [req.url for req in proc(Request(url) for url in urls)]
        self.failUnlessEquals(filtered, [])

        proc = FilterDomain(allow=('blah1.com', 'blah2.com'))
        filtered = [req.url for req in proc(Request(url) for url in urls)]
        self.failUnlessEquals(filtered, urls)

    def test_filter_url(self):
        urls = [
            'http://blah1.com/index',
            'http://blah2.com/index',
            'http://blah1.com/section',
            'http://blah2.com/section',
            ]

        proc = FilterUrl(allow=(r'blah1'), deny=(r'blah2'))
        filtered = [req.url for req in proc(Request(url) for url in urls)]
        self.failUnlessEquals(filtered, [
                    'http://blah1.com/index',
                    'http://blah1.com/section',
                ])

        proc = FilterUrl(deny=('blah1', 'blah2'))
        filtered = [req.url for req in proc(Request(url) for url in urls)]
        self.failUnlessEquals(filtered, [])

        proc = FilterUrl(allow=('index$', 'section$'))
        filtered = [req.url for req in proc(Request(url) for url in urls)]
        self.failUnlessEquals(filtered, urls)



    def test_all_processors(self):
        urls = [
            'http://example.com/sample1.html',
            'http://example.com/sample2.html',
            'http://example.com/sample3.html',
            'http://example.com/sample1.html',
            'http://example.com/sample2.html',
            'http://example.com/do?&b=1&a=2&c=3',
            'http://example.com/do?123,&q=a space',
            ]
        urls_processed = [
            'http://example.com/sample1.html',
            'http://example.com/sample2.html',
            'http://example.com/sample3.html',
            'http://example.com/do?a=2&b=1&c=3',
            'http://example.com/do?123%2C=&q=a+space',
            ]

        processors = [
            Canonicalize(),
            FilterDupes(),
            ]

        def _process(requests):
            """Apply all processors"""
            # copy list
            processed = [copy.copy(req) for req in requests]
            for proc in processors:
                processed = proc(processed)
            return processed

        # empty requests
        results1 = [r.url for r in _process([])]
        self.failUnlessEquals(results1, [])

        # try urls
        requests = (Request(url) for url in urls)
        results2 = [r.url for r in _process(requests)]
        self.failUnlessEquals(results2, urls_processed)

