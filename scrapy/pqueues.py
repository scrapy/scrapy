import hashlib
import logging
from collections import namedtuple
from six.moves.urllib.parse import urlparse

from queuelib import PriorityQueue

from scrapy.core.downloader import Downloader
from scrapy.http import Request
from scrapy.signals import request_reached_downloader, response_downloaded
from scrapy.utils.httpobj import urlparse_cached


logger = logging.getLogger(__name__)


SCHEDULER_SLOT_META_KEY = Downloader.DOWNLOAD_SLOT


def _get_request_meta(request):
    if isinstance(request, dict):
        return request.setdefault('meta', {})

    if isinstance(request, Request):
        return request.meta

    raise ValueError('Bad type of request "%s"' % (request.__class__, ))


def _scheduler_slot_read(request, default=None):
    return request.meta.get(SCHEDULER_SLOT_META_KEY, default)


def _scheduler_slot_write(request, slot):
    request.meta[SCHEDULER_SLOT_META_KEY] = slot


def _set_scheduler_slot(request):
    meta = _get_request_meta(request)
    slot = meta.get(SCHEDULER_SLOT_META_KEY, None)

    if slot is not None:
        return slot

    if isinstance(request, dict):
        url = request.get('url', None)
        slot = urlparse(url).hostname or ''
    elif isinstance(request, Request):
        slot = urlparse_cached(request).hostname or ''

    meta[SCHEDULER_SLOT_META_KEY] = slot
    return slot


def _path_safe(text):
    """ Return a filesystem-safe version of a string ``text`` """
    pathable_slot = "".join([c if c.isalnum() or c in '-._' else '_'
                             for c in text])
    # as we replace some letters we can get collision for different slots
    # add we add unique part
    unique_slot = hashlib.md5(text.encode('utf8')).hexdigest()
    return '-'.join([pathable_slot, unique_slot])


class PrioritySlot(namedtuple("PrioritySlot", ["priority", "slot"])):
    """ ``(priority, slot)`` tuple which uses a path-safe slot name
    when converting to str """
    __slots__ = ()

    def __str__(self):
        return '%s_%s' % (self.priority, _path_safe(str(self.slot)))


class PriorityAsTupleQueue(PriorityQueue):
    """
    Python structures is not directly (de)serialized (to)from json.
    We need this modified queue to transform custom structure (from)to
    json serializable structures
    """
    def __init__(self, qfactory, startprios=()):
        startprios = [PrioritySlot(priority=p[0], slot=p[1])
                      for p in startprios]
        super(PriorityAsTupleQueue, self).__init__(
            qfactory=qfactory,
            startprios=startprios)


class SlotPriorityQueues(object):
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


class DownloaderAwarePriorityQueue(object):

    _DOWNLOADER_AWARE_PQ_ID = 'DOWNLOADER_AWARE_PQ_ID'

    @classmethod
    def from_crawler(cls, crawler, qfactory, startprios=None):
        return cls(crawler, qfactory, startprios)

    def __init__(self, crawler, qfactory, startprios=None):
        ip_concurrency_key = 'CONCURRENT_REQUESTS_PER_IP'
        ip_concurrency = crawler.settings.getint(ip_concurrency_key, 0)

        if ip_concurrency > 0:
            raise ValueError('"%s" does not support %s=%d' % (self.__class__,
                                                              ip_concurrency_key,
                                                              ip_concurrency))

        def pqfactory(startprios=()):
            return PriorityAsTupleQueue(qfactory, startprios)

        if startprios and not isinstance(startprios, dict):
            raise ValueError("DownloaderAwarePriorityQueue accepts "
                             "``startprios`` as a dict; %r instance is passed."
                             " Only a crawl started with the same priority "
                             "queue class can be resumed." % startprios.__class__)
        self._slot_pqueues = SlotPriorityQueues(pqfactory,
                                                slot_startprios=startprios)

        self._active_downloads = {slot: 0 for slot in self._slot_pqueues.pqueues}
        crawler.signals.connect(self.on_response_download,
                                signal=response_downloaded)
        crawler.signals.connect(self.on_request_reached_downloader,
                                signal=request_reached_downloader)

    def mark(self, request):
        meta = _get_request_meta(request)
        if not isinstance(meta, dict):
            raise ValueError('No meta attribute in %s' % (request, ))
        meta[self._DOWNLOADER_AWARE_PQ_ID] = id(self)

    def check_mark(self, request):
        return request.meta.get(self._DOWNLOADER_AWARE_PQ_ID, None) == id(self)

    def pop(self):
        slots = [(active_downloads, slot)
                 for slot, active_downloads in self._active_downloads.items()
                 if slot in self._slot_pqueues]

        if not slots:
            return

        slot = min(slots)[1]
        request = self._slot_pqueues.pop_slot(slot)
        self.mark(request)
        return request

    def push(self, request, priority):
        slot = _set_scheduler_slot(request)
        priority_slot = PrioritySlot(priority=priority, slot=slot)
        self._slot_pqueues.push_slot(slot, request, priority_slot)
        if slot not in self._active_downloads:
            self._active_downloads[slot] = 0

    def on_response_download(self, response, request, spider):
        if not self.check_mark(request):
            return

        slot = _scheduler_slot_read(request)
        if slot not in self._active_downloads or self._active_downloads[slot] <= 0:
            raise ValueError('Get response for wrong slot "%s"' % (slot, ))
        self._active_downloads[slot] = self._active_downloads[slot] - 1
        if self._active_downloads[slot] == 0 and slot not in self._slot_pqueues:
            del self._active_downloads[slot]

    def on_request_reached_downloader(self, request, spider):
        if not self.check_mark(request):
            return

        slot = _scheduler_slot_read(request)
        self._active_downloads[slot] = self._active_downloads.get(slot, 0) + 1

    def close(self):
        self._active_downloads.clear()
        return self._slot_pqueues.close()

    def __len__(self):
        return len(self._slot_pqueues)
