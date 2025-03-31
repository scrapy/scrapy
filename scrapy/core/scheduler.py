from __future__ import annotations

import json
import logging
from abc import abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

# working around https://github.com/sphinx-doc/sphinx/issues/10400
from twisted.internet.defer import Deferred  # noqa: TC002

from scrapy.spiders import Spider  # noqa: TC001
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
    from scrapy.pqueues import PriorityQueueProtocol
    from scrapy.statscollectors import StatsCollector


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
    """Base class for :ref:`scheduler <topics-scheduler>` :ref:`components
    <topics-components>`."""

    @abstractmethod
    def enqueue_request(self, request: Request) -> bool:
        """Store or drop *request*.

        Return ``True`` if the request is stored or ``False`` if the request is
        dropped, e.g. because it is deemed a duplicate of a previously-seen
        request.

        Returning ``False`` triggers the :signal:`request_dropped` signal.
        """
        raise NotImplementedError

    @abstractmethod
    def next_request(self) -> Request | None:
        """Return the next :class:`~scrapy.Request` to send or ``None`` if
        there are no requests to be sent.

        .. note:: Returning ``None`` does not prevent future calls to this
            method. See :meth:`has_pending_requests`.
        """
        raise NotImplementedError

    @abstractmethod
    def has_pending_requests(self) -> bool:
        """Return ``True`` if there are pending requests or ``False``
        otherwise.

        It is OK to return ``True`` even is the next call to
        :meth:`next_request` returns ``None``.

        .. tip:: If you do this with the goal of feeding your crawl *start*
            requests from a slow resource, like a network service, instead of a
            custom scheduler, consider writing a :ref:`spider middleware
            <topics-spider-middleware>` that implements
            :meth:`~scrapy.spidermiddlewares.SpiderMiddleware.process_start`.

        .. warning:: The crawl will continue running as long as this method
            returns ``True``.
        """
        raise NotImplementedError

    def open(self, spider: Spider) -> Deferred[None] | None:
        """Called after the spider opens.

        Useful for initialization code that needs to run later than the
        ``__init__`` method, e.g. once the iteration of the
        :meth:`~scrapy.Spider.start` method has started.

        May return a :class:`~twisted.internet.defer.Deferred`.
        """

    def close(self, reason: str) -> Deferred[None] | None:
        """Called after the spider closes due to *reason* (see
        :exc:`~scrapy.exceptions.CloseSpider`).

        Useful for cleanup code.

        May return a :class:`~twisted.internet.defer.Deferred`.
        """


class Scheduler(BaseScheduler):
    """Default :ref:`scheduler <topics-scheduler>`.

    Requests are stored in memory by default. Set :setting:`JOBDIR` to switch
    to disk storage.

    Requests are dropped if :attr:`~scrapy.Request.dont_filter` is ``False``
    and :setting:`DUPEFILTER_CLASS` flags them as duplicate requests.

    :setting:`SCHEDULER_PRIORITY_QUEUE` handles request prioritization.

    The following stats are generated:

    .. code-block:: none

        scheduler/enqueued
        scheduler/enqueued/memory
        scheduler/enqueued/disk
        scheduler/dequeued
        scheduler/dequeued/memory
        scheduler/dequeued/disk
        scheduler/unserializable

    If the value of the ``scheduler/unserializable`` stat is non-zero, consider
    enabling :setting:`SCHEDULER_DEBUG` to log a warning message with details
    about the first unserializable request, to try and figure out how to make
    it serializable.

    .. seealso:: :ref:`topics-jobs`
    """

    def __init__(
        self,
        dupefilter: BaseDupeFilter,
        jobdir: str | None = None,
        dqclass: type[BaseQueue] | None = None,
        mqclass: type[BaseQueue] | None = None,
        logunser: bool = False,
        stats: StatsCollector | None = None,
        pqclass: type[PriorityQueueProtocol] | None = None,
        crawler: Crawler | None = None,
    ):
        self.df: BaseDupeFilter = dupefilter
        self.dqdir: str | None = self._dqdir(jobdir)
        self.pqclass: type[PriorityQueueProtocol] | None = pqclass
        self.dqclass: type[BaseQueue] | None = dqclass
        self.mqclass: type[BaseQueue] | None = mqclass
        self.logunser: bool = logunser
        self.stats: StatsCollector | None = stats
        self.crawler: Crawler | None = crawler
        self._paused = False

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

    def has_pending_requests(self) -> bool:
        return len(self) > 0

    def open(self, spider: Spider) -> Deferred[None] | None:
        self.spider: Spider = spider
        self.mqs: PriorityQueueProtocol = self._mq()
        self.dqs: PriorityQueueProtocol | None = self._dq() if self.dqdir else None
        return self.df.open()

    def close(self, reason: str) -> Deferred[None] | None:
        if self.dqs is not None:
            state = self.dqs.close()
            assert isinstance(self.dqdir, str)
            self._write_dqs_state(self.dqdir, state)
        return self.df.close(reason)

    def enqueue_request(self, request: Request) -> bool:
        if not request.dont_filter and self.df.request_seen(request):
            self.df.log(request, self.spider)
            return False
        dqok = self._dqpush(request)
        assert self.stats is not None
        if dqok:
            self.stats.inc_value("scheduler/enqueued/disk", spider=self.spider)
        else:
            self._mqpush(request)
            self.stats.inc_value("scheduler/enqueued/memory", spider=self.spider)
        self.stats.inc_value("scheduler/enqueued", spider=self.spider)
        return True

    def next_request(self) -> Request | None:
        if self._paused:
            return None
        request: Request | None = self.mqs.pop()
        assert self.stats is not None
        if request is not None:
            self.stats.inc_value("scheduler/dequeued/memory", spider=self.spider)
        else:
            request = self._dqpop()
            if request is not None:
                self.stats.inc_value("scheduler/dequeued/disk", spider=self.spider)
        if request is not None:
            self.stats.inc_value("scheduler/dequeued", spider=self.spider)
        return request

    def __len__(self) -> int:
        """Return the number of pending requests."""
        return len(self.dqs) + len(self.mqs) if self.dqs is not None else len(self.mqs)

    def pause(self) -> None:
        """Stop sending pending requests.

        It does not affect enqueing.

        See :ref:`start-requests-front-load` for an example.
        """
        self._paused = True

    def unpause(self) -> None:
        """Resume sending pending requests."""
        self._paused = False

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
            self.stats.inc_value("scheduler/unserializable", spider=self.spider)
            return False
        return True

    def _mqpush(self, request: Request) -> None:
        self.mqs.push(request)

    def _dqpop(self) -> Request | None:
        if self.dqs is not None:
            return self.dqs.pop()
        return None

    def _mq(self) -> PriorityQueueProtocol:
        """Create a new priority queue instance, with in-memory storage"""
        assert self.crawler
        assert self.pqclass
        return build_from_crawler(
            self.pqclass,
            self.crawler,
            downstream_queue_cls=self.mqclass,
            key="",
        )

    def _dq(self) -> PriorityQueueProtocol:
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
            return []
        with path.open(encoding="utf-8") as f:
            return cast(Any, json.load(f))

    def _write_dqs_state(self, dqdir: str, state: Any) -> None:
        with Path(dqdir, "active.json").open("w", encoding="utf-8") as f:
            json.dump(state, f)
