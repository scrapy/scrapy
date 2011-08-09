"""
Scheduler disk-based queues
"""

import marshal

from scrapy.utils.queue import DiskQueue

class MarshalDiskQueue(DiskQueue):

    def push(self, obj):
        super(MarshalDiskQueue, self).push(marshal.dumps(obj))

    def pop(self):
        s = super(MarshalDiskQueue, self).pop()
        if s:
            return marshal.loads(s)
