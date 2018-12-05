import hashlib
import logging
from six import text_type
from six.moves.urllib.parse import urlparse

from queuelib import PriorityQueue

from scrapy.core.downloader import Downloader
from scrapy.http import Request
from scrapy.signals import request_reached_downloader, response_downloaded


logger = logging.getLogger(__name__)


SCHEDULER_SLOT_META_KEY = Downloader.DOWNLOAD_SLOT


def _get_from_request(request, key, default=None):
    if isinstance(request, dict):
        return request.get(key, default)

    if isinstance(request, Request):
        return getattr(request, key, default)

    raise ValueError('Bad type of request "%s"' % (request.__class__, ))


def _scheduler_slot_read(request, default=None):
    meta = _get_from_request(request, 'meta', dict())
    slot = meta.get(SCHEDULER_SLOT_META_KEY, default)
    return slot


def _scheduler_slot_write(request, slot):
    meta = _get_from_request(request, 'meta', None)
    if not isinstance(meta, dict):
        raise ValueError('No meta attribute in %s' % (request, ))
    meta[SCHEDULER_SLOT_META_KEY] = slot


def _scheduler_slot(request):

    slot = _scheduler_slot_read(request, None)
    if slot is None:
        url = _get_from_request(request, 'url')
        slot = urlparse(url).hostname or ''
        _scheduler_slot_write(request, slot)

    return slot


def _pathable(x):
    pathable_slot = "".join([c if c.isalnum() or c in '-._' else '_' for c in x])

    """
        as we replace some letters we can get collision for different slots
        add we add unique part
    """
    unique_slot = hashlib.md5(x.encode('utf8')).hexdigest()

    return '-'.join([pathable_slot, unique_slot])


class PrioritySlot:
    __slots__ = ('priority', 'slot')

    def __init__(self, priority=0, slot=None):
        self.priority = priority
        self.slot = slot

    def __hash__(self):
        return hash((self.priority, self.slot))

    def __eq__(self, other):
        return (self.priority, self.slot) == (other.priority, other.slot)

    def __lt__(self, other):
        return (self.priority, self.slot) < (other.priority, other.slot)

    def __str__(self):
        return '_'.join([text_type(self.priority),
                         _pathable(text_type(self.slot))])


class PriorityAsTupleQueue(PriorityQueue):
    """
        Python structures is not directly (de)serialized (to)from json.
        We need this modified queue to transform custom structure (from)to
        json serializable structures
    """
    def __init__(self, qfactory, startprios=()):

        super(PriorityAsTupleQueue, self).__init__(
                qfactory,
                [PrioritySlot(priority=p[0], slot=p[1]) for p in startprios]
                )

    def close(self):
        startprios = super(PriorityAsTupleQueue, self).close()
        return [(s.priority, s.slot) for s in startprios]

    def is_empty(self):
        return not self.queues or len(self) == 0


class SlotBasedPriorityQueue(object):

    def __init__(self, qfactory, startprios={}):
        self.pqueues = dict()     # slot -> priority queue
        self.qfactory = qfactory  # factory for creating new internal queues

        if not startprios:
            return

        if not isinstance(startprios, dict):
            raise ValueError("Looks like your priorities file malforfemed. "
                             "Possible reason: You run scrapy with previous "
                             "version. Interrupted it. Updated scrapy. And "
                             "run again.")

        for slot, prios in startprios.items():
            self.pqueues[slot] = PriorityAsTupleQueue(self.qfactory, prios)

    def pop_slot(self, slot):
        queue = self.pqueues[slot]
        request = queue.pop()
        is_empty = queue.is_empty()
        if is_empty:
            del self.pqueues[slot]

        return request, is_empty

    def push_slot(self, request, priority):
        slot = _scheduler_slot(request)
        is_new = False
        if slot not in self.pqueues:
            self.pqueues[slot] = PriorityAsTupleQueue(self.qfactory)
        queue = self.pqueues[slot]
        is_new = queue.is_empty()
        queue.push(request, PrioritySlot(priority=priority, slot=slot))
        return slot, is_new

    def close(self):
        startprios = dict()
        for slot, queue in self.pqueues.items():
            prios = queue.close()
            startprios[slot] = prios
        self.pqueues.clear()
        return startprios

    def __len__(self):
        return sum(len(x) for x in self.pqueues.values()) if self.pqueues else 0


class DownloaderAwarePriorityQueue(SlotBasedPriorityQueue):

    _DOWNLOADER_AWARE_PQ_ID = 'DOWNLOADER_AWARE_PQ_ID'

    @classmethod
    def from_crawler(cls, crawler, qfactory, startprios={}):
        return cls(crawler, qfactory, startprios)

    def __init__(self, crawler, qfactory, startprios={}):
        super(DownloaderAwarePriorityQueue, self).__init__(qfactory,
                                                           startprios)
        self._slots = {slot: 0 for slot in self.pqueues}
        crawler.signals.connect(self.on_response_download,
                                signal=response_downloaded)
        crawler.signals.connect(self.on_request_reached_downloader,
                                signal=request_reached_downloader)

    def mark(self, request):
        meta = _get_from_request(request, 'meta', None)
        if not isinstance(meta, dict):
            raise ValueError('No meta attribute in %s' % (request, ))
        meta[self._DOWNLOADER_AWARE_PQ_ID] = id(self)

    def check_mark(self, request):
        return request.meta.get(self._DOWNLOADER_AWARE_PQ_ID, None) == id(self)

    def pop(self):
        slots = [(d, s) for s, d in self._slots.items() if s in self.pqueues]

        if not slots:
            return

        slot = min(slots)[1]
        request, _ = self.pop_slot(slot)
        self.mark(request)
        return request

    def push(self, request, priority):
        slot, _ = self.push_slot(request, priority)
        if slot not in self._slots:
            self._slots[slot] = 0

    def on_response_download(self, response, request, spider):
        if not self.check_mark(request):
            return

        slot = _scheduler_slot_read(request)
        if slot not in self._slots or self._slots[slot] <= 0:
            raise ValueError('Get response for wrong slot "%s"' % (slot, ))
        self._slots[slot] = self._slots[slot] - 1
        if self._slots[slot] == 0 and slot not in self.pqueues:
            del self._slots[slot]

    def on_request_reached_downloader(self, request, spider):
        if not self.check_mark(request):
            return

        slot = _scheduler_slot_read(request)
        self._slots[slot] = self._slots.get(slot, 0) + 1

    def close(self):
        self._slots.clear()
        return super(DownloaderAwarePriorityQueue, self).close()
