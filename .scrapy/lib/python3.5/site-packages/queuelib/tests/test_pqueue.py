import os
from queuelib.pqueue import PriorityQueue
from queuelib.queue import (
    FifoMemoryQueue, LifoMemoryQueue, FifoDiskQueue, LifoDiskQueue,
    FifoSQLiteQueue, LifoSQLiteQueue,
)
from queuelib.tests import QueuelibTestCase


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


# hack to prevent py.test from discovering base test class
class base:
    class PQueueTestBase(QueuelibTestCase):

        def setUp(self):
            QueuelibTestCase.setUp(self)
            self.q = PriorityQueue(self.qfactory)

        def qfactory(self, prio):
            raise NotImplementedError

        def test_len_nonzero(self):
            assert not self.q
            self.assertEqual(len(self.q), 0)
            self.q.push(b'a', 3)
            assert self.q
            self.q.push(b'b', 1)
            self.q.push(b'c', 2)
            self.q.push(b'd', 1)
            self.assertEqual(len(self.q), 4)
            self.q.pop()
            self.q.pop()
            self.q.pop()
            self.q.pop()
            assert not self.q
            self.assertEqual(len(self.q), 0)

        def test_close(self):
            self.q.push(b'a', 3)
            self.q.push(b'b', 1)
            self.q.push(b'c', 2)
            self.q.push(b'd', 1)
            iqueues = self.q.queues.values()
            self.assertEqual(sorted(self.q.close()), [1, 2, 3])
            assert all(q.closed for q in iqueues)

        def test_close_return_active(self):
            self.q.push(b'b', 1)
            self.q.push(b'c', 2)
            self.q.push(b'a', 3)
            self.q.pop()
            self.assertEqual(sorted(self.q.close()), [2, 3])

        def test_popped_internal_queues_closed(self):
            self.q.push(b'a', 3)
            self.q.push(b'b', 1)
            self.q.push(b'c', 2)
            p1queue = self.q.queues[1]
            self.assertEqual(self.q.pop(), b'b')
            self.q.close()
            assert p1queue.closed


class FifoTestMixin(object):

    def test_push_pop_noprio(self):
        self.q.push(b'a')
        self.q.push(b'b')
        self.q.push(b'c')
        self.assertEqual(self.q.pop(), b'a')
        self.assertEqual(self.q.pop(), b'b')
        self.assertEqual(self.q.pop(), b'c')
        self.assertEqual(self.q.pop(), None)

    def test_push_pop_prio(self):
        self.q.push(b'a', 3)
        self.q.push(b'b', 1)
        self.q.push(b'c', 2)
        self.q.push(b'd', 1)
        self.assertEqual(self.q.pop(), b'b')
        self.assertEqual(self.q.pop(), b'd')
        self.assertEqual(self.q.pop(), b'c')
        self.assertEqual(self.q.pop(), b'a')
        self.assertEqual(self.q.pop(), None)


class LifoTestMixin(object):

    def test_push_pop_noprio(self):
        self.q.push(b'a')
        self.q.push(b'b')
        self.q.push(b'c')
        self.assertEqual(self.q.pop(), b'c')
        self.assertEqual(self.q.pop(), b'b')
        self.assertEqual(self.q.pop(), b'a')
        self.assertEqual(self.q.pop(), None)

    def test_push_pop_prio(self):
        self.q.push(b'a', 3)
        self.q.push(b'b', 1)
        self.q.push(b'c', 2)
        self.q.push(b'd', 1)
        self.assertEqual(self.q.pop(), b'd')
        self.assertEqual(self.q.pop(), b'b')
        self.assertEqual(self.q.pop(), b'c')
        self.assertEqual(self.q.pop(), b'a')
        self.assertEqual(self.q.pop(), None)


class FifoMemoryPriorityQueueTest(FifoTestMixin, base.PQueueTestBase):

    def qfactory(self, prio):
        return track_closed(FifoMemoryQueue)()


class LifoMemoryPriorityQueueTest(LifoTestMixin, base.PQueueTestBase):

    def qfactory(self, prio):
        return track_closed(LifoMemoryQueue)()


class DiskTestMixin(object):

    def test_nonserializable_object_one(self):
        self.assertRaises(TypeError, self.q.push, lambda x: x, 0)
        self.assertEqual(self.q.close(), [])

    def test_nonserializable_object_many_close(self):
        self.q.push(b'a', 3)
        self.q.push(b'b', 1)
        self.assertRaises(TypeError, self.q.push, lambda x: x, 0)
        self.q.push(b'c', 2)
        self.assertEqual(self.q.pop(), b'b')
        self.assertEqual(sorted(self.q.close()), [2, 3])

    def test_nonserializable_object_many_pop(self):
        self.q.push(b'a', 3)
        self.q.push(b'b', 1)
        self.assertRaises(TypeError, self.q.push, lambda x: x, 0)
        self.q.push(b'c', 2)
        self.assertEqual(self.q.pop(), b'b')
        self.assertEqual(self.q.pop(), b'c')
        self.assertEqual(self.q.pop(), b'a')
        self.assertEqual(self.q.pop(), None)
        self.assertEqual(self.q.close(), [])

    def test_reopen_with_prio(self):
        q1 = PriorityQueue(self.qfactory)
        q1.push(b'a', 3)
        q1.push(b'b', 1)
        q1.push(b'c', 2)
        active = q1.close()
        q2 = PriorityQueue(self.qfactory, startprios=active)
        self.assertEqual(q2.pop(), b'b')
        self.assertEqual(q2.pop(), b'c')
        self.assertEqual(q2.pop(), b'a')
        self.assertEqual(q2.close(), [])


class FifoDiskPriorityQueueTest(FifoTestMixin, DiskTestMixin, base.PQueueTestBase):

    def qfactory(self, prio):
        path = os.path.join(self.qdir, str(prio))
        return track_closed(FifoDiskQueue)(path)


class LifoDiskPriorityQueueTest(LifoTestMixin, DiskTestMixin, base.PQueueTestBase):

    def qfactory(self, prio):
        path = os.path.join(self.qdir, str(prio))
        return track_closed(LifoDiskQueue)(path)


class FifoSQLitePriorityQueueTest(FifoTestMixin, DiskTestMixin, base.PQueueTestBase):

    def qfactory(self, prio):
        path = os.path.join(self.qdir, str(prio))
        return track_closed(FifoSQLiteQueue)(path)


class LifoSQLitePriorityQueueTest(LifoTestMixin, DiskTestMixin, base.PQueueTestBase):

    def qfactory(self, prio):
        path = os.path.join(self.qdir, str(prio))
        return track_closed(LifoSQLiteQueue)(path)
