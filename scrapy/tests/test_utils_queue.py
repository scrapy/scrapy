import os, glob
from twisted.trial import unittest

from scrapy.utils.queue import MemoryQueue, DiskQueue

class MemoryQueueTest(unittest.TestCase):

    def queue(self):
        return MemoryQueue()

    def test_empty(self):
        """Empty queue test"""
        q = self.queue()
        assert q.pop() is None

    def test_push_pop1(self):
        """Basic push/pop test"""
        q = self.queue()
        q.push('a')
        q.push('b')
        q.push('c')
        self.assertEqual(q.pop(), 'a')
        self.assertEqual(q.pop(), 'b')
        self.assertEqual(q.pop(), 'c')
        self.assertEqual(q.pop(), None)

    def test_push_pop2(self):
        """Test interleaved push and pops"""
        q = self.queue()
        q.push('a')
        q.push('b')
        q.push('c')
        q.push('d')
        self.assertEqual(q.pop(), 'a')
        self.assertEqual(q.pop(), 'b')
        q.push('e')
        self.assertEqual(q.pop(), 'c')
        self.assertEqual(q.pop(), 'd')
        self.assertEqual(q.pop(), 'e')

    def test_len(self):
        q = self.queue()
        self.assertEqual(len(q), 0)
        q.push('a')
        self.assertEqual(len(q), 1)
        q.push('b')
        q.push('c')
        self.assertEqual(len(q), 3)
        q.pop()
        q.pop()
        q.pop()
        self.assertEqual(len(q), 0)


class DiskQueueTest(MemoryQueueTest):

    chunksize = 100000

    def setUp(self):
        self.qdir = self.mktemp()

    def queue(self):
        return DiskQueue(self.qdir, chunksize=self.chunksize)

    def test_close_open(self):
        """Test closing and re-opening keeps state"""
        q = self.queue()
        q.push('a')
        q.push('b')
        q.push('c')
        q.push('d')
        self.assertEqual(q.pop(), 'a')
        self.assertEqual(q.pop(), 'b')
        q.close()
        del q
        q = self.queue()
        self.assertEqual(len(q), 2)
        q.push('e')
        self.assertEqual(q.pop(), 'c')
        self.assertEqual(q.pop(), 'd')
        q.close()
        del q
        q = self.queue()
        self.assertEqual(q.pop(), 'e')
        self.assertEqual(len(q), 0)

    def test_chunks(self):
        """Test chunks are created and removed"""
        q = self.queue()
        for x in range(5):
            q.push(str(x))
        chunks = glob.glob(os.path.join(self.qdir, 'q*'))
        self.assertEqual(len(chunks), 5/self.chunksize + 1)
        for x in range(5):
            q.pop()
        chunks = glob.glob(os.path.join(self.qdir, 'q*'))
        self.assertEqual(len(chunks), 1)

    def test_cleanup(self):
        """Test queue dir is removed if queue is empty"""
        q = self.queue()
        assert os.path.exists(self.qdir)
        for x in range(5):
            q.push(str(x))
        for x in range(5):
            q.pop()
        q.close()
        assert not os.path.exists(self.qdir)


class ChunkSize1DiskQueueTest(DiskQueueTest):
    chunksize = 1

class ChunkSize2DiskQueueTest(DiskQueueTest):
    chunksize = 2

class ChunkSize3DiskQueueTest(DiskQueueTest):
    chunksize = 3

class ChunkSize4DiskQueueTest(DiskQueueTest):
    chunksize = 4
