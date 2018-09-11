import abc
import hashlib
import json
import logging
import os
from os.path import join, exists

from queuelib import RoundRobinQueue

from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.job import job_dir
from scrapy.utils.misc import load_object, create_instance
from scrapy.utils.reqser import request_to_dict, request_from_dict

logger = logging.getLogger(__name__)


def _make_file_safe(string):
    """
    Make string file safe but readable.
    """
    clean_string = "".join([c if c.isalnum() or c in '-._' else '_' for c in string])
    hash_string = hashlib.md5(string.encode('utf8')).hexdigest()
    return "{}-{}".format(clean_string[:40], hash_string[:10])


class BaseScheduler(object):
    __metaclass__ = abc.ABCMeta

    def __init__(self, dupefilter, jobdir=None, dqclass=None, mqclass=None,
                 logunser=False, stats=None, pqclass=None):
        self.df = dupefilter
        self.dqdir = self._dqdir(jobdir)
        self.pqclass = pqclass
        self.dqclass = dqclass
        self.mqclass = mqclass
        self.logunser = logunser
        self.stats = stats

    @classmethod
    def from_crawler(cls, crawler):
        settings = crawler.settings
        dupefilter_cls = load_object(settings['DUPEFILTER_CLASS'])
        dupefilter = create_instance(dupefilter_cls, settings, crawler)
        pqclass = load_object(settings['SCHEDULER_PRIORITY_QUEUE'])
        dqclass = load_object(settings['SCHEDULER_DISK_QUEUE'])
        mqclass = load_object(settings['SCHEDULER_MEMORY_QUEUE'])
        logunser = settings.getbool('LOG_UNSERIALIZABLE_REQUESTS', settings.getbool('SCHEDULER_DEBUG'))
        return cls(dupefilter, jobdir=job_dir(settings), logunser=logunser,
                   stats=crawler.stats, pqclass=pqclass, dqclass=dqclass, mqclass=mqclass)

    def request_key(self, request):
        return request.meta.get('scheduler_slot', self._request_key(request))

    @abc.abstractmethod
    def _request_key(self, request):
        raise NotImplementedError

    def has_pending_requests(self):
        return len(self) > 0

    def open(self, spider):
        self.spider = spider
        self.mqs = self.pqclass(self._newmq)
        self.dqs = self._dq() if self.dqdir else None
        return self.df.open()

    def close(self, reason):
        if self.dqs:
            state = self.dqs.close()
            with open(join(self.dqdir, 'active.json'), 'w') as f:
                json.dump(state, f)
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
            reqd = request_to_dict(request, self.spider)
            self.dqs.push(reqd, self.request_key(request))
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
        self.mqs.push(request, self.request_key(request))

    def _dqpop(self):
        if self.dqs:
            d = self.dqs.pop()
            if d:
                return request_from_dict(d, self.spider)

    def _newmq(self, key):
        return self.mqclass()

    @abc.abstractmethod
    def _newdq(self, key):
        raise NotImplementedError

    def _dq(self):
        statef = join(self.dqdir, 'active.json')
        if exists(statef):
            with open(statef) as f:
                state = json.load(f)
        else:
            state = ()
        q = self.pqclass(self._newdq, state)
        if q:
            logger.info("Resuming crawl (%(queuesize)d requests scheduled)",
                        {'queuesize': len(q)}, extra={'spider': self.spider})
        return q

    def _dqdir(self, jobdir):
        if jobdir:
            dqdir = join(jobdir, 'requests.queue')
            if not exists(dqdir):
                os.makedirs(dqdir)
            return dqdir


class Scheduler(BaseScheduler):
    """
    Key is the priority of the request (an integer)
    """

    def _request_key(self, request):
        return -request.priority

    def _newdq(self, key):
        return self.dqclass(join(self.dqdir, 'p%s' % key))


class RoundRobinScheduler(BaseScheduler):
    """
    Key is the domain and we round robin, choosing the new request to be from
    the domain that was requested last.  The default Scheduler sends multiple
    consecutive requests to a domain if multiple links were discovered and
    added consecutively.  This scheduler spreads those out that workload.

    Uses `RoundRobinQueue`.  The `pqclass` parameter and
    `SCHEDULER_PRIORITY_QUEUE` are ignored, and does not use priorities.
    """

    def __init__(self, dupefilter, jobdir=None, dqclass=None, mqclass=None,
                 logunser=False, stats=None, pqclass=None):
        super(RoundRobinScheduler, self).__init__(dupefilter, jobdir=jobdir, dqclass=dqclass,
                                                  mqclass=mqclass, logunser=logunser,
                                                  stats=stats, pqclass=RoundRobinQueue)

    def _request_key(self, request):
        return urlparse_cached(request).hostname or ''

    def _newdq(self, key):
        return self.dqclass(join(self.dqdir, _make_file_safe('k%s' % key)))
