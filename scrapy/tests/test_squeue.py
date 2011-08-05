from scrapy.tests import test_utils_queue as t
from scrapy.squeue import MarshalDiskQueue


class MarshalDiskQueueTest(t.DiskQueueTest):

    chunksize = 100000

    def queue(self):
        return MarshalDiskQueue(self.qdir, chunksize=self.chunksize)

    def test_serialize(self):
        q = self.queue()
        q.push('a')
        q.push(123)
        q.push({'a': 'dict'})
        self.assertEqual(q.pop(), 'a')
        self.assertEqual(q.pop(), 123)
        self.assertEqual(q.pop(), {'a': 'dict'})

class ChunkSize1MarshalDiskQueueTest(MarshalDiskQueueTest):
    chunksize = 1

class ChunkSize2MarshalDiskQueueTest(MarshalDiskQueueTest):
    chunksize = 2

class ChunkSize3MarshalDiskQueueTest(MarshalDiskQueueTest):
    chunksize = 3

class ChunkSize4MarshalDiskQueueTest(MarshalDiskQueueTest):
    chunksize = 4
