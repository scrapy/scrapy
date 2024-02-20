import shutil
import tempfile
import unittest

import queuelib

from scrapy.http import Request
from scrapy.spiders import Spider
from scrapy.squeues import (
    FifoMemoryQueue,
    LifoMemoryQueue,
    MarshalFifoDiskQueue,
    MarshalLifoDiskQueue,
    PickleFifoDiskQueue,
    PickleLifoDiskQueue,
)
from scrapy.utils.test import get_crawler

"""
Queues that handle requests
"""


class BaseQueueTestCase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="scrapy-queue-tests-")
        self.qpath = self.tempfilename()
        self.qdir = tempfile.mkdtemp()
        self.crawler = get_crawler(Spider)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def tempfilename(self):
        with tempfile.NamedTemporaryFile(dir=self.tmpdir) as nf:
            return nf.name

    def mkdtemp(self):
        return tempfile.mkdtemp(dir=self.tmpdir)


class RequestQueueTestMixin:
    def queue(self):
        raise NotImplementedError()

    def test_one_element_with_peek(self):
        if not hasattr(queuelib.queue.FifoMemoryQueue, "peek"):
            raise unittest.SkipTest("The queuelib queues do not define peek")
        q = self.queue()
        self.assertEqual(len(q), 0)
        self.assertIsNone(q.peek())
        self.assertIsNone(q.pop())
        req = Request("http://www.example.com")
        q.push(req)
        self.assertEqual(len(q), 1)
        self.assertEqual(q.peek().url, req.url)
        self.assertEqual(q.pop().url, req.url)
        self.assertEqual(len(q), 0)
        self.assertIsNone(q.peek())
        self.assertIsNone(q.pop())
        q.close()

    def test_one_element_without_peek(self):
        if hasattr(queuelib.queue.FifoMemoryQueue, "peek"):
            raise unittest.SkipTest("The queuelib queues define peek")
        q = self.queue()
        self.assertEqual(len(q), 0)
        self.assertIsNone(q.pop())
        req = Request("http://www.example.com")
        q.push(req)
        self.assertEqual(len(q), 1)
        with self.assertRaises(
            NotImplementedError,
            msg="The underlying queue class does not implement 'peek'",
        ):
            q.peek()
        self.assertEqual(q.pop().url, req.url)
        self.assertEqual(len(q), 0)
        self.assertIsNone(q.pop())
        q.close()


class FifoQueueMixin(RequestQueueTestMixin):
    def test_fifo_with_peek(self):
        if not hasattr(queuelib.queue.FifoMemoryQueue, "peek"):
            raise unittest.SkipTest("The queuelib queues do not define peek")
        q = self.queue()
        self.assertEqual(len(q), 0)
        self.assertIsNone(q.peek())
        self.assertIsNone(q.pop())
        req1 = Request("http://www.example.com/1")
        req2 = Request("http://www.example.com/2")
        req3 = Request("http://www.example.com/3")
        q.push(req1)
        q.push(req2)
        q.push(req3)
        self.assertEqual(len(q), 3)
        self.assertEqual(q.peek().url, req1.url)
        self.assertEqual(q.pop().url, req1.url)
        self.assertEqual(len(q), 2)
        self.assertEqual(q.peek().url, req2.url)
        self.assertEqual(q.pop().url, req2.url)
        self.assertEqual(len(q), 1)
        self.assertEqual(q.peek().url, req3.url)
        self.assertEqual(q.pop().url, req3.url)
        self.assertEqual(len(q), 0)
        self.assertIsNone(q.peek())
        self.assertIsNone(q.pop())
        q.close()

    def test_fifo_without_peek(self):
        if hasattr(queuelib.queue.FifoMemoryQueue, "peek"):
            raise unittest.SkipTest("The queuelib queues do not define peek")
        q = self.queue()
        self.assertEqual(len(q), 0)
        self.assertIsNone(q.pop())
        req1 = Request("http://www.example.com/1")
        req2 = Request("http://www.example.com/2")
        req3 = Request("http://www.example.com/3")
        q.push(req1)
        q.push(req2)
        q.push(req3)
        with self.assertRaises(
            NotImplementedError,
            msg="The underlying queue class does not implement 'peek'",
        ):
            q.peek()
        self.assertEqual(len(q), 3)
        self.assertEqual(q.pop().url, req1.url)
        self.assertEqual(len(q), 2)
        self.assertEqual(q.pop().url, req2.url)
        self.assertEqual(len(q), 1)
        self.assertEqual(q.pop().url, req3.url)
        self.assertEqual(len(q), 0)
        self.assertIsNone(q.pop())
        q.close()


class LifoQueueMixin(RequestQueueTestMixin):
    def test_lifo_with_peek(self):
        if not hasattr(queuelib.queue.FifoMemoryQueue, "peek"):
            raise unittest.SkipTest("The queuelib queues do not define peek")
        q = self.queue()
        self.assertEqual(len(q), 0)
        self.assertIsNone(q.peek())
        self.assertIsNone(q.pop())
        req1 = Request("http://www.example.com/1")
        req2 = Request("http://www.example.com/2")
        req3 = Request("http://www.example.com/3")
        q.push(req1)
        q.push(req2)
        q.push(req3)
        self.assertEqual(len(q), 3)
        self.assertEqual(q.peek().url, req3.url)
        self.assertEqual(q.pop().url, req3.url)
        self.assertEqual(len(q), 2)
        self.assertEqual(q.peek().url, req2.url)
        self.assertEqual(q.pop().url, req2.url)
        self.assertEqual(len(q), 1)
        self.assertEqual(q.peek().url, req1.url)
        self.assertEqual(q.pop().url, req1.url)
        self.assertEqual(len(q), 0)
        self.assertIsNone(q.peek())
        self.assertIsNone(q.pop())
        q.close()

    def test_lifo_without_peek(self):
        if hasattr(queuelib.queue.FifoMemoryQueue, "peek"):
            raise unittest.SkipTest("The queuelib queues do not define peek")
        q = self.queue()
        self.assertEqual(len(q), 0)
        self.assertIsNone(q.pop())
        req1 = Request("http://www.example.com/1")
        req2 = Request("http://www.example.com/2")
        req3 = Request("http://www.example.com/3")
        q.push(req1)
        q.push(req2)
        q.push(req3)
        with self.assertRaises(
            NotImplementedError,
            msg="The underlying queue class does not implement 'peek'",
        ):
            q.peek()
        self.assertEqual(len(q), 3)
        self.assertEqual(q.pop().url, req3.url)
        self.assertEqual(len(q), 2)
        self.assertEqual(q.pop().url, req2.url)
        self.assertEqual(len(q), 1)
        self.assertEqual(q.pop().url, req1.url)
        self.assertEqual(len(q), 0)
        self.assertIsNone(q.pop())
        q.close()


class PickleFifoDiskQueueRequestTest(FifoQueueMixin, BaseQueueTestCase):
    def queue(self):
        return PickleFifoDiskQueue.from_crawler(crawler=self.crawler, key="pickle/fifo")


class PickleLifoDiskQueueRequestTest(LifoQueueMixin, BaseQueueTestCase):
    def queue(self):
        return PickleLifoDiskQueue.from_crawler(crawler=self.crawler, key="pickle/lifo")


class MarshalFifoDiskQueueRequestTest(FifoQueueMixin, BaseQueueTestCase):
    def queue(self):
        return MarshalFifoDiskQueue.from_crawler(
            crawler=self.crawler, key="marshal/fifo"
        )


class MarshalLifoDiskQueueRequestTest(LifoQueueMixin, BaseQueueTestCase):
    def queue(self):
        return MarshalLifoDiskQueue.from_crawler(
            crawler=self.crawler, key="marshal/lifo"
        )


class FifoMemoryQueueRequestTest(FifoQueueMixin, BaseQueueTestCase):
    def queue(self):
        return FifoMemoryQueue.from_crawler(crawler=self.crawler)


class LifoMemoryQueueRequestTest(LifoQueueMixin, BaseQueueTestCase):
    def queue(self):
        return LifoMemoryQueue.from_crawler(crawler=self.crawler)
