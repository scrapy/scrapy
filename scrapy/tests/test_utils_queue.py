import os, glob
from twisted.trial import unittest

from scrapy.utils.queue import FifoMemoryQueue, LifoMemoryQueue, FifoDiskQueue, LifoDiskQueue

class FifoMemoryQueueTest(unittest.TestCase):

    def queue(self):
        return FifoMemoryQueue()

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


class LifoMemoryQueueTest(unittest.TestCase):

    def queue(self):
        return LifoMemoryQueue()

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
        self.assertEqual(q.pop(), 'c')
        self.assertEqual(q.pop(), 'b')
        self.assertEqual(q.pop(), 'a')
        self.assertEqual(q.pop(), None)

    def test_push_pop2(self):
        """Test interleaved push and pops"""
        q = self.queue()
        q.push('a')
        q.push('b')
        q.push('c')
        q.push('d')
        self.assertEqual(q.pop(), 'd')
        self.assertEqual(q.pop(), 'c')
        q.push('e')
        self.assertEqual(q.pop(), 'e')
        self.assertEqual(q.pop(), 'b')
        self.assertEqual(q.pop(), 'a')

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


class FifoDiskQueueTest(FifoMemoryQueueTest):

    chunksize = 100000

    def setUp(self):
        self.qdir = self.mktemp()

    def queue(self):
        return FifoDiskQueue(self.qdir, chunksize=self.chunksize)

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


class ChunkSize1FifoDiskQueueTest(FifoDiskQueueTest):
    chunksize = 1

class ChunkSize2FifoDiskQueueTest(FifoDiskQueueTest):
    chunksize = 2

class ChunkSize3FifoDiskQueueTest(FifoDiskQueueTest):
    chunksize = 3

class ChunkSize4FifoDiskQueueTest(FifoDiskQueueTest):
    chunksize = 4


class LifoDiskQueueTest(LifoMemoryQueueTest):

    def setUp(self):
        self.path = self.mktemp()

    def queue(self):
        return LifoDiskQueue(self.path)

    def test_close_open(self):
        """Test closing and re-opening keeps state"""
        q = self.queue()
        q.push('a')
        q.push('b')
        q.push('c')
        q.push('d')
        self.assertEqual(q.pop(), 'd')
        self.assertEqual(q.pop(), 'c')
        q.close()
        del q
        q = self.queue()
        self.assertEqual(len(q), 2)
        q.push('e')
        self.assertEqual(q.pop(), 'e')
        self.assertEqual(q.pop(), 'b')
        q.close()
        del q
        q = self.queue()
        self.assertEqual(q.pop(), 'a')
        self.assertEqual(len(q), 0)

    def test_cleanup(self):
        """Test queue file is removed if queue is empty"""
        q = self.queue()
        assert os.path.exists(self.path)
        for x in range(5):
            q.push(str(x))
        for x in range(5):
            q.pop()
        q.close()
        assert not os.path.exists(self.path)

    def test_file_size_shrinks(self):
        """Test size of queue file shrinks when popping items"""
        q = self.queue()
        q.push('a')
        q.push('b')
        q.close()
        size = os.path.getsize(self.path)
        q = self.queue()
        q.pop()
        q.close()
        assert os.path.getsize(self.path), size
