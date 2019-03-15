from unittest import TestCase

from scrapy.item import Item, Field
from scrapy.spiders import Spider
from scrapy.utils.test import get_crawler
from scrapy.http import Response, Request
from scrapy.spidermiddlewares.retry import RetryMiddleware


class TestItem(Item):
    name = Field()


class TestRetryMiddleware(TestCase):

    spider_settings = {
        'name': 'foo',
    }

    def setUp(self):
        crawler = self._get_crawler()
        self.spider = self._get_spider(crawler)
        self.mw = self._get_middleware(crawler)

    def _get_crawler(self, spider_settings=None):
        return get_crawler(Spider, spider_settings)

    def _get_spider(self, crawler):
        return crawler._create_spider(**self.spider_settings)

    def _get_middleware(self, crawler):
        return RetryMiddleware.from_crawler(crawler)

    def _assert_retry(self, original_request, output):
        """assert that output of the middleware is a retrying request of a original request"""
        self.assertIsNotNone(output)
        self.assertEqual(original_request.url, output.url)
        self.assertTrue(output.dont_filter)

    def test_retry_request(self):
        response = Response('http://scrapytest.org')
        request = Request('http://scrapytest.org/1').mark_for_retry('No content')
        reqs = [request]

        out = list(self.mw.process_spider_output(response, reqs, self.spider))[0]
        self._assert_retry(request, out)

    def test_retry_times(self):
        response = Response('http://scrapytest.org')
        request = Request('http://scrapytest.org/1').mark_for_retry('No content')
        reqs = [request]
        for attempt in range(1, 3):
            out = list(self.mw.process_spider_output(response, reqs, self.spider))
            self.assertEqual(out[0].meta['retry_times'], attempt)
            reqs = [r.mark_for_retry('No content') for r in out]

    def test_is_marked_for_retry(self):
        response = Response('http://scrapytest.org')
        request = Request('http://scrapytest.org/1').mark_for_retry('No content')
        self.assertTrue(request.is_marked_for_retry())
        out = list(self.mw.process_spider_output(response, [request], self.spider))[0]
        self._assert_retry(request, out)
        self.assertFalse(out.is_marked_for_retry())

    def test_retry_reason(self):
        reason = 'No content'
        response = Response('http://scrapytest.org')
        request = Request('http://scrapytest.org/1').mark_for_retry(reason)
        self.assertEqual(request.get_retry_reason(), reason)
        out = list(self.mw.process_spider_output(response, [request], self.spider))[0]
        self._assert_retry(request, out)
        self.assertIsNone(out.get_retry_reason())

    def test_unmarked_requests(self):
        """middleware should return unmarked requests as is"""
        response = Response('http://scrapytest.org')
        url = 'https://scrapytest.org/{}'
        reqs = [Request(url.format(i + 1)) for i in range(5)]
        out = list(self.mw.process_spider_output(response, reqs, self.spider))
        self.assertEqual(reqs, out)

    def test_non_requests(self):
        """middleware should return non Request objects as is"""
        response = Response('http://scrapytest.org')
        items = [TestItem({'name': 'name{}'.format(i)}) for i in range(5)]
        out = list(self.mw.process_spider_output(response, items, self.spider))
        self.assertEqual(items, out)

        items = [{'Address': 'add{}'.format(i)} for i in range(5)]
        out = list(self.mw.process_spider_output(response, items, self.spider))
        self.assertEqual(items, out)

    def test_max_retry_times(self):
        """if a request has reached maximum retry times it should be dropped"""
        max_retry_setting = 5
        max_retry_meta = 3

        crawler = self._get_crawler({'RETRY_TIMES': max_retry_setting})
        spider = self._get_spider(crawler)
        mw = self._get_middleware(crawler)

        response = Response('http://scrapytest.org')
        request = Request('http://scrapytest.org/1').mark_for_retry('No content')
        reqs = [request]
        for attempt in range(1, max_retry_setting + 2):
            out = list(mw.process_spider_output(response, reqs, spider))
            if attempt < max_retry_setting + 1:
                self._assert_retry(request, out[0])
            else:
                self.assertEqual(out, [])

            reqs = [r.mark_for_retry('No content') for r in out]


        # setting max retry times in meta
        meta = {
            'max_retry_times': max_retry_meta,
        }
        response2 = Response('http://scrapytest.org')
        request2 = Request('http://scrapytest.org/1', meta=meta).mark_for_retry('No content')
        reqs2 = [request2]

        for attempt in range(1, max_retry_meta + 2):
            out2 = list(mw.process_spider_output(response2, reqs2, spider))
            if attempt < max_retry_meta + 1:
                self._assert_retry(request2, out2[0])
            else:
                self.assertEqual(out2, [])

            reqs2 = [r.mark_for_retry('No content') for r in out2]

    def test_disabled(self):
        """if retrying is disabled requests marked for retrying should be dropped"""
        crawler = self._get_crawler({'RETRY_ENABLED': False})
        spider = self._get_spider(crawler)
        mw = self._get_middleware(crawler)

        response = Response('http://scrapytest.org')
        request = Request('http://scrapytest.org/1').mark_for_retry('No content')
        reqs = [request]
        out = list(mw.process_spider_output(response, reqs, spider))
        self.assertEqual(out, [])
