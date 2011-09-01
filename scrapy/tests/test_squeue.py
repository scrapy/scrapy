from scrapy.tests import test_utils_queue as t
from scrapy.squeue import MarshalDiskQueue, PickleDiskQueue
from scrapy.item import Item, Field
from scrapy.http import Request
from scrapy.contrib.loader import ItemLoader

class TestItem(Item):
    name = Field()

def test_processor(x):
    return x + x

class TestLoader(ItemLoader):
    default_item_class = TestItem
    name_out = staticmethod(test_processor)

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


class PickleDiskQueueTest(t.DiskQueueTest):

    chunksize = 100000

    def queue(self):
        return PickleDiskQueue(self.qdir, chunksize=self.chunksize)

    def test_serialize(self):
        q = self.queue()
        q.push('a')
        q.push(123)
        q.push({'a': 'dict'})
        self.assertEqual(q.pop(), 'a')
        self.assertEqual(q.pop(), 123)
        self.assertEqual(q.pop(), {'a': 'dict'})

    def test_serialize_item(self):
        q = self.queue()
        i = TestItem(name='foo')
        q.push(i)
        i2 = q.pop()
        assert isinstance(i2, TestItem)
        self.assertEqual(i, i2)

    def test_serialize_loader(self):
        q = self.queue()
        l = TestLoader()
        q.push(l)
        l2 = q.pop()
        assert isinstance(l2, TestLoader)
        assert l2.default_item_class is TestItem
        self.assertEqual(l2.name_out('x'), 'xx')

    def test_serialize_request_recursive(self):
        q = self.queue()
        r = Request('http://www.example.com')
        r.meta['request'] = r
        q.push(r)
        r2 = q.pop()
        assert isinstance(r2, Request)
        self.assertEqual(r.url, r2.url)
        assert r2.meta['request'] is r2

class ChunkSize1PickleDiskQueueTest(PickleDiskQueueTest):
    chunksize = 1

class ChunkSize2PickleDiskQueueTest(PickleDiskQueueTest):
    chunksize = 2

class ChunkSize3PickleDiskQueueTest(PickleDiskQueueTest):
    chunksize = 3

class ChunkSize4PickleDiskQueueTest(PickleDiskQueueTest):
    chunksize = 4

