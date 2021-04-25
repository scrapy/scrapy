import tempfile
import unittest

import queuelib

from scrapy.http.request import Request
from scrapy.pqueues import ScrapyPriorityQueue, DownloaderAwarePriorityQueue
from scrapy.spiders import Spider
from scrapy.squeues import FifoMemoryQueue
from scrapy.utils.test import get_crawler

from tests.test_scheduler import MockDownloader, MockEngine


class PriorityQueueTest(unittest.TestCase):
    def setUp(self):
        self.crawler = get_crawler(Spider)
        self.spider = self.crawler._create_spider("foo")

    def test_queue_push_pop_one(self):
        temp_dir = tempfile.mkdtemp()
        queue = ScrapyPriorityQueue.from_crawler(self.crawler, FifoMemoryQueue, temp_dir)
        self.assertIsNone(queue.pop())
        self.assertEqual(len(queue), 0)
        req1 = Request("https://example.org/1", priority=1)
        queue.push(req1)
        self.assertEqual(len(queue), 1)
        dequeued = queue.pop()
        self.assertEqual(len(queue), 0)
        self.assertEqual(dequeued.url, req1.url)
        self.assertEqual(dequeued.priority, req1.priority)
        self.assertEqual(queue.close(), [])

    def test_no_peek_raises(self):
        if hasattr(queuelib.queue.FifoMemoryQueue, "peek"):
            raise unittest.SkipTest("queuelib.queue.FifoMemoryQueue.peek is defined")
        temp_dir = tempfile.mkdtemp()
        queue = ScrapyPriorityQueue.from_crawler(self.crawler, FifoMemoryQueue, temp_dir)
        queue.push(Request("https://example.org"))
        with self.assertRaises(NotImplementedError, msg="The underlying queue class does not implement 'peek'"):
            queue.peek()
        queue.close()

    def test_peek(self):
        if not hasattr(queuelib.queue.FifoMemoryQueue, "peek"):
            raise unittest.SkipTest("queuelib.queue.FifoMemoryQueue.peek is undefined")
        temp_dir = tempfile.mkdtemp()
        queue = ScrapyPriorityQueue.from_crawler(self.crawler, FifoMemoryQueue, temp_dir)
        self.assertEqual(len(queue), 0)
        self.assertIsNone(queue.peek())
        req1 = Request("https://example.org/1")
        req2 = Request("https://example.org/2")
        req3 = Request("https://example.org/3")
        queue.push(req1)
        queue.push(req2)
        queue.push(req3)
        self.assertEqual(len(queue), 3)
        self.assertEqual(queue.peek().url, req1.url)
        self.assertEqual(queue.pop().url, req1.url)
        self.assertEqual(len(queue), 2)
        self.assertEqual(queue.peek().url, req2.url)
        self.assertEqual(queue.pop().url, req2.url)
        self.assertEqual(len(queue), 1)
        self.assertEqual(queue.peek().url, req3.url)
        self.assertEqual(queue.pop().url, req3.url)
        self.assertEqual(queue.close(), [])

    def test_queue_push_pop_priorities(self):
        temp_dir = tempfile.mkdtemp()
        queue = ScrapyPriorityQueue.from_crawler(self.crawler, FifoMemoryQueue, temp_dir, [-1, -2, -3])
        self.assertIsNone(queue.pop())
        self.assertEqual(len(queue), 0)
        req1 = Request("https://example.org/1", priority=1)
        req2 = Request("https://example.org/2", priority=2)
        req3 = Request("https://example.org/3", priority=3)
        queue.push(req1)
        queue.push(req2)
        queue.push(req3)
        self.assertEqual(len(queue), 3)
        dequeued = queue.pop()
        self.assertEqual(len(queue), 2)
        self.assertEqual(dequeued.url, req3.url)
        self.assertEqual(dequeued.priority, req3.priority)
        self.assertEqual(queue.close(), [-1, -2])


class DownloaderAwarePriorityQueueTest(unittest.TestCase):
    def setUp(self):
        crawler = get_crawler(Spider)
        crawler.engine = MockEngine(downloader=MockDownloader())
        self.queue = DownloaderAwarePriorityQueue.from_crawler(
            crawler=crawler,
            downstream_queue_cls=FifoMemoryQueue,
            key="foo/bar",
        )

    def tearDown(self):
        self.queue.close()

    def test_push_pop(self):
        self.assertEqual(len(self.queue), 0)
        self.assertIsNone(self.queue.pop())
        req1 = Request("http://www.example.com/1")
        req2 = Request("http://www.example.com/2")
        req3 = Request("http://www.example.com/3")
        self.queue.push(req1)
        self.queue.push(req2)
        self.queue.push(req3)
        self.assertEqual(len(self.queue), 3)
        self.assertEqual(self.queue.pop().url, req1.url)
        self.assertEqual(len(self.queue), 2)
        self.assertEqual(self.queue.pop().url, req2.url)
        self.assertEqual(len(self.queue), 1)
        self.assertEqual(self.queue.pop().url, req3.url)
        self.assertEqual(len(self.queue), 0)
        self.assertIsNone(self.queue.pop())

    def test_no_peek_raises(self):
        if hasattr(queuelib.queue.FifoMemoryQueue, "peek"):
            raise unittest.SkipTest("queuelib.queue.FifoMemoryQueue.peek is defined")
        self.queue.push(Request("https://example.org"))
        with self.assertRaises(NotImplementedError, msg="The underlying queue class does not implement 'peek'"):
            self.queue.peek()

    def test_peek(self):
        if not hasattr(queuelib.queue.FifoMemoryQueue, "peek"):
            raise unittest.SkipTest("queuelib.queue.FifoMemoryQueue.peek is undefined")
        self.assertEqual(len(self.queue), 0)
        req1 = Request("https://example.org/1")
        req2 = Request("https://example.org/2")
        req3 = Request("https://example.org/3")
        self.queue.push(req1)
        self.queue.push(req2)
        self.queue.push(req3)
        self.assertEqual(len(self.queue), 3)
        self.assertEqual(self.queue.peek().url, req1.url)
        self.assertEqual(self.queue.pop().url, req1.url)
        self.assertEqual(len(self.queue), 2)
        self.assertEqual(self.queue.peek().url, req2.url)
        self.assertEqual(self.queue.pop().url, req2.url)
        self.assertEqual(len(self.queue), 1)
        self.assertEqual(self.queue.peek().url, req3.url)
        self.assertEqual(self.queue.pop().url, req3.url)
        self.assertIsNone(self.queue.peek())
