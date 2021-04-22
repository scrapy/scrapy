import tempfile
import unittest

from scrapy.http.request import Request
from scrapy.pqueues import ScrapyPriorityQueue
from scrapy.spiders import Spider
from scrapy.squeues import FifoMemoryQueue
from scrapy.utils.test import get_crawler


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
