import hashlib
import logging

from scrapy.utils.misc import create_instance


class PriorityQueue:
    def __init__(self, downstream_queue_cls):
        self.downstream_queue_cls = downstream_queue_cls
        self.queues = {}

    def add_queue(self, key):
        self.queues[key] = create_instance(self.downstream_queue_cls, None, key)

    def push(self, request):
        priority = -request.priority

        if priority not in self.queues:
            self.add_queue(priority)

        self.queues[priority].push(request)

    def pop(self):
        if not self.queues:
            return

        queue = self.queues[min(self.queues)]
        request = queue.pop()

        if not queue:
            del self.queues[min(self.queues)]
            queue.close()

        return request

    def peek(self):
        return self.queues[min(self.queues)].peek() if self.queues else None

    def close(self):
        return [queue.close() for queue in self.queues.values()]

    def __len__(self):
        return sum([len(queue) for queue in self.queues.values()])


class DownloaderInterface:
    @staticmethod
    def _active_downloads(slot, downloader):
        # Check active downloads in a slot.
        return len(downloader.slots.get(slot, {}).active)

    @staticmethod
    def stats(pqueues, downloader):
        return [(-DownloaderInterface._active_downloads(slot, downloader), slot) for slot in pqueues]

    @staticmethod
    def get_slot_key(request, downloader):
        return downloader._get_slot_key(request, None)


class DownloaderAwarePriorityQueue:
    def __init__(self, downstream_queue_cls, *, downloader=None, slot_startprios=None):
        if downloader and downloader.settings.getint('CONCURRENT_REQUESTS_PER_IP') != 0:
            raise ValueError(f'"{self.__class__}" does not support CONCURRENT_REQUESTS_PER_IP')

        self.downstream_queue_cls = downstream_queue_cls
        self.pqueues = PriorityQueue(downstream_queue_cls)
        self.downloader_interface = DownloaderInterface()
        self.slot_startprios = slot_startprios or {}

        if downloader:
            self._copy_state(downloader)

    def _copy_state(self, downloader):
        for slot, startprios in self.slot_startprios.items():
            self.pqueues.add_queue(slot)

            for priority in startprios:
                requests = downloader.slot_requests(slot)
                for request in requests:
                    if request.priority == priority:
                        self.push(request, slot)

    def push(self, request, slot=None):
        slot = slot or self.downloader_interface.get_slot_key(request)
        self.pqueues.push(request)

    def pop(self):
        return self.pqueues.pop()

    def peek(self):
        return self.pqueues.peek()

    def close(self):
        return self.pqueues.close()

    def __len__(self):
        return len(self.pqueues)

    def __contains__(self, slot):
        return slot in self.pqueues