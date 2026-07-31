from __future__ import annotations

import hashlib
import heapq
import json
import logging
import time
from typing import TYPE_CHECKING, Protocol, cast

from scrapy.throttler import _mark_request_delayed, iter_scopes
from scrapy.utils.misc import build_from_crawler

if TYPE_CHECKING:
    from collections.abc import Callable, Collection, Iterable

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
        while self.curprio is not None:
            for queues in (self.queues, self._start_queues):
                q = queues.get(self.curprio)
                # An empty queue can linger at a priority when a push failed
                # after creating it (e.g. a serialization error), so it is
                # skipped rather than popped from: popping would return None
                # and hide the request that the other dict may hold at the same
                # priority.
                if not q:
                    continue
                m = q.pop()
                if not q:
                    # Always refresh, even if the other dict is not empty: it
                    # may have no queue at this priority, and leaving curprio
                    # pointing at a priority that neither dict has would make
                    # peek() come up empty.
                    self._update_curprio()
                return m
            # Nothing to pop at this priority: refreshing drops the empty
            # leftovers and moves on to the next priority.
            self._update_curprio()
        return None

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
        # The dicts are walked in the same order as in pop(), which is what makes
        # the returned request the one that pop() then returns; a caller that
        # peeks to decide whether to pop (see
        # ThrottlerAwarePriorityQueue._select) would otherwise act on one request
        # and dequeue another.
        for queues in (self.queues, self._start_queues):
            queue = queues.get(self.curprio)
            # Empty queues can linger at a priority (see pop()), and skipping
            # them is what keeps them from hiding the request that the other
            # dict may hold at the same priority.
            if queue:
                # Protocols can't declare optional members
                return cast("Request", queue.peek())  # type: ignore[attr-defined]
        return None

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
    requests with :ref:`several scopes <custom-throttling-scopes>` are balanced
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


def _scope_set_key(scope_set: frozenset[ScopeID]) -> str:
    """Return a reversible, JSON-safe string key for *scope_set*.

    Used both as the in-memory dict key encoding for the on-disk state and to
    derive the per-scope-set subdirectory name. The encoding is
    order-independent (the scope ids are sorted)."""
    return json.dumps(sorted(scope_set))


def _scope_set_from_key(key: str) -> frozenset[ScopeID]:
    """Reverse :func:`_scope_set_key`, raising :exc:`ValueError` for a *key*
    that it did not produce (e.g. the plain slot name that another priority
    queue class recorded in the same place)."""
    scope_ids = _decode_scope_ids(key)
    if scope_ids is None:
        raise ValueError(f"{key!r} is not a throttling scope set key.")
    return frozenset(scope_ids)


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

        # Scope sets grouped by the priority of the request at the head of their
        # queue (their "band"), so that _select() can go straight to the
        # best-priority candidates instead of walking every pending scope set,
        # which on a broad crawl means every pending domain. A band is a dict
        # rather than a set so that iteration stays insertion-ordered, and hence
        # deterministic. _band_of records where each scope set is filed so that
        # _reindex() can move it; both are maintained there, and nowhere else.
        self._bands: dict[int, dict[frozenset[ScopeID], None]] = {}
        self._band_of: dict[frozenset[ScopeID], int] = {}

        if slot_startprios:
            # Every key is decoded before any queue is created, so that an
            # incompatible state does not leave restored queues open behind the
            # error below.
            try:
                scope_sets = {
                    _scope_set_from_key(set_key): startprios
                    for set_key, startprios in slot_startprios.items()
                }
            except ValueError as e:
                raise ValueError(
                    f"ThrottlerAwarePriorityQueue cannot read its "
                    f"``slot_startprios``: {e} Most likely, it means the state "
                    f"is created by an incompatible priority queue. Only a crawl "
                    f"started with the same priority queue class can be resumed."
                ) from None
            for scope_set, startprios in scope_sets.items():
                self.pqueues[scope_set] = self._pqfactory(scope_set, startprios)
                self._reindex(scope_set)

        # Requests held back by their own per-request delay wait
        # here instead of in their scope-set queue, so a not-yet-due request
        # never sits at a queue head and blocks the other requests that share
        # its scopes (the head-of-line blocking this scheduler exists to
        # avoid). Once the delay elapses, _promote_ready() moves the request
        # into its scope-set queue, where it competes normally.
        #
        # A min-heap of (deadline, seq, scope_set, request): seq (a monotonic
        # counter) breaks deadline ties, so heapq never gets to compare the
        # scope_set (a frozenset, only partially ordered) or the request (not
        # ordered at all).
        self._delayed: list[tuple[float, int, frozenset[ScopeID], Request]] = []
        self._delayed_seq: int = 0

        # Where a request that this queue cannot store goes instead (see
        # _release_delayed). Scheduler points it at the memory queue; left
        # unset, an unstorable request is dropped.
        self.on_unstorable: Callable[[Request], None] | None = None

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

    def push(self, request: Request) -> None:
        scope_set = frozenset(iter_scopes(self._throttler.get_resolved_scopes(request)))
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
        # A push that raises (a serialization error) leaves the head where it
        # was, so there is nothing to reindex on that path.
        self.pqueues[scope_set].push(request)
        self._reindex(scope_set)

    def _reindex(self, scope_set: frozenset[ScopeID]) -> None:
        """File *scope_set* under the priority of its queue head, moving it out
        of whichever band it was in. Call after anything that can change that
        head, i.e. after a push into its queue and after a pop out of it."""
        previous = self._band_of.pop(scope_set, None)
        if previous is not None:
            band = self._bands[previous]
            del band[scope_set]
            if not band:
                del self._bands[previous]
        queue = self.pqueues.get(scope_set)
        # curprio is the priority the head is stored under, i.e.
        # queue.priority(queue.peek()), without the cost of peeking. A queue with
        # no head (gone, or left empty by a failed push) belongs to no band,
        # which is what keeps _select() from considering it.
        if queue is None or queue.curprio is None:
            return
        self._band_of[scope_set] = queue.curprio
        self._bands.setdefault(queue.curprio, {})[scope_set] = None

    def _promote_ready(self, now: float) -> None:
        """Move every held-back request whose per-request delay has elapsed into
        its scope-set queue, where it competes normally for its scopes."""
        while self._delayed and self._delayed[0][0] <= now:
            self._release_delayed(heapq.heappop(self._delayed))

    def _release_delayed(
        self, entry: tuple[float, int, frozenset[ScopeID], Request]
    ) -> None:
        _, _, scope_set, request = entry
        # The delay has been honored, or the queue is closing and the deadline
        # would be meaningless on resume.
        _mark_request_delayed(request)
        try:
            self._push_to_queue(request, scope_set)
        except ValueError as e:
            # A disk queue serializes on push; held-back requests defer that
            # serialization until here, so a non-serializable one would
            # otherwise raise while flushing on close and take the rest of the
            # disk queue down with it.
            logger.warning(
                "Unable to serialize request: %(request)s - reason: %(reason)s",
                {"request": request, "reason": e},
                exc_info=True,
                extra={"spider": getattr(self.crawler, "spider", None)},
            )
            if self.crawler.stats is not None:
                self.crawler.stats.inc_value("scheduler/unserializable")
            # Hand it over to the fallback, which is how it gets the same
            # memory-queue second chance that a request failing to serialize at
            # enqueue time gets. Without one there is nowhere left to put it.
            if self.on_unstorable is not None:
                self.on_unstorable(request)

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

        Candidates are visited band by band (see :attr:`_bands`), best priority
        first, so that a sendable one is normally found without looking at every
        pending scope set: a band is left as soon as it yields a candidate, and
        a candidate of zero load ends the search outright.

        The head of a queue is read with ``peek()``, and it is what ``pop()``
        then returns, so the request whose readiness decides the choice is the
        one that :meth:`pop` dequeues.
        """
        self._promote_ready(time.monotonic())
        best_load: float | None = None
        best: tuple[frozenset[ScopeID], ScrapyPriorityQueue] | None = None
        # There are few distinct priorities in a crawl, so this outer loop is
        # short; the inner one is what the bands keep from covering everything.
        for band in sorted(self._bands):
            for scope_set in self._bands[band]:
                queue = self.pqueues[scope_set]
                head = queue.peek()
                if head is None or not self._throttler.is_ready(head):
                    continue
                load = _scopes_load(self._throttler, scope_set)
                if not load:
                    return scope_set, queue
                if best_load is None or load < best_load:
                    best_load = load
                    best = (scope_set, queue)
            if best is not None:
                return best
        return None

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
        self._reindex(scope_set)
        return request

    def get_next_request_delay(self) -> float | None:
        now = time.monotonic()
        # Anything sendable means no wakeup is needed, and _select() answers
        # that without walking every pending scope set (it promotes the requests
        # whose delay has elapsed on the way).
        if self._select() is not None:
            return 0.0
        delay: float | None = None
        for queue in self.pqueues.values():
            head = queue.peek()
            if head is None:
                continue
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
        self._bands.clear()
        self._band_of.clear()
        return active

    def __len__(self) -> int:
        queued = sum(len(x) for x in self.pqueues.values()) if self.pqueues else 0
        return queued + len(self._delayed)
