from unittest import TestCase

from scrapy.spidermiddlewares.stickymeta import StickyMeta
from scrapy.http import Response, Request
from scrapy.spiders import Spider
from scrapy.utils.test import get_crawler


class TestStickyMetaMiddleware(TestCase):

    def setUp(self):
        crawler = get_crawler(Spider, settings_dict={'STICKY_META': ['settings', 'settings2']})
        self.spider = crawler._create_spider(name='foobar')
        self.mw = StickyMeta.from_crawler(crawler)

    def test_process_spider_output(self):
        # plain, no match
        resp = Response(
            'http://scrapytest.org',
            request=Request(
                'http://scrapytest.org/',
                meta={'oh_no': "I'm not sticky! :("}
            ),
        )
        reqs = [Request('http://scrapytest.org')]
        for result in self.mw.process_spider_output(resp, reqs, self.spider):
            self.assertEqual(result.meta, {})

        # unattached response
        wild_resp = Response('http://httpbin.org/headers')
        reqs = [Request('http://scrapytest.org')]
        for result in self.mw.process_spider_output(wild_resp, reqs, self.spider):
            self.assertEqual(result.meta, {})

        # setting STICKY_META
        reqs = [Request('http://scrapytest.org')]
        resp = Response(
            'http://scrapytest.org',
            request=Request(
                'http://scrapytest.org/',
                meta={'settings': "I'm sticky!"}
            ),
        )

        out = list(self.mw.process_spider_output(resp, reqs, self.spider))
        self.assertEqual(out[0].meta, {'settings': "I'm sticky!"})

        # meta["sticky"]
        reqs = [Request('http://scrapytest.org')]
        resp = Response(
            'http://scrapytest.org',
            request=Request(
                'http://scrapytest.org/',
                meta={'meta': "I'm sticky!", 'sticky': ['meta']}
            ),
        )
        out = list(self.mw.process_spider_output(resp, reqs, self.spider))
        self.assertEqual(out[0].meta, {'meta': "I'm sticky!"})

        # spider.sticky_meta
        reqs = [Request('http://scrapytest.org')]
        resp = Response(
            'http://scrapytest.org',
            request=Request(
                'http://scrapytest.org/',
                meta={'spider': "I'm sticky!"}
            ),
        )
        self.spider.sticky_meta = ['spider']
        out = list(self.mw.process_spider_output(resp, reqs, self.spider))
        self.assertEqual(out[0].meta, {'spider': "I'm sticky!"})

