from __future__ import annotations

import hashlib
import logging
from typing import TYPE_CHECKING, Any, Protocol, cast

# typing.Self requires Python 3.11
from typing_extensions import Self

from scrapy import Request
from scrapy.utils.misc import build_from_crawler

if TYPE_CHECKING:
    from collections.abc import Iterable

    from scrapy.core.downloader import Downloader
    from scrapy.crawler import Crawler

logger = logging.getLogger(__name__)


def _path_safe(text: str) -> str:
    """
    Return a filesystem-safe version of a string ``text``

    >>> _path_safe('simple.org').startswith('simple.org')
    True
    >>> _path_safe('dash-underscore_.org').startswith('dash-underscore_.org')
    True
    >>> _path_safe('some@symbol?').startswith('some_symbol_')
    True
    """
    pathable_slot = "".join([c if c.isalnum() or c in "-._" else "_" for c in text])
    # as we replace some letters we can get collision for different slots
    # add we add unique part
    unique_slot = hashlib.md5(text.encode("utf8")).hexdigest()  # noqa: S324
    return f"{pathable_slot}-{unique_slot}"


class QueueProtocol(Protocol):
    """:class:`~typing.Protocol` of queues for the
    :setting:`SCHEDULER_MEMORY_QUEUE` and :setting:`SCHEDULER_DISK_QUEUE`
    settings.

    Queues may also define a ``peek()`` method, identical to :meth:`pop` except
    that the returned request is not removed from the queue.
    """

    def push(self, request: Request) -> None:
        """Add *request* to the queue.

        Raise :exc:`ValueError` if *request* cannot be stored, e.g. if
        the queue stores requests on disk but it cannot serialize *request*.
        """

    def pop(self) -> Request | None:
        """Remove the next request from the queue and return it, or return
        ``None`` if there are no requests."""

    def close(self) -> None:
        """Called when the queue is closed. May be used for cleanup code."""

    def __len__(self) -> int:
        """Return the number of requests that are currently in the queue."""


class PriorityQueueProtocol(Protocol):
    """:class:`~typing.Protocol` of queues for the
    :setting:`SCHEDULER_PRIORITY_QUEUE` setting."""

    @classmethod
    def from_crawler(
        cls,
        crawler: Crawler,
        downstream_queue_cls: type[QueueProtocol],
        key: str,
        startprios: Any = None,
    ) -> Self:
        """Create an instance of the queue.

        See :meth:`__init__` for details.
        """

    def __init__(
        self,
        crawler: Crawler,
        downstream_queue_cls: type[QueueProtocol],
        key: str,
        startprios: Any = None,
    ):
        """Initializes the queue.

        *crawler* is the running crawler.

        *downstream_queue_cls* is an :ref:`internal queue
        <custom-internal-queue>`, e.g. a :ref:`memory queue <memory-queues>` or
        a :ref:`disk queue <disk-queues>`. Each set of same-priority requests
        should be stored in an instance of this queue.

        *key* is the path where the queue should serialize requests, if the
        queue uses disk storage. Queues that do not use disk storage may ignore
        this parameter.

        If :ref:`resuming a job <topics-jobs>`, *startprios* is the return
        value of the previous call to :meth:`close`. Otherwise, it is a falsy
        value (e.g. ``None`` or an empty :class:`list`).
        """

    def push(self, request: Request) -> None:
        """Add *request* to the queue.

        Raise :exc:`ValueError` if *request* cannot be stored, e.g. if
        the queue stores requests on disk but it cannot serialize *request*.
        """

    def pop(self) -> Request | None:
        """Remove the next request from the queue and return it, or return
        ``None`` if there are no requests."""

    def close(self) -> Any:
        """Called when closing the queue if the priority queue was initialized
        with a disk-based internal queue.

        It must return JSON-serializable data representing the internal state
        of the queue. The returned data will be passed back to :meth:`__init__`
        as *startprio* when :ref:`resuming a job <topics-jobs>`.
        """

    def __len__(self) -> int:
        """Return the number of requests that are currently in the queue."""


class ScrapyPriorityQueue:
    """Default scheduler priority queue (:setting:`SCHEDULER_PRIORITY_QUEUE`).

    Sorts requests based solely on :attr:`Request.priority
    <scrapy.Request.priority>`.

    Requests with the same :attr:`Request.priority <scrapy.Request.priority>`
    value are sorted by the corresponding internal queue,
    :setting:`SCHEDULER_MEMORY_QUEUE` or :setting:`SCHEDULER_DISK_QUEUE`.

    Which internal queue is used depends on the value of :setting:`JOBDIR`:

    -   If :setting:`JOBDIR` is not set, :setting:`SCHEDULER_MEMORY_QUEUE` is
        always used.

    -   If :setting:`JOBDIR` is set, :setting:`SCHEDULER_DISK_QUEUE` is used by
        default, while :setting:`SCHEDULER_MEMORY_QUEUE` is used as a fallback
        for requests that :setting:`SCHEDULER_DISK_QUEUE` cannot serialize.

        When returning a request, memory requests always take precedence over
        disk requests.
    """

    @classmethod
    def from_crawler(
        cls,
        crawler: Crawler,
        downstream_queue_cls: type[QueueProtocol],
        key: str,
        startprios: Iterable[int] = (),
    ) -> Self:
        return cls(crawler, downstream_queue_cls, key, startprios)

    def __init__(
        self,
        crawler: Crawler,
        downstream_queue_cls: type[QueueProtocol],
        key: str,
        startprios: Iterable[int] = (),
    ):
        self.crawler: Crawler = crawler
        self.downstream_queue_cls: type[QueueProtocol] = downstream_queue_cls
        self.key: str = key
        self.queues: dict[int, QueueProtocol] = {}
        self.curprio: int | None = None
        self.init_prios(startprios)

    def init_prios(self, startprios: Iterable[int]) -> None:
        if not startprios:
            return

        for priority in startprios:
            self.queues[priority] = self.qfactory(priority)

        self.curprio = min(startprios)

    def qfactory(self, key: int) -> QueueProtocol:
        return build_from_crawler(
            self.downstream_queue_cls,
            self.crawler,
            self.key + "/" + str(key),
        )

    def priority(self, request: Request) -> int:
        return -request.priority

    def push(self, request: Request) -> None:
        priority = self.priority(request)
        if priority not in self.queues:
            self.queues[priority] = self.qfactory(priority)
        q = self.queues[priority]
        q.push(request)  # this may fail (eg. serialization error)
        if self.curprio is None or priority < self.curprio:
            self.curprio = priority

    def pop(self) -> Request | None:
        if self.curprio is None:
            return None
        q = self.queues[self.curprio]
        m = q.pop()
        if not q:
            del self.queues[self.curprio]
            q.close()
            prios = [p for p, q in self.queues.items() if q]
            self.curprio = min(prios) if prios else None
        return m

    def peek(self) -> Request | None:
        """Returns the next object to be returned by :meth:`pop`,
        but without removing it from the queue.

        Raises :exc:`NotImplementedError` if the underlying queue class does
        not implement a ``peek`` method, which is optional for queues.
        """
        if self.curprio is None:
            return None
        queue = self.queues[self.curprio]
        # Protocols can't declare optional members
        return cast(Request, queue.peek())  # type: ignore[attr-defined]

    def close(self) -> list[int]:
        active: list[int] = []
        for p, q in self.queues.items():
            active.append(p)
            q.close()
        return active

    def __len__(self) -> int:
        return sum(len(x) for x in self.queues.values()) if self.queues else 0


class DownloaderInterface:
    def __init__(self, crawler: Crawler):
        assert crawler.engine
        self.downloader: Downloader = crawler.engine.downloader

    def stats(self, possible_slots: Iterable[str]) -> list[tuple[int, str]]:
        return [(self._active_downloads(slot), slot) for slot in possible_slots]

    def get_slot_key(self, request: Request) -> str:
        return self.downloader.get_slot_key(request)

    def _active_downloads(self, slot: str) -> int:
        """Return a number of requests in a Downloader for a given slot"""
        if slot not in self.downloader.slots:
            return 0
        return len(self.downloader.slots[slot].active)


class DownloaderAwarePriorityQueue:
    """Scheduler priority queue (:setting:`SCHEDULER_PRIORITY_QUEUE`) that
    accounts for the download slot (usually the domain name) of active requests
    (i.e. requests being downloaded).

    It prioritizes requests that have their download slot in common with
    *fewer* active requests. Otherwise, it works like
    :class:`ScrapyPriorityQueue`.

    It works better than :class:`ScrapyPriorityQueue` for :ref:`broad crawls
    <broad-crawls>`.

    Cannot work with :setting:`CONCURRENT_REQUESTS_PER_IP`.
    """

    @classmethod
    def from_crawler(
        cls,
        crawler: Crawler,
        downstream_queue_cls: type[QueueProtocol],
        key: str,
        startprios: dict[str, Iterable[int]] | None = None,
    ) -> Self:
        return cls(crawler, downstream_queue_cls, key, startprios)

    def __init__(
        self,
        crawler: Crawler,
        downstream_queue_cls: type[QueueProtocol],
        key: str,
        slot_startprios: dict[str, Iterable[int]] | None = None,
    ):
        if crawler.settings.getint("CONCURRENT_REQUESTS_PER_IP") != 0:
            raise ValueError(
                f'"{self.__class__}" does not support CONCURRENT_REQUESTS_PER_IP'
            )

        if slot_startprios and not isinstance(slot_startprios, dict):
            raise ValueError(
                "DownloaderAwarePriorityQueue accepts "
                "``slot_startprios`` as a dict; "
                f"{slot_startprios.__class__!r} instance "
                "is passed. Most likely, it means the state is "
                "created by an incompatible priority queue. "
                "Only a crawl started with the same priority "
                "queue class can be resumed."
            )

        self._downloader_interface: DownloaderInterface = DownloaderInterface(crawler)
        self.downstream_queue_cls: type[QueueProtocol] = downstream_queue_cls
        self.key: str = key
        self.crawler: Crawler = crawler

        self.pqueues: dict[str, ScrapyPriorityQueue] = {}  # slot -> priority queue
        for slot, startprios in (slot_startprios or {}).items():
            self.pqueues[slot] = self.pqfactory(slot, startprios)

    def pqfactory(
        self, slot: str, startprios: Iterable[int] = ()
    ) -> ScrapyPriorityQueue:
        return ScrapyPriorityQueue(
            self.crawler,
            self.downstream_queue_cls,
            self.key + "/" + _path_safe(slot),
            startprios,
        )

    def pop(self) -> Request | None:
        stats = self._downloader_interface.stats(self.pqueues)

        if not stats:
            return None

        slot = min(stats)[1]
        queue = self.pqueues[slot]
        request = queue.pop()
        if len(queue) == 0:
            del self.pqueues[slot]
        return request

    def push(self, request: Request) -> None:
        slot = self._downloader_interface.get_slot_key(request)
        if slot not in self.pqueues:
            self.pqueues[slot] = self.pqfactory(slot)
        queue = self.pqueues[slot]
        queue.push(request)

    def peek(self) -> Request | None:
        """Returns the next object to be returned by :meth:`pop`,
        but without removing it from the queue.

        Raises :exc:`NotImplementedError` if the underlying queue class does
        not implement a ``peek`` method, which is optional for queues.
        """
        stats = self._downloader_interface.stats(self.pqueues)
        if not stats:
            return None
        slot = min(stats)[1]
        queue = self.pqueues[slot]
        return queue.peek()

    def close(self) -> dict[str, list[int]]:
        active = {slot: queue.close() for slot, queue in self.pqueues.items()}
        self.pqueues.clear()
        return active

    def __len__(self) -> int:
        return sum(len(x) for x in self.pqueues.values()) if self.pqueues else 0

    def __contains__(self, slot: str) -> bool:
        return slot in self.pqueues
