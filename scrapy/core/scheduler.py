from __future__ import annotations

import json
import logging
from abc import abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

# working around https://github.com/sphinx-doc/sphinx/issues/10400
from twisted.internet.defer import Deferred  # noqa: TC002

from scrapy.spiders import Spider  # noqa: TC001
from scrapy.throttling import iter_scopes
from scrapy.utils.job import job_dir
from scrapy.utils.misc import build_from_crawler, load_object

if TYPE_CHECKING:
    # requires queuelib >= 1.6.2
    from queuelib.queue import BaseQueue

    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.crawler import Crawler
    from scrapy.dupefilters import BaseDupeFilter
    from scrapy.http.request import Request
    from scrapy.pqueues import ScrapyPriorityQueue
    from scrapy.statscollectors import StatsCollector
    from scrapy.throttling import ThrottlingManagerProtocol


logger = logging.getLogger(__name__)


class BaseSchedulerMeta(type):
    """
    Metaclass to check scheduler classes against the necessary interface
    """

    def __instancecheck__(cls, instance: Any) -> bool:
        return cls.__subclasscheck__(type(instance))

    def __subclasscheck__(cls, subclass: type) -> bool:
        return (
            hasattr(subclass, "has_pending_requests")
            and callable(subclass.has_pending_requests)
            and hasattr(subclass, "enqueue_request")
            and callable(subclass.enqueue_request)
            and hasattr(subclass, "next_request")
            and callable(subclass.next_request)
        )


class BaseScheduler(metaclass=BaseSchedulerMeta):
    """The scheduler component is responsible for storing requests received
    from the engine, and feeding them back upon request (also to the engine).

    The original sources of said requests are:

    * Spider: ``start`` method, requests created for URLs in the ``start_urls`` attribute, request callbacks
    * Spider middleware: ``process_spider_output`` and ``process_spider_exception`` methods
    * Downloader middleware: ``process_request``, ``process_response`` and ``process_exception`` methods

    The order in which the scheduler returns its stored requests (via the ``next_request`` method)
    plays a great part in determining the order in which those requests are downloaded. See :ref:`request-order`.

    The methods defined in this class constitute the minimal interface that the Scrapy engine will interact with.
    """

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        """
        Factory method which receives the current :class:`~scrapy.crawler.Crawler` object as argument.
        """
        return cls()

    def open(self, spider: Spider) -> Deferred[None] | None:
        """
        Called when the spider is opened by the engine. It receives the spider
        instance as argument and it's useful to execute initialization code.

        :param spider: the spider object for the current crawl
        :type spider: :class:`~scrapy.spiders.Spider`
        """

    def close(self, reason: str) -> Deferred[None] | None:
        """
        Called when the spider is closed by the engine. It receives the reason why the crawl
        finished as argument and it's useful to execute cleaning code.

        :param reason: a string which describes the reason why the spider was closed
        :type reason: :class:`str`
        """

    @abstractmethod
    def has_pending_requests(self) -> bool:
        """
        ``True`` if the scheduler has enqueued requests, ``False`` otherwise
        """
        raise NotImplementedError

    @abstractmethod
    def enqueue_request(self, request: Request) -> bool:
        """
        Process a request received by the engine.

        Return ``True`` if the request is stored correctly, ``False`` otherwise.

        If ``False``, the engine will fire a ``request_dropped`` signal, and
        will not make further attempts to schedule the request at a later time.
        For reference, the default Scrapy scheduler returns ``False`` when the
        request is rejected by the dupefilter.
        """
        raise NotImplementedError

    @abstractmethod
    def next_request(self) -> Request | None:
        """
        Return the next :class:`~scrapy.Request` to be processed, or ``None``
        to indicate that there are no requests to be considered ready at the moment.

        Returning ``None`` implies that no request from the scheduler will be sent
        to the downloader in the current reactor cycle. The engine will continue
        calling ``next_request`` until ``has_pending_requests`` is ``False``.
        """
        raise NotImplementedError


class Scheduler(BaseScheduler):
    r"""Default scheduler.

    Requests are stored into priority queues
    (:setting:`SCHEDULER_PRIORITY_QUEUE`) that sort requests by
    :attr:`~scrapy.http.Request.priority`.

    By default, memory-based priority queues are used for all requests.
    When using :setting:`JOBDIR`, disk-based priority queues are also created,
    and only unserializable requests are stored in the memory-based priority
    queues. For a given priority value, requests in memory take precedence over
    requests in disk.

    Each priority queue stores requests in separate internal queues, one per
    priority value. The memory priority queue uses
    :setting:`SCHEDULER_MEMORY_QUEUE` queues, while the disk priority queue
    uses :setting:`SCHEDULER_DISK_QUEUE` queues. The internal queues determine
    :ref:`request order <request-order>` when requests have the same priority.
    :ref:`Start requests <start-requests>` are stored into separate internal
    queues by default, and :ref:`ordered differently <start-request-order>`.

    Duplicate requests are filtered out with an instance of
    :setting:`DUPEFILTER_CLASS`.

    .. _request-order:

    Request order
    =============

    With default settings, pending requests are stored in a LIFO_ queue
    (:ref:`except for start requests <start-request-order>`). As a result,
    crawling happens in `DFO order`_, which is usually the most convenient
    crawl order. However, you can enforce :ref:`BFO <bfo>` or :ref:`a custom
    order <custom-request-order>` (:ref:`except for the first few requests
    <concurrency-v-order>`).

    .. _LIFO: https://en.wikipedia.org/wiki/Stack_(abstract_data_type)
    .. _DFO order: https://en.wikipedia.org/wiki/Depth-first_search

    .. _start-request-order:

    Start request order
    -------------------

    :ref:`Start requests <start-requests>` are sent in the order they are
    yielded from :meth:`~scrapy.Spider.start`, and given the same
    :attr:`~scrapy.http.Request.priority`, other requests take precedence over
    start requests.

    You can set :setting:`SCHEDULER_START_MEMORY_QUEUE` and
    :setting:`SCHEDULER_START_DISK_QUEUE` to ``None`` to handle start requests
    the same as other requests when it comes to order and priority.


    .. _bfo:

    Crawling in BFO order
    ---------------------

    If you do want to crawl in `BFO order`_, you can do it by setting the
    following :ref:`settings <topics-settings>`:

    | :setting:`DEPTH_PRIORITY` = ``1``
    | :setting:`SCHEDULER_DISK_QUEUE` =
      ``"scrapy.squeues.PickleFifoDiskQueue"``
    | :setting:`SCHEDULER_MEMORY_QUEUE` = ``"scrapy.squeues.FifoMemoryQueue"``

    .. _BFO order: https://en.wikipedia.org/wiki/Breadth-first_search


    .. _custom-request-order:

    Crawling in a custom order
    --------------------------

    You can manually set :attr:`~scrapy.http.Request.priority` on requests to
    force a specific request order.


    .. _concurrency-v-order:

    Concurrency affects order
    -------------------------

    While pending requests are below the configured values of
    :setting:`CONCURRENT_REQUESTS` or :setting:`THROTTLING_SCOPE_CONCURRENCY`,
    those requests are sent concurrently.

    As a result, the first few requests of a crawl may not follow the desired
    order. Lowering those settings to ``1`` enforces the desired order except
    for the very first request, but it significantly slows down the crawl as a
    whole.

    Job directory contents
    ======================

    .. warning:: The files that this class generates in the :ref:`job directory
        <job-dir>` are an implementation detail, and may change without a
        warning in a future version of Scrapy. Do not rely on the following
        information for anything other than debugging purposes.

    When using :setting:`JOBDIR`, this scheduler class:

    -   Creates a directory named ``requests.queue`` inside the :ref:`job
        directory <job-dir>`, meant to keep track of all requests stored in
        the scheduler (i.e. not downloaded yet).

    -   Generates inside that directory an ``active.json`` file with a JSON
        representation of the state (``startprios``) of
        :setting:`SCHEDULER_PRIORITY_QUEUE`.

        The file is generated whenever the job stops (cleanly) and is loaded
        when resuming the job.

    -   Instantiates the configured :setting:`SCHEDULER_PRIORITY_QUEUE` with
        ``requests.queue/`` as persistence directory (*key*) and
        :setting:`SCHEDULER_DISK_QUEUE` as *downstream_queue_cls*. The priority
        queue may create additional files and directories inside that
        directory, directly or though instances of
        :setting:`SCHEDULER_DISK_QUEUE`.

    This scheduler class also uses the configured :setting:`DUPEFILTER_CLASS`,
    which may also write data inside the job directory.
    """

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        dupefilter_cls = load_object(crawler.settings["DUPEFILTER_CLASS"])
        return cls(
            dupefilter=build_from_crawler(dupefilter_cls, crawler),
            jobdir=job_dir(crawler.settings),
            dqclass=load_object(crawler.settings["SCHEDULER_DISK_QUEUE"]),
            mqclass=load_object(crawler.settings["SCHEDULER_MEMORY_QUEUE"]),
            logunser=crawler.settings.getbool("SCHEDULER_DEBUG"),
            stats=crawler.stats,
            pqclass=load_object(crawler.settings["SCHEDULER_PRIORITY_QUEUE"]),
            crawler=crawler,
        )

    def __init__(
        self,
        dupefilter: BaseDupeFilter,
        jobdir: str | None = None,
        dqclass: type[BaseQueue] | None = None,
        mqclass: type[BaseQueue] | None = None,
        logunser: bool = False,
        stats: StatsCollector | None = None,
        pqclass: type[ScrapyPriorityQueue] | None = None,
        crawler: Crawler | None = None,
    ):
        """Initialize the scheduler.

        :param dupefilter: An object responsible for checking and filtering duplicate requests.
                        The value for the :setting:`DUPEFILTER_CLASS` setting is used by default.
        :type dupefilter: :class:`scrapy.dupefilters.BaseDupeFilter` instance or similar:
                        any class that implements the `BaseDupeFilter` interface

        :param jobdir: The path of a directory to be used for persisting the crawl's state.
                    The value for the :setting:`JOBDIR` setting is used by default.
                    See :ref:`topics-jobs`.
        :type jobdir: :class:`str` or ``None``

        :param dqclass: A class to be used as persistent request queue.
                        The value for the :setting:`SCHEDULER_DISK_QUEUE` setting is used by default.
        :type dqclass: class

        :param mqclass: A class to be used as non-persistent request queue.
                        The value for the :setting:`SCHEDULER_MEMORY_QUEUE` setting is used by default.
        :type mqclass: class

        :param logunser: A boolean that indicates whether or not unserializable requests should be logged.
                        The value for the :setting:`SCHEDULER_DEBUG` setting is used by default.
        :type logunser: bool

        :param stats: A stats collector object to record stats about the request scheduling process.
                    The value for the :setting:`STATS_CLASS` setting is used by default.
        :type stats: :class:`scrapy.statscollectors.StatsCollector` instance or similar:
                    any class that implements the `StatsCollector` interface

        :param pqclass: A class to be used as priority queue for requests.
                        The value for the :setting:`SCHEDULER_PRIORITY_QUEUE` setting is used by default.
        :type pqclass: class

        :param crawler: The crawler object corresponding to the current crawl.
        :type crawler: :class:`scrapy.crawler.Crawler`
        """
        self.df: BaseDupeFilter = dupefilter
        self.dqdir: str | None = self._dqdir(jobdir)
        self.pqclass: type[ScrapyPriorityQueue] | None = pqclass
        self.dqclass: type[BaseQueue] | None = dqclass
        self.mqclass: type[BaseQueue] | None = mqclass
        self.logunser: bool = logunser
        self.stats: StatsCollector | None = stats
        self.crawler: Crawler | None = crawler
        self._sdqclass: type[BaseQueue] | None = self._get_start_queue_cls(
            crawler, "DISK"
        )
        self._smqclass: type[BaseQueue] | None = self._get_start_queue_cls(
            crawler, "MEMORY"
        )

    def _get_start_queue_cls(
        self, crawler: Crawler | None, queue: str
    ) -> type[BaseQueue] | None:
        if crawler is None:
            return None
        cls = crawler.settings[f"SCHEDULER_START_{queue}_QUEUE"]
        if not cls:
            return None
        return cast("type[BaseQueue]", load_object(cls))

    def has_pending_requests(self) -> bool:
        return len(self) > 0

    def open(self, spider: Spider) -> Deferred[None] | None:
        """
        (1) initialize the memory queue
        (2) initialize the disk queue if the ``jobdir`` argument wasn't empty
        (3) return the result of the dupefilter's ``open`` method
        """
        self.spider: Spider = spider
        self.mqs: ScrapyPriorityQueue = self._mq()
        self.dqs: ScrapyPriorityQueue | None = self._dq() if self.dqdir else None
        return self.df.open()

    def close(self, reason: str) -> Deferred[None] | None:
        """
        (1) dump pending requests to disk if there is a disk queue
        (2) return the result of the dupefilter's ``close`` method
        """
        if self.dqs is not None:
            state = self.dqs.close()
            assert isinstance(self.dqdir, str)
            self._write_dqs_state(self.dqdir, state)
        return self.df.close(reason)

    def enqueue_request(self, request: Request) -> bool:
        """
        Unless the received request is filtered out by the Dupefilter, attempt to push
        it into the disk queue, falling back to pushing it into the memory queue.

        Increment the appropriate stats, such as: ``scheduler/enqueued``,
        ``scheduler/enqueued/disk``, ``scheduler/enqueued/memory``.

        Return ``True`` if the request was stored successfully, ``False`` otherwise.
        """
        if not request.dont_filter and self.df.request_seen(request):
            self.df.log(request, self.spider)
            return False
        dqok = self._dqpush(request)
        assert self.stats is not None
        if dqok:
            self.stats.inc_value("scheduler/enqueued/disk")
        else:
            self._mqpush(request)
            self.stats.inc_value("scheduler/enqueued/memory")
        self.stats.inc_value("scheduler/enqueued")
        return True

    def next_request(self) -> Request | None:
        """
        Return a :class:`~scrapy.Request` object from the memory queue,
        falling back to the disk queue if the memory queue is empty.
        Return ``None`` if there are no more enqueued requests.

        Increment the appropriate stats, such as: ``scheduler/dequeued``,
        ``scheduler/dequeued/disk``, ``scheduler/dequeued/memory``.
        """
        request: Request | None = self.mqs.pop()
        assert self.stats is not None
        if request is not None:
            self.stats.inc_value("scheduler/dequeued/memory")
        else:
            request = self._dqpop()
            if request is not None:
                self.stats.inc_value("scheduler/dequeued/disk")
        if request is not None:
            self.stats.inc_value("scheduler/dequeued")
        return request

    def __len__(self) -> int:
        """
        Return the total amount of enqueued requests
        """
        return len(self.dqs) + len(self.mqs) if self.dqs is not None else len(self.mqs)

    def _dqpush(self, request: Request) -> bool:
        if self.dqs is None:
            return False
        try:
            self.dqs.push(request)
        except ValueError as e:  # non serializable request
            if self.logunser:
                msg = (
                    "Unable to serialize request: %(request)s - reason:"
                    " %(reason)s - no more unserializable requests will be"
                    " logged (stats being collected)"
                )
                logger.warning(
                    msg,
                    {"request": request, "reason": e},
                    exc_info=True,
                    extra={"spider": self.spider},
                )
                self.logunser = False
            assert self.stats is not None
            self.stats.inc_value("scheduler/unserializable")
            return False
        return True

    def _mqpush(self, request: Request) -> None:
        self.mqs.push(request)

    def _dqpop(self) -> Request | None:
        if self.dqs is not None:
            return self.dqs.pop()
        return None

    def _mq(self) -> ScrapyPriorityQueue:
        """Create a new priority queue instance, with in-memory storage"""
        assert self.crawler
        assert self.pqclass
        return build_from_crawler(
            self.pqclass,
            self.crawler,
            downstream_queue_cls=self.mqclass,
            key="",
            start_queue_cls=self._smqclass,
        )

    def _dq(self) -> ScrapyPriorityQueue:
        """Create a new priority queue instance, with disk storage"""
        assert self.crawler
        assert self.dqdir
        assert self.pqclass
        state = self._read_dqs_state(self.dqdir)
        q = build_from_crawler(
            self.pqclass,
            self.crawler,
            downstream_queue_cls=self.dqclass,
            key=self.dqdir,
            startprios=state,
            start_queue_cls=self._sdqclass,
        )
        if q:
            logger.info(
                "Resuming crawl (%(queuesize)d requests scheduled)",
                {"queuesize": len(q)},
                extra={"spider": self.spider},
            )
        return q

    def _dqdir(self, jobdir: str | None) -> str | None:
        """Return a folder name to keep disk queue state at"""
        if jobdir:
            dqdir = Path(jobdir, "requests.queue")
            if not dqdir.exists():
                dqdir.mkdir(parents=True)
            return str(dqdir)
        return None

    def _read_dqs_state(self, dqdir: str) -> Any:
        path = Path(dqdir, "active.json")
        if not path.exists():
            return ()
        with path.open(encoding="utf-8") as f:
            return json.load(f)

    def _write_dqs_state(self, dqdir: str, state: Any) -> None:
        with Path(dqdir, "active.json").open("w", encoding="utf-8") as f:
            json.dump(state, f)


def _queue_supports_peek(queue_cls: type) -> bool:
    """Return whether *queue_cls* (a Scrapy queue class) is backed by an
    underlying queue that really implements ``peek``.

    Scrapy's queue wrappers in :mod:`scrapy.squeues` always define a ``peek``
    method, but it merely delegates to the underlying queue class (e.g. a
    queuelib one, which only gained ``peek`` in queuelib 1.6.1) and raises
    :exc:`NotImplementedError` if that one lacks it. This checks the real
    implementation by ignoring the delegating wrappers.
    """
    return any(
        "peek" in base.__dict__ and base.__module__ != "scrapy.squeues"
        for base in queue_cls.__mro__
    )


class ThrottlingAwareScheduler(Scheduler):
    """A :setting:`SCHEDULER` that only ever hands the engine requests whose
    :ref:`throttling scopes <throttling-scopes>` allow them to be sent **right
    now**.

    This avoids the head-of-line blocking that the default scheduler can suffer
    when a crawl mixes heavily-throttled scopes with unthrottled ones: with the
    default scheduler, requests taken from the scheduler in order wait at the
    throttling gate
    (:meth:`~scrapy.throttling.ThrottlingManagerProtocol.acquire`) while
    holding a concurrency slot, so enough throttled requests waiting on a clock
    can fill :setting:`CONCURRENT_REQUESTS` and starve unthrottled requests
    that could be sent right away. Requests held back by this scheduler instead
    occupy neither concurrency slots nor memory (beyond what is needed to track
    each distinct scope set), so they cannot starve other scopes.

    When several requests could be sent at the same time, the one with the
    highest request :attr:`~scrapy.Request.priority` is sent first; ties are
    broken by preferring the least-busy scopes.

    It requires :setting:`SCHEDULER_PRIORITY_QUEUE` to be set to
    :class:`~scrapy.pqueues.ThrottlingAwarePriorityQueue` (or a compatible
    subclass), and the configured :setting:`SCHEDULER_DISK_QUEUE` /
    :setting:`SCHEDULER_MEMORY_QUEUE` to support ``peek``.
    """

    def open(self, spider: Spider) -> Deferred[None] | None:
        result = super().open(spider)
        if not hasattr(self.mqs, "get_next_request_delay"):
            raise ValueError(
                f"{type(self).__name__} requires SCHEDULER_PRIORITY_QUEUE to be "
                f"set to a throttling-aware priority queue such as "
                f"scrapy.pqueues.ThrottlingAwarePriorityQueue, but the "
                f"configured one ({type(self.mqs).__name__}) is not."
            )
        for setting, pq in (
            ("SCHEDULER_MEMORY_QUEUE", self.mqs),
            ("SCHEDULER_DISK_QUEUE", self.dqs),
        ):
            if pq is None:
                continue
            queue_cls = getattr(pq, "downstream_queue_cls", None)
            if queue_cls is not None and not _queue_supports_peek(queue_cls):
                raise ValueError(
                    f"{type(self).__name__} requires {setting} to be set to a "
                    f"queue class that supports peek(), but the configured one "
                    f"({queue_cls.__name__}) does not."
                )
        assert self.crawler is not None
        assert self.crawler.throttler is not None
        self._throttler: ThrottlingManagerProtocol = self.crawler.throttler
        return result

    def enqueue_request(self, request: Request) -> bool:
        raise RuntimeError(
            "ThrottlingAwareScheduler requires the asynchronous enqueue path; "
            "enqueue_request_async() is used by the engine instead of "
            "enqueue_request()."
        )

    async def enqueue_request_async(self, request: Request) -> bool:
        """Resolve the :ref:`throttling scope set <throttling-scopes>` of
        *request* and store it under the queue for that scope set.

        This is the asynchronous counterpart of
        :meth:`Scheduler.enqueue_request`; scope resolution
        (:meth:`~scrapy.throttling.ThrottlingManagerProtocol.get_scopes`) is
        asynchronous, which is why enqueuing has to be too.
        """
        if not request.dont_filter and self.df.request_seen(request):
            self.df.log(request, self.spider)
            return False
        scope_set = frozenset(iter_scopes(await self._throttler.get_scopes(request)))
        assert self.stats is not None
        if self._dqpush_throttling(request, scope_set):
            self.stats.inc_value("scheduler/enqueued/disk")
        else:
            self.mqs.push(request, scope_set)  # type: ignore[call-arg]
            self.stats.inc_value("scheduler/enqueued/memory")
        self.stats.inc_value("scheduler/enqueued")
        return True

    def _dqpush_throttling(self, request: Request, scope_set: frozenset[str]) -> bool:
        if self.dqs is None:
            return False
        try:
            self.dqs.push(request, scope_set)  # type: ignore[call-arg]
        except ValueError as e:  # non serializable request
            if self.logunser:
                logger.warning(
                    "Unable to serialize request: %(request)s - reason:"
                    " %(reason)s - no more unserializable requests will be"
                    " logged (stats being collected)",
                    {"request": request, "reason": e},
                    exc_info=True,
                    extra={"spider": self.spider},
                )
                self.logunser = False
            assert self.stats is not None
            self.stats.inc_value("scheduler/unserializable")
            return False
        return True

    def get_next_request_delay(self) -> float | None:
        """Return the minimum number of seconds until some pending request
        becomes sendable because a time-based throttling gate opens, or
        ``None`` if no pending request is time-blocked.

        The engine uses this to arm a single wakeup timer when
        :meth:`next_request` returns ``None`` while requests are still
        pending."""
        delays = [
            delay
            for pq in (self.mqs, self.dqs)
            if pq is not None and (delay := pq.get_next_request_delay()) is not None  # type: ignore[attr-defined]
        ]
        return min(delays) if delays else None
