"""
Queues that handle requests
"""

from pathlib import Path

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
        self.crawler = get_crawler(Spider)


class RequestQueueTestMixin:
    def queue(self, base_path: Path):
        raise NotImplementedError

    def test_one_element_with_peek(self, tmp_path):
        if not hasattr(queuelib.queue.FifoMemoryQueue, "peek"):
            pytest.skip("The queuelib queues do not define peek")
        q = self.queue(tmp_path)
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

    def test_one_element_without_peek(self, tmp_path):
        if hasattr(queuelib.queue.FifoMemoryQueue, "peek"):
            pytest.skip("The queuelib queues define peek")
        q = self.queue(tmp_path)
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
    def test_fifo_with_peek(self, tmp_path):
        if not hasattr(queuelib.queue.FifoMemoryQueue, "peek"):
            pytest.skip("The queuelib queues do not define peek")
        q = self.queue(tmp_path)
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

    def test_fifo_without_peek(self, tmp_path):
        if hasattr(queuelib.queue.FifoMemoryQueue, "peek"):
            pytest.skip("The queuelib queues define peek")
        q = self.queue(tmp_path)
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
    def test_lifo_with_peek(self, tmp_path):
        if not hasattr(queuelib.queue.FifoMemoryQueue, "peek"):
            pytest.skip("The queuelib queues do not define peek")
        q = self.queue(tmp_path)
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

    def test_lifo_without_peek(self, tmp_path):
        if hasattr(queuelib.queue.FifoMemoryQueue, "peek"):
            pytest.skip("The queuelib queues define peek")
        q = self.queue(tmp_path)
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
    def queue(self, base_path):
        return PickleFifoDiskQueue.from_crawler(
            crawler=self.crawler, key=str(base_path / "pickle" / "fifo")
        )


class TestPickleLifoDiskQueueRequest(LifoQueueMixin, TestBaseQueue):
    def queue(self, base_path):
        return PickleLifoDiskQueue.from_crawler(
            crawler=self.crawler, key=str(base_path / "pickle" / "lifo")
        )


class TestMarshalFifoDiskQueueRequest(FifoQueueMixin, TestBaseQueue):
    def queue(self, base_path):
        return MarshalFifoDiskQueue.from_crawler(
            crawler=self.crawler, key=str(base_path / "marshal" / "fifo")
        )


class TestMarshalLifoDiskQueueRequest(LifoQueueMixin, TestBaseQueue):
    def queue(self, base_path):
        return MarshalLifoDiskQueue.from_crawler(
            crawler=self.crawler, key=str(base_path / "marshal" / "lifo")
        )


class TestFifoMemoryQueueRequest(FifoQueueMixin, TestBaseQueue):
    def queue(self, base_path):
        return FifoMemoryQueue.from_crawler(crawler=self.crawler)


class TestLifoMemoryQueueRequest(LifoQueueMixin, TestBaseQueue):
    def queue(self, base_path):
        return LifoMemoryQueue.from_crawler(crawler=self.crawler)
