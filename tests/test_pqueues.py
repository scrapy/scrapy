from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import Mock

import pytest

from scrapy.core.downloader import Downloader
from scrapy.http.request import Request
from scrapy.pqueues import DownloaderAwarePriorityQueue, ScrapyPriorityQueue, _path_safe
from scrapy.spiders import Spider
from scrapy.squeues import FifoMemoryQueue, PickleFifoDiskQueue
from scrapy.utils.misc import build_from_crawler, load_object
from scrapy.utils.test import get_crawler
from tests.utils.downloader import MockDownloader

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    from scrapy.crawler import Crawler


class DroppingFifoMemoryQueue(FifoMemoryQueue):  # type: ignore[valid-type,misc]
    """Queue that drops requests marked with ``drop`` in their metadata, the
    way a custom queue class could drop requests it does not want to store."""

    def push(self, request: Request) -> None:
        if not request.meta.get("drop"):
            self.q.append(request)


def _pop(queue: ScrapyPriorityQueue | DownloaderAwarePriorityQueue) -> Request:
    request = queue.pop()
    assert request is not None
    return request


def _peek(queue: ScrapyPriorityQueue | DownloaderAwarePriorityQueue) -> Request:
    request = queue.peek()
    assert request is not None
    return request


class TestPriorityQueue:
    @pytest.fixture
    def crawler(self) -> Crawler:
        return get_crawler(Spider)

    def test_queue_push_pop_one(self, crawler: Crawler, tmp_path: Path) -> None:
        queue = build_from_crawler(
            ScrapyPriorityQueue, crawler, FifoMemoryQueue, str(tmp_path)
        )
        assert queue.pop() is None
        assert len(queue) == 0
        req1 = Request("https://example.org/1", priority=1)
        queue.push(req1)
        assert len(queue) == 1
        dequeued = _pop(queue)
        assert len(queue) == 0
        assert dequeued.url == req1.url
        assert dequeued.priority == req1.priority
        assert not queue.close()

    def test_peek(self, crawler: Crawler, tmp_path: Path) -> None:
        queue = build_from_crawler(
            ScrapyPriorityQueue, crawler, FifoMemoryQueue, str(tmp_path)
        )
        assert len(queue) == 0
        assert queue.peek() is None
        req1 = Request("https://example.org/1")
        req2 = Request("https://example.org/2")
        req3 = Request("https://example.org/3")
        queue.push(req1)
        queue.push(req2)
        queue.push(req3)
        assert len(queue) == 3
        assert _peek(queue).url == req1.url
        assert _pop(queue).url == req1.url
        assert len(queue) == 2
        assert _peek(queue).url == req2.url
        assert _pop(queue).url == req2.url
        assert len(queue) == 1
        assert _peek(queue).url == req3.url
        assert _pop(queue).url == req3.url
        assert not queue.close()

    def test_peek_after_draining_a_higher_priority_queue(
        self, crawler: Crawler, tmp_path: Path
    ) -> None:
        """Draining the queue of the current priority while start requests
        remain at a different one must not leave ``curprio`` pointing at a
        priority that no queue has, which would make ``peek()`` come up empty
        with requests still queued."""
        queue = ScrapyPriorityQueue.from_crawler(
            crawler,
            FifoMemoryQueue,
            str(tmp_path),
            start_queue_cls=FifoMemoryQueue,
        )
        start_request = Request(
            "https://example.org/start", meta={"is_start_request": True}
        )
        queue.push(start_request)
        # A redirect of a start request, which REDIRECT_PRIORITY_ADJUST puts at
        # a higher priority, i.e. in a separate, non-start queue.
        queue.push(Request("https://example.org/redirect", priority=2))

        assert _peek(queue).url == "https://example.org/redirect"
        assert _pop(queue).url == "https://example.org/redirect"
        assert _peek(queue).url == start_request.url
        assert _pop(queue).url == start_request.url
        assert queue.peek() is None
        queue.close()

    def test_peek_agrees_with_pop_on_start_requests(
        self, crawler: Crawler, tmp_path: Path
    ) -> None:
        """A start request and a non-start request at the same priority sit in
        separate queues, and ``peek()`` must report the one that ``pop()``
        returns, since a caller may peek to decide whether to pop."""
        queue = ScrapyPriorityQueue.from_crawler(
            crawler,
            FifoMemoryQueue,
            str(tmp_path),
            start_queue_cls=FifoMemoryQueue,
        )
        queue.push(
            Request("https://example.org/start", meta={"is_start_request": True})
        )
        queue.push(Request("https://example.org/other"))

        while len(queue):
            peeked = _peek(queue)
            assert _pop(queue).url == peeked.url
        queue.close()

    def test_peek_and_pop_skip_an_empty_queue_left_by_a_failed_push(
        self, crawler: Crawler, tmp_path: Path
    ) -> None:
        """A queue is created before the request is pushed into it, so a push
        that fails (e.g. a serialization error) leaves an empty queue behind at
        that priority. Neither ``peek()`` nor ``pop()`` may let it hide the
        request that the other dict holds at the same priority."""
        queue = ScrapyPriorityQueue.from_crawler(
            crawler,
            PickleFifoDiskQueue,
            str(tmp_path),
            start_queue_cls=PickleFifoDiskQueue,
        )
        with pytest.raises(ValueError, match="is not an instance method"):
            queue.push(
                Request(
                    "https://example.org/lambda",
                    callback=lambda response: None,  # type: ignore[misc]
                )
            )
        assert queue.queues[0] is not None  # the empty leftover
        assert len(queue) == 0

        start_request = Request(
            "https://example.org/start", meta={"is_start_request": True}
        )
        queue.push(start_request)
        assert len(queue) == 1
        assert _peek(queue).url == start_request.url
        assert _pop(queue).url == start_request.url
        assert len(queue) == 0
        assert queue.peek() is None
        assert queue.pop() is None
        queue.close()

    def test_empty_queues_are_dropped_on_refresh(
        self, crawler: Crawler, tmp_path: Path
    ) -> None:
        """The empty leftover of a failed push is forgotten (and closed) the
        next time the current priority is refreshed, rather than kept around
        holding its storage open."""
        queue = ScrapyPriorityQueue.from_crawler(
            crawler, PickleFifoDiskQueue, str(tmp_path)
        )
        with pytest.raises(ValueError, match="is not an instance method"):
            queue.push(
                Request(
                    "https://example.org/lambda",
                    callback=lambda response: None,  # type: ignore[misc]
                )
            )
        assert set(queue.queues) == {0}  # the empty leftover
        # A request at a different priority, whose queue emptying is what
        # triggers the refresh.
        queue.push(Request("https://example.org/1", priority=1))
        assert _pop(queue).url == "https://example.org/1"
        assert queue.queues == {}
        assert queue.curprio is None
        assert queue.pop() is None
        assert not queue.close()

    def test_push_into_a_queue_that_drops_the_request(
        self, crawler: Crawler, tmp_path: Path
    ) -> None:
        """A queue class may drop a request instead of storing it, and that
        priority must not become the current one, or ``peek()`` and ``pop()``
        would come up empty with requests still queued."""
        queue = ScrapyPriorityQueue.from_crawler(
            crawler, DroppingFifoMemoryQueue, str(tmp_path)
        )
        # A higher priority than the request below, so that it would become the
        # current priority if it were stored.
        queue.push(
            Request("https://example.org/dropped", priority=1, meta={"drop": True})
        )
        kept = Request("https://example.org/kept")
        queue.push(kept)

        assert len(queue) == 1
        assert _peek(queue).url == kept.url
        assert _pop(queue).url == kept.url
        assert queue.peek() is None
        assert queue.pop() is None
        assert not queue.close()

    def test_init_prios_without_a_restorable_queue(
        self, crawler: Crawler, tmp_path: Path
    ) -> None:
        """A priority recorded on close may have nothing to restore, e.g. if
        its only request failed to serialize. ``curprio`` must not point at it,
        or ``peek()`` raises :exc:`KeyError` on the resumed crawl."""
        queue = ScrapyPriorityQueue.from_crawler(
            crawler, PickleFifoDiskQueue, str(tmp_path)
        )
        with pytest.raises(ValueError, match="is not an instance method"):
            queue.push(
                Request(
                    "https://example.org/lambda",
                    callback=lambda response: None,  # type: ignore[misc]
                )
            )
        startprios = queue.close()
        assert startprios == [0]

        queue2 = ScrapyPriorityQueue.from_crawler(
            crawler, PickleFifoDiskQueue, str(tmp_path), startprios
        )
        assert len(queue2) == 0
        assert queue2.curprio is None
        assert queue2.peek() is None
        assert queue2.pop() is None
        queue2.close()

    def test_init_prios_with_start_queue(
        self, crawler: Crawler, tmp_path: Path
    ) -> None:
        queue = build_from_crawler(
            ScrapyPriorityQueue,
            crawler,
            PickleFifoDiskQueue,
            str(tmp_path),
            start_queue_cls=PickleFifoDiskQueue,
        )
        req = Request("https://example.org/", meta={"is_start_request": True})
        queue.push(req)
        startprios = queue.close()

        queue2 = build_from_crawler(
            ScrapyPriorityQueue,
            crawler,
            PickleFifoDiskQueue,
            str(tmp_path),
            startprios,
            start_queue_cls=PickleFifoDiskQueue,
        )
        assert len(queue2) == 1
        assert _pop(queue2).url == req.url
        queue2.close()

    def test_queue_push_pop_priorities(self, crawler: Crawler, tmp_path: Path) -> None:
        queue = build_from_crawler(
            ScrapyPriorityQueue, crawler, FifoMemoryQueue, str(tmp_path), [-1, -2, -3]
        )
        assert queue.pop() is None
        assert len(queue) == 0
        req1 = Request("https://example.org/1", priority=1)
        req2 = Request("https://example.org/2", priority=2)
        req3 = Request("https://example.org/3", priority=3)
        queue.push(req1)
        queue.push(req2)
        queue.push(req3)
        assert len(queue) == 3
        dequeued = _pop(queue)
        assert len(queue) == 2
        assert dequeued.url == req3.url
        assert dequeued.priority == req3.priority
        assert set(queue.close()) == {-1, -2}

    def test_next_priority_empty_startprios(self, crawler: Crawler) -> None:
        queue = build_from_crawler(
            ScrapyPriorityQueue, crawler, FifoMemoryQueue, "", [-1]
        )
        assert queue.next_priority() is None

    def test_next_priority_with_start_queue(self, crawler: Crawler) -> None:
        queue = build_from_crawler(
            ScrapyPriorityQueue,
            crawler,
            FifoMemoryQueue,
            "",
            start_queue_cls=FifoMemoryQueue,
        )
        queue.push(Request("https://example.org/1", meta={"is_start_request": True}))
        queue.push(Request("https://example.org/2", priority=1))
        assert queue.next_priority() == -1
        queue.pop()
        assert queue.next_priority() == 0
        queue.pop()
        assert queue.next_priority() is None


class TestDownloaderAwarePriorityQueue:
    @pytest.fixture
    def downloader(self) -> MockDownloader:
        return MockDownloader()

    @pytest.fixture
    def queue(
        self, downloader: MockDownloader
    ) -> Generator[DownloaderAwarePriorityQueue]:
        crawler = get_crawler(Spider)
        crawler.engine = Mock(downloader=downloader)
        queue = build_from_crawler(
            DownloaderAwarePriorityQueue,
            crawler,
            downstream_queue_cls=FifoMemoryQueue,
            key="foo/bar",
        )
        try:
            yield queue
        finally:
            queue.close()

    def test_push_pop(self, queue: DownloaderAwarePriorityQueue) -> None:
        assert len(queue) == 0
        assert queue.pop() is None
        req1 = Request("http://www.example.com/1")
        req2 = Request("http://www.example.com/2")
        req3 = Request("http://www.example.com/3")
        queue.push(req1)
        queue.push(req2)
        queue.push(req3)
        assert len(queue) == 3
        assert _pop(queue).url == req1.url
        assert len(queue) == 2
        assert _pop(queue).url == req2.url
        assert len(queue) == 1
        assert _pop(queue).url == req3.url
        assert len(queue) == 0
        assert queue.pop() is None

    def test_peek(self, queue: DownloaderAwarePriorityQueue) -> None:
        assert len(queue) == 0
        req1 = Request("https://example.org/1")
        req2 = Request("https://example.org/2")
        req3 = Request("https://example.org/3")
        queue.push(req1)
        queue.push(req2)
        queue.push(req3)
        assert len(queue) == 3
        assert _peek(queue).url == req1.url
        assert _pop(queue).url == req1.url
        assert len(queue) == 2
        assert _peek(queue).url == req2.url
        assert _pop(queue).url == req2.url
        assert len(queue) == 1
        assert _peek(queue).url == req3.url
        assert _pop(queue).url == req3.url
        assert queue.peek() is None

    def test_tie_breaking_rotates_slots(
        self, queue: DownloaderAwarePriorityQueue
    ) -> None:
        # No active downloads are tracked in the downloader, so every slot has
        # the same score and tie-breaking must not starve a slot.
        req_a1 = Request("https://example.org/a1")
        req_a1.meta[Downloader.DOWNLOAD_SLOT] = "slot-a"
        req_b1 = Request("https://example.org/b1")
        req_b1.meta[Downloader.DOWNLOAD_SLOT] = "slot-b"
        req_a2 = Request("https://example.org/a2")
        req_a2.meta[Downloader.DOWNLOAD_SLOT] = "slot-a"
        req_b2 = Request("https://example.org/b2")
        req_b2.meta[Downloader.DOWNLOAD_SLOT] = "slot-b"

        for request in (req_a1, req_b1, req_a2, req_b2):
            queue.push(request)

        slots = [
            _pop(queue).meta[Downloader.DOWNLOAD_SLOT],
            _pop(queue).meta[Downloader.DOWNLOAD_SLOT],
            _pop(queue).meta[Downloader.DOWNLOAD_SLOT],
            _pop(queue).meta[Downloader.DOWNLOAD_SLOT],
        ]

        assert slots == ["slot-a", "slot-b", "slot-a", "slot-b"]

    def test_tie_breaking_keeps_rotation_after_selected_slot_is_deleted(
        self, queue: DownloaderAwarePriorityQueue
    ) -> None:
        # If the selected slot becomes empty, rotation should continue from
        # that slot marker to avoid restarting from the smallest slot.
        req_a1 = Request("https://example.org/a1")
        req_a1.meta[Downloader.DOWNLOAD_SLOT] = "slot-a"
        req_a2 = Request("https://example.org/a2")
        req_a2.meta[Downloader.DOWNLOAD_SLOT] = "slot-a"
        req_b1 = Request("https://example.org/b1")
        req_b1.meta[Downloader.DOWNLOAD_SLOT] = "slot-b"
        req_c1 = Request("https://example.org/c1")
        req_c1.meta[Downloader.DOWNLOAD_SLOT] = "slot-c"

        for request in (req_a1, req_a2, req_b1, req_c1):
            queue.push(request)

        slots = [
            _pop(queue).meta[Downloader.DOWNLOAD_SLOT],
            _pop(queue).meta[Downloader.DOWNLOAD_SLOT],
            _pop(queue).meta[Downloader.DOWNLOAD_SLOT],
            _pop(queue).meta[Downloader.DOWNLOAD_SLOT],
        ]

        assert slots == ["slot-a", "slot-b", "slot-c", "slot-a"]

    def test_pop_prefers_slot_with_fewer_active_downloads(
        self, downloader: MockDownloader, queue: DownloaderAwarePriorityQueue
    ) -> None:
        req_a = Request("https://example.org/a")
        req_a.meta[Downloader.DOWNLOAD_SLOT] = "slot-a"
        req_b = Request("https://example.org/b")
        req_b.meta[Downloader.DOWNLOAD_SLOT] = "slot-b"
        req_c = Request("https://example.org/c")
        req_c.meta[Downloader.DOWNLOAD_SLOT] = "slot-c"

        for req in (req_a, req_b, req_c):
            queue.push(req)

        downloader.increment("slot-a")
        downloader.increment("slot-c")

        popped = _pop(queue)
        assert popped.url == req_b.url

    def test_contains(self, queue: DownloaderAwarePriorityQueue) -> None:
        req = Request("https://example.org/")
        req.meta[Downloader.DOWNLOAD_SLOT] = "example-slot"
        assert "example-slot" not in queue
        queue.push(req)
        assert "example-slot" in queue
        assert "other-slot" not in queue


def test_slot_directory_removed_when_slot_drains(tmp_path: Path) -> None:
    crawler = get_crawler(Spider)
    crawler.spider = crawler._create_spider("foo")
    crawler.engine = Mock(downloader=MockDownloader())
    queue = build_from_crawler(
        DownloaderAwarePriorityQueue,
        crawler,
        downstream_queue_cls=PickleFifoDiskQueue,
        key=str(tmp_path),
    )
    request = Request("https://example.org/1")
    slot_dir = tmp_path / _path_safe("example.org")

    queue.push(request)
    assert slot_dir.is_dir()

    assert _pop(queue).url == request.url
    assert not slot_dir.exists()

    queue.push(request)
    assert slot_dir.is_dir()
    queue.close()


@pytest.mark.parametrize(
    ("input_", "output"),
    [
        # By default, start requests are FIFO, other requests are LIFO.
        ([{}, {}], [2, 1]),
        ([{"start": True}, {"start": True}], [1, 2]),
        # Priority matters.
        ([{"priority": 1}, {"start": True}], [1, 2]),
        ([{}, {"start": True, "priority": 1}], [2, 1]),
        # For the same priority, start requests pop last.
        ([{}, {"start": True}], [1, 2]),
        ([{"start": True}, {}], [2, 1]),
    ],
)
def test_pop_order(input_: list[dict[str, Any]], output: list[int]) -> None:
    def make_url(index: int) -> str:
        return f"https://toscrape.com/{index}"

    def make_request(index: int, data: dict[str, Any]) -> Request:
        meta: dict[str, Any] = {}
        if data.get("start", False):
            meta["is_start_request"] = True
        return Request(
            url=make_url(index),
            priority=data.get("priority", 0),
            meta=meta,
        )

    input_requests = [
        make_request(index, data) for index, data in enumerate(input_, start=1)
    ]
    expected_output_urls = [make_url(index) for index in output]

    crawler = get_crawler(Spider)
    settings = crawler.settings
    queue = build_from_crawler(
        ScrapyPriorityQueue,
        crawler,
        downstream_queue_cls=load_object(settings["SCHEDULER_MEMORY_QUEUE"]),
        key="",
        start_queue_cls=load_object(settings["SCHEDULER_START_MEMORY_QUEUE"]),
    )

    for request in input_requests:
        queue.push(request)

    actual_output_urls = []
    while popped := queue.pop():
        actual_output_urls.append(popped.url)

    assert actual_output_urls == expected_output_urls
