import hashlib
import logging
from collections import namedtuple

from queuelib import PriorityQueue

from scrapy.utils.reqser import request_to_dict, request_from_dict


logger = logging.getLogger(__name__)


def _path_safe(text):
    """
    Return a filesystem-safe version of a string ``text``

    >>> _path_safe('simple.org').startswith('simple.org')
    True
    >>> _path_safe('dash-underscore_.org').startswith('dash-underscore_.org')
    True
    >>> _path_safe('some@symbol?').startswith('some_symbol_')
    True
    """
    pathable_slot = "".join([c if c.isalnum() or c in '-._' else '_'
                             for c in text])
    # as we replace some letters we can get collision for different slots
    # add we add unique part
    unique_slot = hashlib.md5(text.encode('utf8')).hexdigest()
    return '-'.join([pathable_slot, unique_slot])


class _Priority(namedtuple("_Priority", ["priority", "slot"])):
    """ Slot-specific priority. It is a hack - ``(priority, slot)`` tuple
    which can be used instead of int priorities in queues:

    * they are ordered in the same way - order is still by priority value,
      min(prios) works;
    * str(p) representation is guaranteed to be different when slots
      are different - this is important because str(p) is used to create
      queue files on disk;
    * they have readable str(p) representation which is safe
      to use as a file name.
    """
    __slots__ = ()

    def __str__(self):
        return '%s_%s' % (self.priority, _path_safe(str(self.slot)))


class _SlotPriorityQueues(object):
    """ Container for multiple priority queues. """
    def __init__(self, pqfactory, slot_startprios=None):
        """
        ``pqfactory`` is a factory for creating new PriorityQueues.
        It must be a function which accepts a single optional ``startprios``
        argument, with a list of priorities to create queues for.

        ``slot_startprios`` is a ``{slot: startprios}`` dict.
        """
        self.pqfactory = pqfactory
        self.pqueues = {}  # slot -> priority queue
        for slot, startprios in (slot_startprios or {}).items():
            self.pqueues[slot] = self.pqfactory(startprios)

    def pop_slot(self, slot):
        """ Pop an object from a priority queue for this slot """
        queue = self.pqueues[slot]
        request = queue.pop()
        if len(queue) == 0:
            del self.pqueues[slot]
        return request

    def push_slot(self, slot, obj, priority):
        """ Push an object to a priority queue for this slot """
        if slot not in self.pqueues:
            self.pqueues[slot] = self.pqfactory()
        queue = self.pqueues[slot]
        queue.push(obj, priority)

    def close(self):
        active = {slot: queue.close()
                  for slot, queue in self.pqueues.items()}
        self.pqueues.clear()
        return active

    def __len__(self):
        return sum(len(x) for x in self.pqueues.values()) if self.pqueues else 0

    def __contains__(self, slot):
        return slot in self.pqueues


class ScrapyPriorityQueue(object):

    @classmethod
    def from_crawler(cls, crawler, downstream_queue_cls, key, startprios=()):
        return cls(crawler, downstream_queue_cls, key, startprios)

    def __init__(self, crawler, downstream_queue_cls, key, startprios=()):
        self.crawler = crawler
        self.downstream_queue_cls = downstream_queue_cls
        self.key = key
        self.queues = {}
        self.curprio = None
        self.read_prios(startprios)

    def read_prios(self, startprios):
        if not startprios:
            return

        for priority, state in startprios.items():
            priority = int(priority)
            self.queues[priority] = self.qfactory(priority, state)

        self.curprio = min(int(p) for p in startprios)

    def qfactory(self, key, startprios=()):
        return self.downstream_queue_cls(self.crawler,
                                         self.key + '/' + str(key),
                                         startprios)

    def push(self, obj, priority=0):
        if priority not in self.queues:
            self.queues[priority] = self.qfactory(priority)
        q = self.queues[priority]
        q.push(obj) # this may fail (eg. serialization error)
        if self.curprio is None or priority < self.curprio:
            self.curprio = priority

    def pop(self):
        if self.curprio is None:
            return
        q = self.queues[self.curprio]
        m = q.pop()
        if len(q) == 0:
            del self.queues[self.curprio]
            q.close()
            prios = [p for p, q in self.queues.items() if len(q) > 0]
            self.curprio = min(prios) if prios else None
        return m

    def close(self):
        active = {}
        for p, q in self.queues.items():
            active[str(p)] = q.close()
        return active

    def __len__(self):
        return sum(len(x) for x in self.queues.values()) if self.queues else 0


class DownloaderInterface(object):

    def __init__(self, crawler):
        self.downloader = crawler.engine.downloader

    def stats(self, possible_slots):
        return [(self._active_downloads(slot), slot)
                for slot in possible_slots]

    def get_slot_key(self, request):
        return self.downloader._get_slot_key(request, None)

    def _active_downloads(self, slot):
        """ Return a number of requests in a Downloader for a given slot """
        if slot not in self.downloader.slots:
            return 0
        return len(self.downloader.slots[slot].active)


class DownloaderAwarePriorityQueue(object):
    """ PriorityQueue which takes Downlaoder activity in account:
    domains (slots) with the least amount of active downloads are dequeued
    first.
    """

    @classmethod
    def from_crawler(cls, crawler, qfactory, slot_startprios=None):
        return cls(crawler, qfactory, slot_startprios)

    def __init__(self, crawler, qfactory, slot_startprios=None):
        if crawler.settings.getint('CONCURRENT_REQUESTS_PER_IP') != 0:
            raise ValueError('"%s" does not support CONCURRENT_REQUESTS_PER_IP'
                             % (self.__class__,))

        if slot_startprios and not isinstance(slot_startprios, dict):
            raise ValueError("DownloaderAwarePriorityQueue accepts "
                             "``slot_startprios`` as a dict; %r instance "
                             "is passed. Most likely, it means the state is"
                             "created by an incompatible priority queue. "
                             "Only a crawl started with the same priority "
                             "queue class can be resumed." %
                             slot_startprios.__class__)

        slot_startprios = {
            slot: [_Priority(p, slot) for p in startprios]
            for slot, startprios in (slot_startprios or {}).items()}

        def pqfactory(startprios=()):
            return ScrapyPriorityQueue(qfactory, startprios)
        self._slot_pqueues = _SlotPriorityQueues(pqfactory, slot_startprios)
        self._downloader_interface = DownloaderInterface(crawler)

    def pop(self):
        stats = self._downloader_interface.stats(self._slot_pqueues.pqueues)

        if not stats:
            return

        slot = min(stats)[1]
        request = self._slot_pqueues.pop_slot(slot)
        return request

    def push(self, request, priority):
        slot = self._downloader_interface.get_slot_key(request)
        priority_slot = _Priority(priority=priority, slot=slot)
        self._slot_pqueues.push_slot(slot, request, priority_slot)

    def close(self):
        active = self._slot_pqueues.close()
        return {slot: [p.priority for p in startprios]
                for slot, startprios in active.items()}

    def __len__(self):
        return len(self._slot_pqueues)
