from __future__ import with_statement

import os
from os.path import join, exists

from scrapy.utils.pqueue import PriorityQueue
from scrapy.utils.reqser import request_to_dict, request_from_dict
from scrapy.utils.misc import load_object
from scrapy.utils.job import job_dir
from scrapy.utils.py26 import json
from scrapy.stats import stats
from scrapy import log

class Scheduler(object):

    def __init__(self, dupefilter, jobdir=None, dqclass=None, mqclass=None, logunser=False):
        self.df = dupefilter
        self.dqdir = self._dqdir(jobdir)
        self.dqclass = dqclass
        self.mqclass = mqclass
        self.logunser = logunser

    @classmethod
    def from_settings(cls, settings):
        dupefilter_cls = load_object(settings['DUPEFILTER_CLASS'])
        dupefilter = dupefilter_cls.from_settings(settings)
        dqclass = load_object(settings['SCHEDULER_DISK_QUEUE'])
        mqclass = load_object(settings['SCHEDULER_MEMORY_QUEUE'])
        logunser = settings.getbool('LOG_UNSERIALIZABLE_REQUESTS')
        return cls(dupefilter, job_dir(settings), dqclass, mqclass, logunser)

    def has_pending_requests(self):
        return len(self) > 0

    def open(self, spider):
        self.spider = spider
        self.mqs = PriorityQueue(self._newmq)
        self.dqs = self._dq() if self.dqdir else None
        return self.df.open()

    def close(self, reason):
        if self.dqs:
            prios = self.dqs.close()
            with open(join(self.dqdir, 'active.json'), 'w') as f:
                json.dump(prios, f)
        return self.df.close(reason)

    def enqueue_request(self, request):
        if not request.dont_filter and self.df.request_seen(request):
            return
        if not self._dqpush(request):
            self._mqpush(request)

    def next_request(self):
        return self.mqs.pop() or self._dqpop()

    def __len__(self):
        return len(self.dqs) + len(self.mqs) if self.dqs else len(self.mqs)

    def _dqpush(self, request):
        if self.dqs is None:
            return
        try:
            reqd = request_to_dict(request, self.spider)
            self.dqs.push(reqd, -request.priority)
        except ValueError, e: # non serializable request
            if self.logunser:
                log.msg("Unable to serialize request: %s - reason: %s" % \
                    (request, str(e)), level=log.ERROR, spider=self.spider)
            return
        else:
            stats.inc_value('scheduler/disk_enqueued', spider=self.spider)
            return True

    def _mqpush(self, request):
        stats.inc_value('scheduler/memory_enqueued', spider=self.spider)
        self.mqs.push(request, -request.priority)

    def _dqpop(self):
        if self.dqs:
            d = self.dqs.pop()
            if d:
                return request_from_dict(d, self.spider)

    def _newmq(self, priority):
        return self.mqclass()

    def _newdq(self, priority):
        return self.dqclass(join(self.dqdir, 'p%s' % priority))

    def _dq(self):
        activef = join(self.dqdir, 'active.json')
        if exists(activef):
            with open(activef) as f:
                prios = json.load(f)
        else:
            prios = ()
        q = PriorityQueue(self._newdq, startprios=prios)
        if q:
            log.msg("Resuming crawl (%d requests scheduled)" % len(q), \
                spider=self.spider)
        return q

    def _dqdir(self, jobdir):
        if jobdir:
            dqdir = join(jobdir, 'requests.queue')
            if not exists(dqdir):
                os.makedirs(dqdir)
            return dqdir
