from __future__ import annotations

import hashlib
import heapq
import json
import logging
import time
from typing import TYPE_CHECKING, Protocol, cast

from scrapy.utils.misc import build_from_crawler

if TYPE_CHECKING:
    from collections.abc import Iterable

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
            q = self.qfactory(priority)
            if q:
                self.queues[priority] = q
            else:
                q.close()
            if self._start_queue_cls:
                q = self._sqfactory(priority)
                if q:
                    self._start_queues[priority] = q
                else:
                    q.close()

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
            queue = self.queues[self.curprio]
        except KeyError:
            queue = self._start_queues[self.curprio]
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


class DownloaderAwarePriorityQueue:
    """PriorityQueue which takes Downloader activity into account:
    domains (slots) with the least amount of active downloads are dequeued
    first.

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

        assert crawler.throttler is not None
        self._throttler: ThrottlerProtocol = crawler.throttler
        self.downstream_queue_cls: type[QueueProtocol] = downstream_queue_cls
        self._start_queue_cls: type[QueueProtocol] | None = start_queue_cls
        self.key: str = key
        self.crawler: Crawler = crawler

        self.pqueues: dict[str, ScrapyPriorityQueue] = {}  # slot -> priority queue
        self._last_selected_slot: str | None = None
        if slot_startprios:
            for slot, startprios in slot_startprios.items():
                self.pqueues[slot] = self.pqfactory(slot, startprios)

    def _next_slot(self, stats: list[tuple[float, str]], *, update_state: bool) -> str:
        last = self._last_selected_slot
        min_load: float | None = None
        best_slot: str | None = None
        best_slot_after_last: str | None = None
        for load, slot in stats:
            if min_load is None or load < min_load:
                min_load = load
                best_slot = slot
                best_slot_after_last = None
                if last is not None and slot > last:
                    best_slot_after_last = slot
            elif load == min_load:
                if best_slot is None or slot < best_slot:
                    best_slot = slot
                if (
                    last is not None
                    and slot > last
                    and (best_slot_after_last is None or slot < best_slot_after_last)
                ):
                    best_slot_after_last = slot
        assert best_slot is not None
        slot = best_slot_after_last if best_slot_after_last is not None else best_slot
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

    def _slot_stats(self) -> list[tuple[float, str]]:
        return [(self._throttler.get_scope_load(slot), slot) for slot in self.pqueues]

    def pop(self) -> Request | None:
        stats = self._slot_stats()

        if not stats:
            return None

        slot = self._next_slot(stats, update_state=True)
        queue = self.pqueues[slot]
        request = queue.pop()
        if len(queue) == 0:
            del self.pqueues[slot]
        return request

    def push(self, request: Request) -> None:
        slot = self._throttler.get_scopes_key(request)
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
        stats = self._slot_stats()
        if not stats:
            return None
        slot = self._next_slot(stats, update_state=False)
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


def _scope_set_key(scope_set: frozenset[ScopeID]) -> str:
    """Return a reversible, JSON-safe string key for *scope_set*.

    Used both as the in-memory dict key encoding for the on-disk state and to
    derive the per-scope-set subdirectory name. The encoding is
    order-independent (the scope ids are sorted)."""
    return json.dumps(sorted(scope_set))


def _scope_set_from_key(key: str) -> frozenset[ScopeID]:
    return frozenset(json.loads(key))


class ThrottlerAwarePriorityQueue:
    """Priority queue that only ever pops a request that can be sent right now
    based on its :ref:`throttling scope set <throttling-scopes>` and
    per-request :reqmeta:`delay`.

    The downstream queue class must support ``peek``.

    Disk persistence
    ================

    .. warning:: The files that this class generates on disk are an
        implementation detail, and may change without a warning in a future
        version of Scrapy. Do not rely on the following information for
        anything other than debugging purposes.

    When instantiated with a non-empty *key* argument, *key* is used as a
    persistence directory, and inside it this class creates a subdirectory per
    scope set, named from a path-safe, order-independent encoding of its scope
    ids.

    For example, a request whose scope set is ``{"example.com",
    "cost:group-1"}`` is stored under a subdirectory derived in two steps:

    #.  The scope ids are sorted and JSON-encoded into an order-independent key
        (so ``{"example.com", "cost:group-1"}`` and ``{"cost:group-1",
        "example.com"}`` map to the same one)::

            ["cost:group-1", "example.com"]

    #.  That key is made path-safe: every character outside ``[A-Za-z0-9-._]``
        becomes ``_`` (here the ``:`` and the JSON quotes, brackets and spaces;
        the ``-`` and ``.`` are kept), and an MD5 suffix disambiguates keys that
        collapse to the same path::

            __cost_group-1____example.com__-fc6ba2aff8f421bf981b662d77739902
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
                "ThrottlerAwarePriorityQueue accepts ``slot_startprios`` as a "
                f"dict; {slot_startprios.__class__!r} instance is passed. Most "
                "likely, it means the state is created by an incompatible "
                "priority queue. Only a crawl started with the same priority "
                "queue class can be resumed."
            )

        assert crawler.throttler is not None
        self._throttler: ThrottlerProtocol = crawler.throttler
        self.downstream_queue_cls: type[QueueProtocol] = downstream_queue_cls
        self._start_queue_cls: type[QueueProtocol] | None = start_queue_cls
        self.key: str = key
        self.crawler: Crawler = crawler

        self.pqueues: dict[frozenset[ScopeID], ScrapyPriorityQueue] = {}
        if slot_startprios:
            for set_key, startprios in slot_startprios.items():
                scope_set = _scope_set_from_key(set_key)
                self.pqueues[scope_set] = self._pqfactory(scope_set, startprios)

        # Requests held back by their own per-request delay wait
        # here instead of in their scope-set queue, so a not-yet-due request
        # never sits at a queue head and blocks the other requests that share
        # its scopes (the head-of-line blocking this scheduler exists to
        # avoid). Once the delay elapses, _promote_ready() moves the request
        # into its scope-set queue, where it competes normally.
        #
        # This is a min-heap of (deadline, seq, scope_set, request). heapq
        # needs a total order and always compares entries to keep its invariant;
        # seq (a monotonic counter) makes the (deadline, seq) prefix totally
        # ordered, so a deadline tie is broken there and the scope_set (a
        # frozenset, whose < is only the partial subset order) and the request
        # (no ordering at all) are never compared. The order among tied
        # deadlines is irrelevant beyond being deterministic.
        self._delayed: list[tuple[float, int, frozenset[ScopeID], Request]] = []
        self._delayed_seq: int = 0

    def _pqfactory(
        self, scope_set: frozenset[ScopeID], startprios: Iterable[int] = ()
    ) -> ScrapyPriorityQueue:
        return ScrapyPriorityQueue(
            self.crawler,
            self.downstream_queue_cls,
            self.key + "/" + _path_safe(_scope_set_key(scope_set)),
            startprios,
            start_queue_cls=self._start_queue_cls,
        )

    def push(self, request: Request, scope_set: frozenset[ScopeID]) -> None:
        now = time.monotonic()
        self._promote_ready(now)
        delay = self._throttler.get_request_delay(request, now)
        if delay > 0:
            self._delayed_seq += 1
            heapq.heappush(
                self._delayed, (now + delay, self._delayed_seq, scope_set, request)
            )
            return
        self._push_to_queue(request, scope_set)

    def _push_to_queue(self, request: Request, scope_set: frozenset[ScopeID]) -> None:
        if scope_set not in self.pqueues:
            self.pqueues[scope_set] = self._pqfactory(scope_set)
        self.pqueues[scope_set].push(request)

    def _promote_ready(self, now: float) -> None:
        """Move every held-back request whose per-request delay has elapsed into
        its scope-set queue, where it competes normally for its scopes."""
        while self._delayed and self._delayed[0][0] <= now:
            self._release_delayed(heapq.heappop(self._delayed))

    def _release_delayed(
        self, entry: tuple[float, int, frozenset[ScopeID], Request]
    ) -> None:
        _, _, scope_set, request = entry
        # The per-request delay has been honored (or the queue is closing), so
        # mark it consumed: the request must not be delayed again, and on resume
        # it must not re-block its scope set on a stale, no-longer-meaningful
        # deadline.
        request.meta["_throttler_delayed"] = True
        try:
            self._push_to_queue(request, scope_set)
        except ValueError as e:
            # A disk queue serializes on push; held-back requests defer that
            # serialization until here, so a non-serializable one would
            # otherwise raise while flushing on close and take the rest of the
            # disk queue down with it. Drop it with a warning instead, matching
            # how the scheduler handles unserializable requests at enqueue time.
            logger.warning(
                "Unable to serialize request: %(request)s - reason: %(reason)s",
                {"request": request, "reason": e},
                exc_info=True,
                extra={"spider": getattr(self.crawler, "spider", None)},
            )
            if self.crawler.stats is not None:
                self.crawler.stats.inc_value("scheduler/unserializable")

    def _select(
        self,
    ) -> tuple[frozenset[ScopeID], ScrapyPriorityQueue] | None:
        """Return the sendable ``(scope_set, queue)`` pair to pop from, or
        ``None`` if no queue can be popped from right now.

        Among the sendable queues (those whose scope set can be sent right now),
        the one whose head has the highest request priority is chosen; ties are
        broken by ascending load (the maximum
        :meth:`~scrapy.throttler.ThrottlerProtocol.get_scope_load` over the
        scopes of the queue), i.e. by preferring the least-busy scopes.
        """
        self._promote_ready(time.monotonic())
        best_sort_key: tuple[int, float] | None = None
        best: tuple[frozenset[ScopeID], ScrapyPriorityQueue] | None = None
        for scope_set, queue in self.pqueues.items():
            head = queue.peek()
            if head is None or not self._throttler.is_ready(head):
                continue
            load = max(
                (self._throttler.get_scope_load(scope_id) for scope_id in scope_set),
                default=0.0,
            )
            sort_key = (queue.priority(head), load)
            if best_sort_key is None or sort_key < best_sort_key:
                best_sort_key = sort_key
                best = (scope_set, queue)
        return best

    def pop(self) -> Request | None:
        selected = self._select()
        if selected is None:
            return None
        scope_set, queue = selected
        request = queue.pop()
        if request is not None:
            self._throttler.reserve(request)
        if len(queue) == 0:
            del self.pqueues[scope_set]
        return request

    def get_next_request_delay(self) -> float | None:
        now = time.monotonic()
        self._promote_ready(now)
        delay: float | None = None
        for queue in self.pqueues.values():
            head = queue.peek()
            if head is None:
                continue
            if self._throttler.is_ready(head):
                return 0.0
            head_delay = self._throttler.get_time_until_ready(head)
            if head_delay is None:
                continue
            if delay is None or head_delay < delay:
                delay = head_delay
        # A request held back only by its own delay is not in any
        # scope-set queue, so factor in when the earliest one is due.
        if self._delayed:
            next_delayed = max(0.0, self._delayed[0][0] - now)
            if delay is None or next_delayed < delay:
                delay = next_delayed
        return delay

    def close(self) -> dict[str, list[int]]:
        # Flush held-back requests into their scope-set queues so they are
        # persisted (and restored on resume) rather than lost.
        while self._delayed:
            self._release_delayed(heapq.heappop(self._delayed))
        active = {
            _scope_set_key(scope_set): queue.close()
            for scope_set, queue in self.pqueues.items()
        }
        self.pqueues.clear()
        return active

    def __len__(self) -> int:
        queued = sum(len(x) for x in self.pqueues.values()) if self.pqueues else 0
        return queued + len(self._delayed)
