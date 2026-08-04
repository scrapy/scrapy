from __future__ import annotations

import hashlib
import json
import logging
from typing import TYPE_CHECKING, Protocol, cast

from scrapy.utils.misc import build_from_crawler

if TYPE_CHECKING:
    from collections.abc import Collection, Iterable

    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy import Request
    from scrapy.crawler import Crawler
    from scrapy.throttler import ScopeID, ThrottlerProtocol

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
    # Replacing characters can make different inputs collapse to the same
    # prefix, so a hash of the original text keeps the result unique.
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
    FIFO queues). It uses one internal queue for each priority value. The
    internal queue must implement the following methods:

        * push(obj)
        * pop()
        * close()
        * __len__()

    Optionally, the queue could provide a ``peek`` method, that should return
    the next object to be returned by ``pop``, but without removing it from the
    queue.

    ``__init__`` method of ScrapyPriorityQueue receives a downstream_queue_cls
    argument, which is a class used to instantiate a new (internal) queue when
    a new priority is allocated.

    Only integer priorities should be used. Lower numbers are higher
    priorities.

    startprios is a sequence of priorities to start with. If the queue was
    previously closed leaving some priority buckets non-empty, those priorities
    should be passed in startprios.

    Disk persistence
    ================

    .. warning:: The files that this class generates on disk are an
        implementation detail, and may change without a warning in a future
        version of Scrapy. Do not rely on the following information for
        anything other than debugging purposes.

    When a component instantiates this class with a non-empty *key* argument,
    *key* is used as a persistence directory.

    For every request enqueued, this class checks:

    -   Whether the request is a :ref:`start request <start-requests>` or not.

    -   The :data:`~scrapy.Request.priority` of the request.

    For each combination of the above seen, this class creates an instance of
    *downstream_queue_cls* (or *start_queue_cls* for start requests if it was
    passed) with *key* set to a subdirectory of the persistence directory,
    named as the negated request priority (e.g. ``-1``), with an ``s`` suffix
    in case of a start request (e.g. ``-1s``).
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
            self.queues[priority] = self.qfactory(priority)
            if self._start_queue_cls:
                self._start_queues[priority] = self._sqfactory(priority)

        # Not min(startprios): a recorded priority may have no queue to restore
        # (e.g. it only ever held a request that failed to serialize), and
        # leaving curprio pointing at a priority that neither dict has would
        # make peek() come up empty. This also drops and closes the queues that
        # turned out to have nothing to restore.
        self._update_curprio()

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
        if self.curprio is None:
            return None
        q = self._queue_at(self.curprio)
        m = q.pop()
        if not q:
            # Always refresh, even if the other dict is not empty: it may have
            # no queue at this priority, and leaving curprio pointing at a
            # priority that neither dict has would make peek() come up empty.
            self._update_curprio()
        return m

    def _queue_at(self, priority: int) -> QueueProtocol:
        """Return the queue holding the next request at *priority*.

        An empty queue can linger at a priority when a push failed after
        creating it (e.g. a serialization error), so it is skipped rather than
        popped from: popping would return None and hide the request that the
        other dict holds at the same priority. One of the two dicts always has a
        request at :attr:`curprio`, since :meth:`_update_curprio` drops a
        priority where neither does.
        """
        return self.queues.get(priority) or self._start_queues[priority]

    def _update_curprio(self) -> None:
        # Empty queues are dropped rather than merely skipped: keeping one would
        # hold its storage open for nothing, and record on close a priority with
        # nothing to restore from it.
        prios: set[int] = set()
        for queues in (self.queues, self._start_queues):
            for p, q in list(queues.items()):
                if q:
                    prios.add(p)
                else:
                    del queues[p]
                    q.close()
        self.curprio = min(prios) if prios else None

    def peek(self) -> Request | None:
        """Returns the next object to be returned by :meth:`pop`,
        but without removing it from the queue.

        Raises :exc:`NotImplementedError` if the underlying queue class does
        not implement a ``peek`` method, which is optional for queues.
        """
        if self.curprio is None:
            return None
        # The very queue that pop() pops from, which is what makes the returned
        # request the one that pop() then returns; a caller that peeks to decide
        # whether to pop would otherwise act on one request and dequeue another.
        queue = self._queue_at(self.curprio)
        # Protocols can't declare optional members
        return cast("Request", queue.peek())  # type: ignore[attr-defined]

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


def _decode_scope_ids(key: str) -> tuple[ScopeID, ...] | None:
    """Return the scope IDs that *key* is a JSON array of, or ``None`` if it is
    not such an array."""
    try:
        decoded = json.loads(key)
    except ValueError:
        return None
    if not isinstance(decoded, list) or not all(isinstance(s, str) for s in decoded):
        return None
    return tuple(decoded)


def _decode_slot_scopes(slot: str) -> tuple[ScopeID, ...]:
    """Return the :ref:`throttling scopes <throttling-scopes>` that *slot*
    stands for.

    This reverses the three encodings of
    :meth:`~scrapy.throttler.ThrottlerProtocol.get_scopes_key`: an empty string
    for no scope, the ID itself for a single one, a JSON array of sorted IDs for
    several. A single scope whose ID looks like such an array is indistinguishable
    from it, and is read as the array; the only cost is a load reading for a
    scope with a very unusual name.
    """
    if not slot:
        return ()
    scope_ids = _decode_scope_ids(slot)
    return (slot,) if scope_ids is None else scope_ids


def _scopes_load(throttler: ThrottlerProtocol, scopes: Collection[ScopeID]) -> float:
    """Return the load of *scopes* as a whole: the highest load among them,
    since a queue of requests sharing them cannot be dequeued faster than their
    busiest one allows."""
    # This runs for every pending scope set on every pop, and almost every scope
    # set holds a single scope; skipping the max() there measures 2.5x faster.
    if len(scopes) == 1:
        return throttler.get_scope_load(next(iter(scopes)))
    return max(map(throttler.get_scope_load, scopes), default=0.0)


class DownloaderAwarePriorityQueue:
    """PriorityQueue which takes Downloader activity into account:
    domains (slots) with the least amount of active downloads are dequeued
    first.

    A slot stands for the :ref:`throttling scopes <throttling-scopes>` of the
    requests it holds, and its load is the highest load among those scopes,
    since a slot cannot be dequeued faster than its busiest scope allows. So
    requests with several scopes are balanced
    by whichever of their scopes is the most constrained.

    .. note:: Slots are keyed by
        :meth:`~scrapy.throttler.ThrottlerProtocol.get_scopes_key`, which
        resolves the scopes of a request synchronously, because
        :meth:`~scrapy.core.scheduler.BaseScheduler.enqueue_request` is
        synchronous. Custom scoping is therefore best expressed by overriding
        :meth:`~scrapy.throttler.Throttler.get_default_scopes`, which that key
        goes through. Scoping that needs ``await`` cannot be reproduced by any
        synchronous method, and grouping is approximate for it; see
        :ref:`async-throttling-scopes`.

    Disk persistence
    ================

    .. warning:: The files that this class generates on disk are an
        implementation detail, and may change without a warning in a future
        version of Scrapy. Do not rely on the following information for
        anything other than debugging purposes.

    When a component instantiates this class with a non-empty *key* argument,
    *key* is used as a persistence directory, and inside that directory this
    class creates a subdirectory per download slot (domain).

    Those subdirectories are named after the corresponding download slot, with
    path-unsafe characters replaced by underscores and an MD5 hash suffix to
    avoid collisions.

    For each download slot, this class creates an instance of
    :class:`ScrapyPriorityQueue` with the download slot subdirectory as *key*
    and its own *downstream_queue_cls*.
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

        assert crawler.throttler is not None
        self._throttler: ThrottlerProtocol = crawler.throttler
        self.downstream_queue_cls: type[QueueProtocol] = downstream_queue_cls
        self._start_queue_cls: type[QueueProtocol] | None = start_queue_cls
        self.key: str = key
        self.crawler: Crawler = crawler

        self.pqueues: dict[str, ScrapyPriorityQueue] = {}  # slot -> priority queue
        # The throttling scopes each slot stands for, decoded from its key once
        # (see _decode_slot_scopes) rather than on every read: _slot_stats()
        # reads the load of every pending slot on every pop, which on a broad
        # crawl means every pending domain. Kept in step with pqueues by
        # _add_slot() and _remove_slot(), and nowhere else.
        self._slot_scopes: dict[str, tuple[ScopeID, ...]] = {}
        self._last_selected_slot: str | None = None
        if slot_startprios:
            for slot, startprios in slot_startprios.items():
                self._add_slot(slot, startprios)

    def _next_slot(self, stats: list[tuple[float, str]], *, update_state: bool) -> str:
        # Lexicographic on (load, slot): the least-loaded slot, and the
        # lowest-named one among ties.
        min_load, slot = min(stats)
        last = self._last_selected_slot
        if last is not None:
            # Round-robin among the tied slots: the first one after the last
            # selected, so that equally-loaded slots take turns rather than the
            # lowest-named one always winning.
            slot = min(
                (s for load, s in stats if load == min_load and s > last), default=slot
            )
        if update_state:
            self._last_selected_slot = slot
        return slot

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

    def _add_slot(
        self, slot: str, startprios: Iterable[int] = ()
    ) -> ScrapyPriorityQueue:
        queue = self.pqfactory(slot, startprios)
        self.pqueues[slot] = queue
        self._slot_scopes[slot] = _decode_slot_scopes(slot)
        return queue

    def _remove_slot(self, slot: str) -> None:
        del self.pqueues[slot]
        del self._slot_scopes[slot]

    def _slot_stats(self) -> list[tuple[float, str]]:
        return [
            (_scopes_load(self._throttler, scopes), slot)
            for slot, scopes in self._slot_scopes.items()
        ]

    def pop(self) -> Request | None:
        stats = self._slot_stats()

        if not stats:
            return None

        slot = self._next_slot(stats, update_state=True)
        queue = self.pqueues[slot]
        request = queue.pop()
        if len(queue) == 0:
            self._remove_slot(slot)
        return request

    def push(self, request: Request) -> None:
        slot = self._throttler.get_scopes_key(request)
        queue = self.pqueues.get(slot)
        if queue is None:
            queue = self._add_slot(slot)
        queue.push(request)

    def peek(self) -> Request | None:
        """Returns the next object to be returned by :meth:`pop`,
        but without removing it from the queue.

        Raises :exc:`NotImplementedError` if the underlying queue class does
        not implement a ``peek`` method, which is optional for queues.
        """
        stats = self._slot_stats()
        if not stats:
            return None
        slot = self._next_slot(stats, update_state=False)
        queue = self.pqueues[slot]
        return queue.peek()

    def close(self) -> dict[str, list[int]]:
        active = {slot: queue.close() for slot, queue in self.pqueues.items()}
        self.pqueues.clear()
        self._slot_scopes.clear()
        return active

    def __len__(self) -> int:
        return sum(len(x) for x in self.pqueues.values()) if self.pqueues else 0

    def __contains__(self, slot: str) -> bool:
        return slot in self.pqueues
