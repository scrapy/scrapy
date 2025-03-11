"""
Queues that handle requests
"""

import shutil
import tempfile
import unittest

import pytest
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


class TestBaseQueue:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp(prefix="scrapy-queue-tests-")
        self.qpath = self.tempfilename()
        self.qdir = tempfile.mkdtemp()
        self.crawler = get_crawler(Spider)

    def teardown_method(self):
        shutil.rmtree(self.tmpdir)

    def tempfilename(self):
        with tempfile.NamedTemporaryFile(dir=self.tmpdir) as nf:
            return nf.name

    def mkdtemp(self):
        return tempfile.mkdtemp(dir=self.tmpdir)


class RequestQueueTestMixin:
    def queue(self):
        raise NotImplementedError

    def test_one_element_with_peek(self):
        if not hasattr(queuelib.queue.FifoMemoryQueue, "peek"):
            raise unittest.SkipTest("The queuelib queues do not define peek")
        q = self.queue()
        assert len(q) == 0
        assert q.peek() is None
        assert q.pop() is None
        req = Request("http://www.example.com")
        q.push(req)
        assert len(q) == 1
        assert q.peek().url == req.url
        assert q.pop().url == req.url
        assert len(q) == 0
        assert q.peek() is None
        assert q.pop() is None
        q.close()

    def test_one_element_without_peek(self):
        if hasattr(queuelib.queue.FifoMemoryQueue, "peek"):
            raise unittest.SkipTest("The queuelib queues define peek")
        q = self.queue()
        assert len(q) == 0
        assert q.pop() is None
        req = Request("http://www.example.com")
        q.push(req)
        assert len(q) == 1
        with pytest.raises(
            NotImplementedError,
            match="The underlying queue class does not implement 'peek'",
        ):
            q.peek()
        assert q.pop().url == req.url
        assert len(q) == 0
        assert q.pop() is None
        q.close()


class FifoQueueMixin(RequestQueueTestMixin):
    def test_fifo_with_peek(self):
        if not hasattr(queuelib.queue.FifoMemoryQueue, "peek"):
            raise unittest.SkipTest("The queuelib queues do not define peek")
        q = self.queue()
        assert len(q) == 0
        assert q.peek() is None
        assert q.pop() is None
        req1 = Request("http://www.example.com/1")
        req2 = Request("http://www.example.com/2")
        req3 = Request("http://www.example.com/3")
        q.push(req1)
        q.push(req2)
        q.push(req3)
        assert len(q) == 3
        assert q.peek().url == req1.url
        assert q.pop().url == req1.url
        assert len(q) == 2
        assert q.peek().url == req2.url
        assert q.pop().url == req2.url
        assert len(q) == 1
        assert q.peek().url == req3.url
        assert q.pop().url == req3.url
        assert len(q) == 0
        assert q.peek() is None
        assert q.pop() is None
        q.close()

    def test_fifo_without_peek(self):
        if hasattr(queuelib.queue.FifoMemoryQueue, "peek"):
            raise unittest.SkipTest("The queuelib queues do not define peek")
        q = self.queue()
        assert len(q) == 0
        assert q.pop() is None
        req1 = Request("http://www.example.com/1")
        req2 = Request("http://www.example.com/2")
        req3 = Request("http://www.example.com/3")
        q.push(req1)
        q.push(req2)
        q.push(req3)
        with pytest.raises(
            NotImplementedError,
            match="The underlying queue class does not implement 'peek'",
        ):
            q.peek()
        assert len(q) == 3
        assert q.pop().url == req1.url
        assert len(q) == 2
        assert q.pop().url == req2.url
        assert len(q) == 1
        assert q.pop().url == req3.url
        assert len(q) == 0
        assert q.pop() is None
        q.close()


class LifoQueueMixin(RequestQueueTestMixin):
    def test_lifo_with_peek(self):
        if not hasattr(queuelib.queue.FifoMemoryQueue, "peek"):
            raise unittest.SkipTest("The queuelib queues do not define peek")
        q = self.queue()
        assert len(q) == 0
        assert q.peek() is None
        assert q.pop() is None
        req1 = Request("http://www.example.com/1")
        req2 = Request("http://www.example.com/2")
        req3 = Request("http://www.example.com/3")
        q.push(req1)
        q.push(req2)
        q.push(req3)
        assert len(q) == 3
        assert q.peek().url == req3.url
        assert q.pop().url == req3.url
        assert len(q) == 2
        assert q.peek().url == req2.url
        assert q.pop().url == req2.url
        assert len(q) == 1
        assert q.peek().url == req1.url
        assert q.pop().url == req1.url
        assert len(q) == 0
        assert q.peek() is None
        assert q.pop() is None
        q.close()

    def test_lifo_without_peek(self):
        if hasattr(queuelib.queue.FifoMemoryQueue, "peek"):
            raise unittest.SkipTest("The queuelib queues do not define peek")
        q = self.queue()
        assert len(q) == 0
        assert q.pop() is None
        req1 = Request("http://www.example.com/1")
        req2 = Request("http://www.example.com/2")
        req3 = Request("http://www.example.com/3")
        q.push(req1)
        q.push(req2)
        q.push(req3)
        with pytest.raises(
            NotImplementedError,
            match="The underlying queue class does not implement 'peek'",
        ):
            q.peek()
        assert len(q) == 3
        assert q.pop().url == req3.url
        assert len(q) == 2
        assert q.pop().url == req2.url
        assert len(q) == 1
        assert q.pop().url == req1.url
        assert len(q) == 0
        assert q.pop() is None
        q.close()


class TestPickleFifoDiskQueueRequest(FifoQueueMixin, TestBaseQueue):
    def queue(self):
        return PickleFifoDiskQueue.from_crawler(crawler=self.crawler, key="pickle/fifo")


class TestPickleLifoDiskQueueRequest(LifoQueueMixin, TestBaseQueue):
    def queue(self):
        return PickleLifoDiskQueue.from_crawler(crawler=self.crawler, key="pickle/lifo")


class TestMarshalFifoDiskQueueRequest(FifoQueueMixin, TestBaseQueue):
    def queue(self):
        return MarshalFifoDiskQueue.from_crawler(
            crawler=self.crawler, key="marshal/fifo"
        )


class TestMarshalLifoDiskQueueRequest(LifoQueueMixin, TestBaseQueue):
    def queue(self):
        return MarshalLifoDiskQueue.from_crawler(
            crawler=self.crawler, key="marshal/lifo"
        )


class TestFifoMemoryQueueRequest(FifoQueueMixin, TestBaseQueue):
    def queue(self):
        return FifoMemoryQueue.from_crawler(crawler=self.crawler)


class TestLifoMemoryQueueRequest(LifoQueueMixin, TestBaseQueue):
    def queue(self):
        return LifoMemoryQueue.from_crawler(crawler=self.crawler)
