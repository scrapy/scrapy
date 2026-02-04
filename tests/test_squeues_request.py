"""
Queues that handle requests
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

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

if TYPE_CHECKING:
    from scrapy.crawler import Crawler


HAVE_PEEK = hasattr(queuelib.queue.FifoMemoryQueue, "peek")


@pytest.fixture
def crawler() -> Crawler:
    return get_crawler(Spider)


class TestRequestQueueBase(ABC):
    @property
    @abstractmethod
    def is_fifo(self) -> bool:
        raise NotImplementedError

    @pytest.mark.parametrize("test_peek", [True, False])
    def test_one_element(self, q: queuelib.queue.BaseQueue, test_peek: bool):
        if test_peek and not HAVE_PEEK:
            pytest.skip("The queuelib queues do not define peek")
        if not test_peek and HAVE_PEEK:
            pytest.skip("The queuelib queues define peek")
        assert len(q) == 0
        if test_peek:
            assert q.peek() is None
        assert q.pop() is None
        req = Request("http://www.example.com")
        q.push(req)
        assert len(q) == 1
        if test_peek:
            result = q.peek()
            assert result is not None
            assert result.url == req.url
        else:
            with pytest.raises(
                NotImplementedError,
                match="The underlying queue class does not implement 'peek'",
            ):
                q.peek()
        result = q.pop()
        assert result is not None
        assert result.url == req.url
        assert len(q) == 0
        if test_peek:
            assert q.peek() is None
        assert q.pop() is None
        q.close()

    @pytest.mark.parametrize("test_peek", [True, False])
    def test_order(self, q: queuelib.queue.BaseQueue, test_peek: bool):
        if test_peek and not HAVE_PEEK:
            pytest.skip("The queuelib queues do not define peek")
        if not test_peek and HAVE_PEEK:
            pytest.skip("The queuelib queues define peek")
        assert len(q) == 0
        if test_peek:
            assert q.peek() is None
        assert q.pop() is None
        req1 = Request("http://www.example.com/1")
        req2 = Request("http://www.example.com/2")
        req3 = Request("http://www.example.com/3")
        q.push(req1)
        q.push(req2)
        q.push(req3)
        if not test_peek:
            with pytest.raises(
                NotImplementedError,
                match="The underlying queue class does not implement 'peek'",
            ):
                q.peek()
        reqs = [req1, req2, req3] if self.is_fifo else [req3, req2, req1]
        for i, req in enumerate(reqs):
            assert len(q) == 3 - i
            if test_peek:
                result = q.peek()
                assert result is not None
                assert result.url == req.url
            result = q.pop()
            assert result is not None
            assert result.url == req.url
        assert len(q) == 0
        if test_peek:
            assert q.peek() is None
        assert q.pop() is None
        q.close()


class TestPickleFifoDiskQueueRequest(TestRequestQueueBase):
    is_fifo = True

    @pytest.fixture
    def q(self, crawler, tmp_path):
        return PickleFifoDiskQueue.from_crawler(
            crawler=crawler, key=str(tmp_path / "pickle" / "fifo")
        )


class TestPickleLifoDiskQueueRequest(TestRequestQueueBase):
    is_fifo = False

    @pytest.fixture
    def q(self, crawler, tmp_path):
        return PickleLifoDiskQueue.from_crawler(
            crawler=crawler, key=str(tmp_path / "pickle" / "lifo")
        )


class TestMarshalFifoDiskQueueRequest(TestRequestQueueBase):
    is_fifo = True

    @pytest.fixture
    def q(self, crawler, tmp_path):
        return MarshalFifoDiskQueue.from_crawler(
            crawler=crawler, key=str(tmp_path / "marshal" / "fifo")
        )


class TestMarshalLifoDiskQueueRequest(TestRequestQueueBase):
    is_fifo = False

    @pytest.fixture
    def q(self, crawler, tmp_path):
        return MarshalLifoDiskQueue.from_crawler(
            crawler=crawler, key=str(tmp_path / "marshal" / "lifo")
        )


class TestFifoMemoryQueueRequest(TestRequestQueueBase):
    is_fifo = True

    @pytest.fixture
    def q(self, crawler):
        return FifoMemoryQueue.from_crawler(crawler=crawler)


class TestLifoMemoryQueueRequest(TestRequestQueueBase):
    is_fifo = False

    @pytest.fixture
    def q(self, crawler):
        return LifoMemoryQueue.from_crawler(crawler=crawler)
