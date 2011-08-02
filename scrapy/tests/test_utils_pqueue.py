import unittest

from scrapy.utils.pqueue import PriorityQueue
from scrapy.utils.queue import MemoryQueue


class TestMemoryQueue(MemoryQueue):

    def __init__(self):
        super(TestMemoryQueue, self).__init__()
        self.closed = False

    def close(self):
        self.closed = True

class PriorityQueueTest(unittest.TestCase):

    def setUp(self):
        qfactory = lambda x: TestMemoryQueue()
        self.q = PriorityQueue(qfactory)

    def test_push_pop_noprio(self):
        self.q.push('a')
        self.q.push('b')
        self.q.push('c')
        self.assertEqual(self.q.pop(), 'a')
        self.assertEqual(self.q.pop(), 'b')
        self.assertEqual(self.q.pop(), 'c')
        self.assertEqual(self.q.pop(), None)

    def test_push_pop_prio(self):
        self.q.push('a', 3)
        self.q.push('b', 1)
        self.q.push('c', 2)
        self.q.push('d', 1)
        self.assertEqual(self.q.pop(), 'b')
        self.assertEqual(self.q.pop(), 'd')
        self.assertEqual(self.q.pop(), 'c')
        self.assertEqual(self.q.pop(), 'a')
        self.assertEqual(self.q.pop(), None)

    def test_len_nonzero(self):
        assert not self.q
        self.assertEqual(len(self.q), 0)
        self.q.push('a', 3)
        assert self.q
        self.q.push('b', 1)
        self.q.push('c', 2)
        self.q.push('d', 1)
        self.assertEqual(len(self.q), 4)
        self.q.pop()
        self.q.pop()
        self.q.pop()
        self.q.pop()
        assert not self.q
        self.assertEqual(len(self.q), 0)

    def test_close(self):
        self.q.push('a', 3)
        self.q.push('b', 1)
        self.q.push('c', 2)
        self.q.push('d', 1)
        iqueues = self.q.queues.values()
        self.assertEqual(sorted(self.q.close()), [1, 2, 3])
        assert all(q.closed for q in iqueues)

    def test_popped_internal_queues_closed(self):
        self.q.push('a', 3)
        self.q.push('b', 1)
        self.q.push('c', 2)
        p1queue = self.q.queues[1]
        self.assertEqual(self.q.pop(), 'b')
        self.q.close()
        assert p1queue.closed
