import unittest

from scrapy.queue import ExecutionQueue
from scrapy.spider import BaseSpider
from scrapy.http import Request

class TestSpider(BaseSpider):

    name = "default"

    def start_requests(self):
        return [Request("http://www.example.com/1"), \
            Request("http://www.example.com/2")]

    def make_requests_from_url(self, url):
        return [Request(url + "/make1"), Request(url + "/make2")]


class TestSpiderManager(object):

    def find_by_request(self, request):
        return ['create_for_request']

    def create(self, spider_name, **spider_kwargs):
        return TestSpider(spider_name, **spider_kwargs)


class ExecutionQueueTest(unittest.TestCase):

    keep_alive = False

    def setUp(self):
        self.queue = ExecutionQueue(TestSpiderManager(), None, keep_alive=self.keep_alive)
        self.spider = TestSpider()
        self.request = Request('about:none')

    def tearDown(self):
        del self.queue, self.spider, self.request

    def test_is_finished(self):
        self.assert_(self.queue.is_finished())
        self.queue.append_request(self.request, self.spider)
        self.assert_(not self.queue.is_finished())

    def test_append_spider(self):
        spider = TestSpider()
        self.queue.append_spider(spider)
        self.assert_(self.queue.spider_requests[0][0] is spider)
        self._assert_request_urls(self.queue.spider_requests[0][1],
            ["http://www.example.com/1", "http://www.example.com/2"])

    def test_append_request1(self):
        spider = TestSpider()
        request = Request('about:blank')
        self.queue.append_request(request, spider=spider)
        self.assert_(self.queue.spider_requests[0][0] is spider)
        self.assert_(self.queue.spider_requests[0][1][0] is request)

    def test_append_request2(self):
        request = Request('about:blank')
        self.queue.append_request(request, arg='123')
        spider = self.queue.spider_requests[0][0]
        self.assert_(spider.name == 'create_for_request')
        self.assert_(spider.arg == '123')

    def test_append_url(self):
        spider = TestSpider()
        url = 'http://www.example.com/asd'
        self.queue.append_url(url, spider=spider)
        self.assert_(self.queue.spider_requests[0][0] is spider)
        self._assert_request_urls(self.queue.spider_requests[0][1], \
            ['http://www.example.com/asd/make1', 'http://www.example.com/asd/make2'])

    def test_append_url_kwarg(self):
        spider = TestSpider()
        url = 'http://www.example.com/asd'
        self.queue.append_url(url=url, spider=spider)
        self.assert_(self.queue.spider_requests[0][0] is spider)
        self._assert_request_urls(self.queue.spider_requests[0][1], \
            ['http://www.example.com/asd/make1', 'http://www.example.com/asd/make2'])

    def test_append_url2(self):
        url = 'http://www.example.com/asd'
        self.queue.append_url(url, arg='123')
        self._assert_request_urls(self.queue.spider_requests[0][1], \
            ['http://www.example.com/asd/make1', 'http://www.example.com/asd/make2'])
        spider = self.queue.spider_requests[0][0]
        self.assert_(spider.name == 'create_for_request')
        self.assert_(spider.arg == '123')

    def test_append_spider_name(self):
        self.queue.append_spider_name('test123', arg='123')
        spider = self.queue.spider_requests[0][0]
        self.assert_(spider.name == 'test123')
        self.assert_(spider.arg == '123')

    def test_append_spider_name_kwarg(self):
        self.queue.append_spider_name(name='test123', arg='123')
        spider = self.queue.spider_requests[0][0]
        self.assert_(spider.name == 'test123')
        self.assert_(spider.arg == '123')

    def test_append_next(self):
        # the reason for this test: http://dev.scrapy.org/ticket/250
        class MockQueue(object):
            def pop(self):
                return {u'name': u'test123', u'test': u'hello'}
        self.queue._queue = MockQueue()
        self.queue._append_next()
        spider = self.queue.spider_requests[0][0]
        self.assert_(spider.name == 'test123')
        self.assert_(spider.test == 'hello')

    def _assert_request_urls(self, requests, urls):
        assert all(isinstance(x, Request) for x in requests)
        self.assertEqual([x.url for x in requests], urls)

class KeepAliveExecutionQueueTest(ExecutionQueueTest):

    keep_alive = True

    def test_is_finished(self):
        self.assert_(not self.queue.is_finished())
        self.queue.append_request(self.request, self.spider)
        self.assert_(not self.queue.is_finished())


if __name__ == "__main__":
    unittest.main()

