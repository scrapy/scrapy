import os
import json
import logging
import warnings
from os.path import join, exists

from queuelib import PriorityQueue

from scrapy.utils.misc import load_object, create_instance
from scrapy.utils.job import job_dir
from scrapy.utils.deprecate import ScrapyDeprecationWarning


logger = logging.getLogger(__name__)


class Scheduler:
    """
    Scrapy Scheduler. It allows to enqueue requests and then get
    a next request to download. Scheduler is also handling duplication
    filtering, via dupefilter.

    Prioritization and queueing is not performed by the Scheduler.
    User sets ``priority`` field for each Request, and a PriorityQueue
    (defined by :setting:`SCHEDULER_PRIORITY_QUEUE`) uses these priorities
    to dequeue requests in a desired order.

    Scheduler uses two PriorityQueue instances, configured to work in-memory
    and on-disk (optional). When on-disk queue is present, it is used by
    default, and an in-memory queue is used as a fallback for cases where
    a disk queue can't handle a request (can't serialize it).

    :setting:`SCHEDULER_MEMORY_QUEUE` and
    :setting:`SCHEDULER_DISK_QUEUE` allow to specify lower-level queue classes
    which PriorityQueue instances would be instantiated with, to keep requests
    on disk and in memory respectively.

    Overall, Scheduler is an object which holds several PriorityQueue instances
    (in-memory and on-disk) and implements fallback logic for them.
    Also, it handles dupefilters.
    """
    def __init__(self, dupefilter, jobdir=None, dqclass=None, mqclass=None,
                 logunser=False, stats=None, pqclass=None, crawler=None):
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
        settings = crawler.settings
        dupefilter_cls = load_object(settings['DUPEFILTER_CLASS'])
        dupefilter = create_instance(dupefilter_cls, settings, crawler)
        pqclass = load_object(settings['SCHEDULER_PRIORITY_QUEUE'])
        if pqclass is PriorityQueue:
            warnings.warn("SCHEDULER_PRIORITY_QUEUE='queuelib.PriorityQueue'"
                          " is no longer supported because of API changes; "
                          "please use 'scrapy.pqueues.ScrapyPriorityQueue'",
                          ScrapyDeprecationWarning)
            from scrapy.pqueues import ScrapyPriorityQueue
            pqclass = ScrapyPriorityQueue

        dqclass = load_object(settings['SCHEDULER_DISK_QUEUE'])
        mqclass = load_object(settings['SCHEDULER_MEMORY_QUEUE'])
        logunser = settings.getbool('SCHEDULER_DEBUG')
        return cls(dupefilter, jobdir=job_dir(settings), logunser=logunser,
                   stats=crawler.stats, pqclass=pqclass, dqclass=dqclass,
                   mqclass=mqclass, crawler=crawler)

    def has_pending_requests(self):
        return len(self) > 0

    def open(self, spider):
        self.spider = spider
        self.mqs = self._mq()
        self.dqs = self._dq() if self.dqdir else None
        return self.df.open()

    def close(self, reason):
        if self.dqs:
            state = self.dqs.close()
            self._write_dqs_state(self.dqdir, state)
        return self.df.close(reason)

    def enqueue_request(self, request):
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

    def next_request(self):
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

    def __len__(self):
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
            self.stats.inc_value('scheduler/unserializable',
                                 spider=self.spider)
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
