from twisted.trial import unittest

from scrapy.utils.pqueue import PriorityQueue
from scrapy.utils.queue import FifoMemoryQueue, LifoMemoryQueue, FifoDiskQueue, LifoDiskQueue


def track_closed(cls):
    """Wraps a queue class to track down if close() method was called"""

    class TrackingClosed(cls):

        def __init__(self, *a, **kw):
            super(TrackingClosed, self).__init__(*a, **kw)
            self.closed = False

        def close(self):
            super(TrackingClosed, self).close()
            self.closed = True

    return TrackingClosed


class FifoMemoryPriorityQueueTest(unittest.TestCase):

    def setUp(self):
        self.q = PriorityQueue(self.qfactory)

    def qfactory(self, prio):
        return track_closed(FifoMemoryQueue)()

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

    def test_close_return_active(self):
        self.q.push('b', 1)
        self.q.push('c', 2)
        self.q.push('a', 3)
        self.q.pop()
        self.assertEqual(sorted(self.q.close()), [2, 3])

    def test_popped_internal_queues_closed(self):
        self.q.push('a', 3)
        self.q.push('b', 1)
        self.q.push('c', 2)
        p1queue = self.q.queues[1]
        self.assertEqual(self.q.pop(), 'b')
        self.q.close()
        assert p1queue.closed


class LifoMemoryPriorityQueueTest(FifoMemoryPriorityQueueTest):

    def qfactory(self, prio):
        return track_closed(LifoMemoryQueue)()

    def test_push_pop_noprio(self):
        self.q.push('a')
        self.q.push('b')
        self.q.push('c')
        self.assertEqual(self.q.pop(), 'c')
        self.assertEqual(self.q.pop(), 'b')
        self.assertEqual(self.q.pop(), 'a')
        self.assertEqual(self.q.pop(), None)

    def test_push_pop_prio(self):
        self.q.push('a', 3)
        self.q.push('b', 1)
        self.q.push('c', 2)
        self.q.push('d', 1)
        self.assertEqual(self.q.pop(), 'd')
        self.assertEqual(self.q.pop(), 'b')
        self.assertEqual(self.q.pop(), 'c')
        self.assertEqual(self.q.pop(), 'a')
        self.assertEqual(self.q.pop(), None)


class FifoDiskPriorityQueueTest(FifoMemoryPriorityQueueTest):

    def setUp(self):
        self.q = PriorityQueue(self.qfactory)

    def qfactory(self, prio):
        return track_closed(FifoDiskQueue)(self.mktemp())

    def test_nonserializable_object_one(self):
        self.assertRaises(TypeError, self.q.push, lambda x: x, 0)
        self.assertEqual(self.q.close(), [])

    def test_nonserializable_object_many_close(self):
        self.q.push('a', 3)
        self.q.push('b', 1)
        self.assertRaises(TypeError, self.q.push, lambda x: x, 0)
        self.q.push('c', 2)
        self.assertEqual(self.q.pop(), 'b')
        self.assertEqual(sorted(self.q.close()), [2, 3])

    def test_nonserializable_object_many_pop(self):
        self.q.push('a', 3)
        self.q.push('b', 1)
        self.assertRaises(TypeError, self.q.push, lambda x: x, 0)
        self.q.push('c', 2)
        self.assertEqual(self.q.pop(), 'b')
        self.assertEqual(self.q.pop(), 'c')
        self.assertEqual(self.q.pop(), 'a')
        self.assertEqual(self.q.pop(), None)
        self.assertEqual(self.q.close(), [])


class FifoDiskPriorityQueueTest(FifoMemoryPriorityQueueTest):

    def qfactory(self, prio):
        return track_closed(FifoDiskQueue)(self.mktemp())

    def test_nonserializable_object_one(self):
        self.assertRaises(TypeError, self.q.push, lambda x: x, 0)
        self.assertEqual(self.q.close(), [])

    def test_nonserializable_object_many_close(self):
        self.q.push('a', 3)
        self.q.push('b', 1)
        self.assertRaises(TypeError, self.q.push, lambda x: x, 0)
        self.q.push('c', 2)
        self.assertEqual(self.q.pop(), 'b')
        self.assertEqual(sorted(self.q.close()), [2, 3])

    def test_nonserializable_object_many_pop(self):
        self.q.push('a', 3)
        self.q.push('b', 1)
        self.assertRaises(TypeError, self.q.push, lambda x: x, 0)
        self.q.push('c', 2)
        self.assertEqual(self.q.pop(), 'b')
        self.assertEqual(self.q.pop(), 'c')
        self.assertEqual(self.q.pop(), 'a')
        self.assertEqual(self.q.pop(), None)
        self.assertEqual(self.q.close(), [])


class LifoDiskPriorityQueueTest(LifoMemoryPriorityQueueTest):

    def qfactory(self, prio):
        return track_closed(LifoDiskQueue)(self.mktemp())
