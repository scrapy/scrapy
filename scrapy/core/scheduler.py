import json
import logging
import os
from abc import abstractmethod
from os.path import join, exists
from typing import Optional

from twisted.internet.defer import Deferred

from scrapy.crawler import Crawler
from scrapy.http.request import Request
from scrapy.spiders import Spider
from scrapy.utils.job import job_dir
from scrapy.utils.misc import load_object, create_instance


logger = logging.getLogger(__name__)


class BaseScheduler:
    """
    The scheduler component is responsible for storing requests received from
    the engine, and feeding them back upon request (also to the engine).

    The methods defined in this class constitute the minimal
    interface that the Scrapy engine will interact with.
    """

    def open(self, spider: Spider) -> Optional[Deferred]:
        """
        Called when the spider is opened by the engine. It receives the spider
        instance as argument and it's useful to execute initialization code.

        :param spider: the spider object for the current crawl
        :type spider: :class:`~scrapy.spiders.Spider`
        """
        pass

    def close(self, reason: str) -> Optional[Deferred]:
        """
        Called when the spider is closed by the engine. It receives the reason why the crawl
        finished as argument and it's useful to execute cleaning code.

        :param reason: a string which describes the reason why the spider was closed
        :type reason: :class:`str`
        """
        pass

    @abstractmethod
    def has_pending_requests(self) -> bool:
        """
        ``True`` if the scheduler has enqueued requests, ``False`` otherwise
        """
        raise NotImplementedError()

    @abstractmethod
    def enqueue_request(self, request: Request) -> bool:
        """
        Process a request received by the engine.

        Return ``True`` if the request is to be considered scheduled, ``False`` otherwise.
        """
        raise NotImplementedError()

    @abstractmethod
    def next_request(self) -> Optional[Request]:
        """
        Return a previously enqueued request.

        Return a :class:`~scrapy.http.Request` object, or ``None`` if there are
        no more enqueued requests, i.e. if ``has_pending_requests`` is ``False``.
        """
        raise NotImplementedError()


class Scheduler(BaseScheduler):
    """
    Default Scrapy scheduler. This implementation also handles duplication
    filtering via the :setting:`dupefilter <DUPEFILTER_CLASS>`.

    Prioritization and queueing is not performed by the scheduler.
    User sets ``priority`` field for each Request, and a PriorityQueue
    (defined by :setting:`SCHEDULER_PRIORITY_QUEUE`) uses these priorities
    to dequeue requests in a desired order.

    This scheduler uses two PriorityQueue instances, configured to work in-memory
    and on-disk (optional). When on-disk queue is present, it is used by
    default, and an in-memory queue is used as a fallback for cases where
    a disk queue can't handle a request (can't serialize it).

    :setting:`SCHEDULER_MEMORY_QUEUE` and
    :setting:`SCHEDULER_DISK_QUEUE` allow to specify lower-level queue classes
    which PriorityQueue instances would be instantiated with, to keep requests
    on disk and in memory respectively.

    Overall, this scheduler is an object which holds several PriorityQueue instances
    (in-memory and on-disk) and implements fallback logic for them.
    Also, it handles dupefilters.

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
    def __init__(
        self,
        dupefilter,
        jobdir: Optional[str] = None,
        dqclass=None,
        mqclass=None,
        logunser: bool = False,
        stats=None,
        pqclass=None,
        crawler: Optional[Crawler] = None,
    ):
        self.df = dupefilter
        self.dqdir = self._dqdir(jobdir)
        self.pqclass = pqclass
        self.dqclass = dqclass
        self.mqclass = mqclass
        self.logunser = logunser
        self.stats = stats
        self.crawler = crawler

    @classmethod
    def from_crawler(cls, crawler):
        """
        Factory method, initializes the scheduler with arguments taken from the crawl settings
        """
        dupefilter_cls = load_object(crawler.settings['DUPEFILTER_CLASS'])
        return cls(
            dupefilter=create_instance(dupefilter_cls, crawler.settings, crawler),
            jobdir=job_dir(crawler.settings),
            dqclass=load_object(crawler.settings['SCHEDULER_DISK_QUEUE']),
            mqclass=load_object(crawler.settings['SCHEDULER_MEMORY_QUEUE']),
            logunser=crawler.settings.getbool('SCHEDULER_DEBUG'),
            stats=crawler.stats,
            pqclass=load_object(crawler.settings['SCHEDULER_PRIORITY_QUEUE']),
            crawler=crawler,
        )

    def has_pending_requests(self) -> bool:
        return len(self) > 0

    def open(self, spider: Spider) -> Optional[Deferred]:
        """
        (1) initialize the memory queue
        (2) initialize the disk queue if the ``jobdir`` attribute is a valid directory
        (3) return the result of the dupefilter's ``open`` method
        """
        self.spider = spider
        self.mqs = self._mq()
        self.dqs = self._dq() if self.dqdir else None
        return self.df.open()

    def close(self, reason: str) -> Optional[Deferred]:
        """
        (1) dump pending requests to disk if there is a disk queue
        (2) return the result of the dupefilter's ``close`` method
        """
        if self.dqs:
            state = self.dqs.close()
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
        if dqok:
            self.stats.inc_value('scheduler/enqueued/disk', spider=self.spider)
        else:
            self._mqpush(request)
            self.stats.inc_value('scheduler/enqueued/memory', spider=self.spider)
        self.stats.inc_value('scheduler/enqueued', spider=self.spider)
        return True

    def next_request(self) -> Optional[Request]:
        """
        Return a request from the memory queue, falling back to the disk queue if the
        memory queue is empty.

        Increment the appropriate stats, such as : ``scheduler/dequeued``,
        ``scheduler/dequeued/disk``, ``scheduler/dequeued/memory``.

        Return a :class:`~scrapy.http.Request` object, or ``None`` if there are no more enqueued requests.
        """
        request = self.mqs.pop()
        if request:
            self.stats.inc_value('scheduler/dequeued/memory', spider=self.spider)
        else:
            request = self._dqpop()
            if request:
                self.stats.inc_value('scheduler/dequeued/disk', spider=self.spider)
        if request:
            self.stats.inc_value('scheduler/dequeued', spider=self.spider)
        return request

    def __len__(self) -> int:
        """
        Return the total amount of enqueued requests
        """
        return len(self.dqs) + len(self.mqs) if self.dqs else len(self.mqs)

    def _dqpush(self, request):
        if self.dqs is None:
            return
        try:
            self.dqs.push(request)
        except ValueError as e:  # non serializable request
            if self.logunser:
                msg = ("Unable to serialize request: %(request)s - reason:"
                       " %(reason)s - no more unserializable requests will be"
                       " logged (stats being collected)")
                logger.warning(msg, {'request': request, 'reason': e},
                               exc_info=True, extra={'spider': self.spider})
                self.logunser = False
            self.stats.inc_value('scheduler/unserializable', spider=self.spider)
            return
        else:
            return True

    def _mqpush(self, request):
        self.mqs.push(request)

    def _dqpop(self):
        if self.dqs:
            return self.dqs.pop()

    def _mq(self):
        """ Create a new priority queue instance, with in-memory storage """
        return create_instance(self.pqclass,
                               settings=None,
                               crawler=self.crawler,
                               downstream_queue_cls=self.mqclass,
                               key='')

    def _dq(self):
        """ Create a new priority queue instance, with disk storage """
        state = self._read_dqs_state(self.dqdir)
        q = create_instance(self.pqclass,
                            settings=None,
                            crawler=self.crawler,
                            downstream_queue_cls=self.dqclass,
                            key=self.dqdir,
                            startprios=state)
        if q:
            logger.info("Resuming crawl (%(queuesize)d requests scheduled)",
                        {'queuesize': len(q)}, extra={'spider': self.spider})
        return q

    def _dqdir(self, jobdir):
        """ Return a folder name to keep disk queue state at """
        if jobdir:
            dqdir = join(jobdir, 'requests.queue')
            if not exists(dqdir):
                os.makedirs(dqdir)
            return dqdir

    def _read_dqs_state(self, dqdir):
        path = join(dqdir, 'active.json')
        if not exists(path):
            return ()
        with open(path) as f:
            return json.load(f)

    def _write_dqs_state(self, dqdir, state):
        with open(join(dqdir, 'active.json'), 'w') as f:
            json.dump(state, f)
