"""
Queues that handle requests
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

import pytest

from scrapy.http import Request
from scrapy.spiders import Spider
from scrapy.squeues import (
    FifoMemoryQueue,
    LifoMemoryQueue,
    MarshalFifoDiskQueue,
    MarshalFifoSQLiteQueue,
    MarshalLifoDiskQueue,
    MarshalLifoSQLiteQueue,
    PickleFifoDiskQueue,
    PickleFifoSQLiteQueue,
    PickleLifoDiskQueue,
    PickleLifoSQLiteQueue,
)
from scrapy.utils.misc import build_from_crawler
from scrapy.utils.test import get_crawler

if TYPE_CHECKING:
    from pathlib import Path

    import queuelib

    from scrapy.crawler import Crawler


@pytest.fixture
def crawler() -> Crawler:
    return get_crawler(Spider)


class TestRequestQueueBase(ABC):
    @property
    @abstractmethod
    def is_fifo(self) -> bool:
        raise NotImplementedError

    def test_one_element(self, q: queuelib.queue.BaseQueue):
        assert len(q) == 0
        assert q.peek() is None
        assert q.pop() is None
        req = Request("http://www.example.com")
        q.push(req)
        assert len(q) == 1
        result = q.peek()
        assert result is not None
        assert result.url == req.url
        result = q.pop()
        assert result is not None
        assert result.url == req.url
        assert len(q) == 0
        assert q.peek() is None
        assert q.pop() is None

    def test_order(self, q: queuelib.queue.BaseQueue):
        assert len(q) == 0
        assert q.peek() is None
        assert q.pop() is None
        req1 = Request("http://www.example.com/1")
        req2 = Request("http://www.example.com/2")
        req3 = Request("http://www.example.com/3")
        q.push(req1)
        q.push(req2)
        q.push(req3)
        reqs = [req1, req2, req3] if self.is_fifo else [req3, req2, req1]
        for i, req in enumerate(reqs):
            assert len(q) == 3 - i
            result = q.peek()
            assert result is not None
            assert result.url == req.url
            result = q.pop()
            assert result is not None
            assert result.url == req.url
        assert len(q) == 0
        assert q.peek() is None
        assert q.pop() is None


class TestPickleFifoDiskQueueRequest(TestRequestQueueBase):
    is_fifo = True

    @pytest.fixture
    def q(self, crawler, tmp_path):
        queue = build_from_crawler(
            PickleFifoDiskQueue, crawler, key=str(tmp_path / "pickle" / "fifo")
        )
        try:
            yield queue
        finally:
            queue.close()


class TestPickleLifoDiskQueueRequest(TestRequestQueueBase):
    is_fifo = False

    @pytest.fixture
    def q(self, crawler, tmp_path):
        queue = build_from_crawler(
            PickleLifoDiskQueue, crawler, key=str(tmp_path / "pickle" / "lifo")
        )
        try:
            yield queue
        finally:
            queue.close()


class TestMarshalFifoDiskQueueRequest(TestRequestQueueBase):
    is_fifo = True

    @pytest.fixture
    def q(self, crawler, tmp_path):
        queue = build_from_crawler(
            MarshalFifoDiskQueue, crawler, key=str(tmp_path / "marshal" / "fifo")
        )
        try:
            yield queue
        finally:
            queue.close()


class TestMarshalLifoDiskQueueRequest(TestRequestQueueBase):
    is_fifo = False

    @pytest.fixture
    def q(self, crawler, tmp_path):
        queue = build_from_crawler(
            MarshalLifoDiskQueue, crawler, key=str(tmp_path / "marshal" / "lifo")
        )
        try:
            yield queue
        finally:
            queue.close()


class TestPickleFifoSQLiteQueueRequest(TestRequestQueueBase):
    is_fifo = True

    @pytest.fixture
    def q(self, crawler, tmp_path):
        queue = build_from_crawler(
            PickleFifoSQLiteQueue, crawler, key=str(tmp_path / "pickle" / "fifo")
        )
        try:
            yield queue
        finally:
            queue.close()


class TestPickleLifoSQLiteQueueRequest(TestRequestQueueBase):
    is_fifo = False

    @pytest.fixture
    def q(self, crawler, tmp_path):
        queue = build_from_crawler(
            PickleLifoSQLiteQueue, crawler, key=str(tmp_path / "pickle" / "lifo")
        )
        try:
            yield queue
        finally:
            queue.close()


class TestMarshalFifoSQLiteQueueRequest(TestRequestQueueBase):
    is_fifo = True

    @pytest.fixture
    def q(self, crawler, tmp_path):
        queue = build_from_crawler(
            MarshalFifoSQLiteQueue, crawler, key=str(tmp_path / "marshal" / "fifo")
        )
        try:
            yield queue
        finally:
            queue.close()


class TestMarshalLifoSQLiteQueueRequest(TestRequestQueueBase):
    is_fifo = False

    @pytest.fixture
    def q(self, crawler, tmp_path):
        queue = build_from_crawler(
            MarshalLifoSQLiteQueue, crawler, key=str(tmp_path / "marshal" / "lifo")
        )
        try:
            yield queue
        finally:
            queue.close()


@pytest.mark.parametrize(
    "queue_cls",
    [
        PickleFifoSQLiteQueue,
        PickleLifoSQLiteQueue,
        MarshalFifoSQLiteQueue,
        MarshalLifoSQLiteQueue,
    ],
)
def test_sqlite_queue_survives_unclean_shutdown(
    crawler: Crawler, tmp_path: Path, queue_cls: Any
) -> None:
    key = str(tmp_path / "queue")
    queue = queue_cls.from_crawler(crawler=crawler, key=key)
    queue.push(Request("https://toscrape.com"))
    # No close(), as if the process had been killed. The connection is closed
    # directly instead, since on Windows the file cannot be removed later while
    # it is still open.
    queue._db.close()

    queue = queue_cls.from_crawler(crawler=crawler, key=key)
    try:
        assert len(queue) == 1
        request = queue.pop()
        assert request is not None
        assert request.url == "https://toscrape.com"
    finally:
        queue.close()


class TestFifoMemoryQueueRequest(TestRequestQueueBase):
    is_fifo = True

    @pytest.fixture
    def q(self, crawler):
        return build_from_crawler(FifoMemoryQueue, crawler)


class TestLifoMemoryQueueRequest(TestRequestQueueBase):
    is_fifo = False

    @pytest.fixture
    def q(self, crawler):
        return build_from_crawler(LifoMemoryQueue, crawler)
