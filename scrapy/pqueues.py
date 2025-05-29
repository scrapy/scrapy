from __future__ import annotations

import hashlib
import logging
from typing import TYPE_CHECKING, Protocol, cast

from scrapy import Request
from scrapy.utils.misc import build_from_crawler

if TYPE_CHECKING:
    from collections.abc import Iterable

    # typing.Self requires Python 3.11
    from typing_extensions import Self

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
    """Protocol for downstream queues of ``ScrapyPriorityQueue``."""

    def push(self, request: Request) -> None: ...

    def pop(self) -> Request | None: ...

    def close(self) -> None: ...

    def __len__(self) -> int: ...


class ScrapyPriorityQueue:
    """A priority queue implemented using multiple internal queues (typically,
    FIFO queues). It uses one internal queue for each priority value. The internal
    queue must implement the following methods:

        * push(obj)
        * pop()
        * close()
        * __len__()

    Optionally, the queue could provide a ``peek`` method, that should return the
    next object to be returned by ``pop``, but without removing it from the queue.

    ``__init__`` method of ScrapyPriorityQueue receives a downstream_queue_cls
    argument, which is a class used to instantiate a new (internal) queue when
    a new priority is allocated.

    Only integer priorities should be used. Lower numbers are higher
    priorities.

    startprios is a sequence of priorities to start with. If the queue was
    previously closed leaving some priority buckets non-empty, those priorities
    should be passed in startprios.
    """

    @classmethod
    def from_crawler(
        cls,
        crawler: Crawler,
        downstream_queue_cls: type[QueueProtocol],
        key: str,
        startprios: Iterable[int] = (),
        *,
        start_queue_cls: type[QueueProtocol] | None = None,
    ) -> Self:
        return cls(
            crawler,
            downstream_queue_cls,
            key,
            startprios,
            start_queue_cls=start_queue_cls,
        )

    def __init__(
        self,
        crawler: Crawler,
        downstream_queue_cls: type[QueueProtocol],
        key: str,
        startprios: Iterable[int] = (),
        *,
        start_queue_cls: type[QueueProtocol] | None = None,
    ):
        self.crawler: Crawler = crawler
        self.downstream_queue_cls: type[QueueProtocol] = downstream_queue_cls
        self._start_queue_cls: type[QueueProtocol] | None = start_queue_cls
        self.key: str = key
        self.queues: dict[int, QueueProtocol] = {}
        self._start_queues: dict[int, QueueProtocol] = {}
        self.curprio: int | None = None
        self.init_prios(startprios)

    def init_prios(self, startprios: Iterable[int]) -> None:
        if not startprios:
            return

        for priority in startprios:
            q = self.qfactory(priority)
            if q:
                self.queues[priority] = q
            if self._start_queue_cls:
                q = self._sqfactory(priority)
                if q:
                    self._start_queues[priority] = q

        self.curprio = min(startprios)

    def qfactory(self, key: int) -> QueueProtocol:
        return build_from_crawler(
            self.downstream_queue_cls,
            self.crawler,
            self.key + "/" + str(key),
        )

    def _sqfactory(self, key: int) -> QueueProtocol:
        assert self._start_queue_cls is not None
        return build_from_crawler(
            self._start_queue_cls,
            self.crawler,
            f"{self.key}/{key}s",
        )

    def priority(self, request: Request) -> int:
        return -request.priority

    def push(self, request: Request) -> None:
        priority = self.priority(request)
        is_start_request = request.meta.get("is_start_request", False)
        if is_start_request and self._start_queue_cls:
            if priority not in self._start_queues:
                self._start_queues[priority] = self._sqfactory(priority)
            q = self._start_queues[priority]
        else:
            if priority not in self.queues:
                self.queues[priority] = self.qfactory(priority)
            q = self.queues[priority]
        q.push(request)  # this may fail (eg. serialization error)
        if self.curprio is None or priority < self.curprio:
            self.curprio = priority

    def pop(self) -> Request | None:
        while self.curprio is not None:
            try:
                q = self.queues[self.curprio]
            except KeyError:
                pass
            else:
                m = q.pop()
                if not q:
                    del self.queues[self.curprio]
                    q.close()
                    if not self._start_queues:
                        self._update_curprio()
                return m
            if self._start_queues:
                try:
                    q = self._start_queues[self.curprio]
                except KeyError:
                    self._update_curprio()
                else:
                    m = q.pop()
                    if not q:
                        del self._start_queues[self.curprio]
                        q.close()
                        self._update_curprio()
                    return m
            else:
                self._update_curprio()
        return None

    def _update_curprio(self) -> None:
        prios = {
            p
            for queues in (self.queues, self._start_queues)
            for p, q in queues.items()
            if q
        }
        self.curprio = min(prios) if prios else None

    def peek(self) -> Request | None:
        """Returns the next object to be returned by :meth:`pop`,
        but without removing it from the queue.

        Raises :exc:`NotImplementedError` if the underlying queue class does
        not implement a ``peek`` method, which is optional for queues.
        """
        if self.curprio is None:
            return None
        try:
            queue = self._start_queues[self.curprio]
        except KeyError:
            queue = self.queues[self.curprio]
        # Protocols can't declare optional members
        return cast(Request, queue.peek())  # type: ignore[attr-defined]

    def close(self) -> list[int]:
        active: set[int] = set()
        for queues in (self.queues, self._start_queues):
            for p, q in queues.items():
                active.add(p)
                q.close()
        return list(active)

    def __len__(self) -> int:
        return (
            sum(
                len(x)
                for queues in (self.queues, self._start_queues)
                for x in queues.values()
            )
            if self.queues or self._start_queues
            else 0
        )


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
    """PriorityQueue which takes Downloader activity into account:
    domains (slots) with the least amount of active downloads are dequeued
    first.
    """

    @classmethod
    def from_crawler(
        cls,
        crawler: Crawler,
        downstream_queue_cls: type[QueueProtocol],
        key: str,
        startprios: dict[str, Iterable[int]] | None = None,
        *,
        start_queue_cls: type[QueueProtocol] | None = None,
    ) -> Self:
        return cls(
            crawler,
            downstream_queue_cls,
            key,
            startprios,
            start_queue_cls=start_queue_cls,
        )

    def __init__(
        self,
        crawler: Crawler,
        downstream_queue_cls: type[QueueProtocol],
        key: str,
        slot_startprios: dict[str, Iterable[int]] | None = None,
        *,
        start_queue_cls: type[QueueProtocol] | None = None,
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
        self._start_queue_cls: type[QueueProtocol] | None = start_queue_cls
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
            start_queue_cls=self._start_queue_cls,
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
