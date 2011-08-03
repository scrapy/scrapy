"""
Scheduler disk-based queues
"""

import marshal

from scrapy.utils.queue import DiskQueue

class MarshalDiskQueue(DiskQueue):

    def push(self, obj):
        super(MarshalDiskQueue, self).push(marshal.dumps(obj))

    def pop(self):
        return marshal.loads(super(MarshalDiskQueue, self).pop())
