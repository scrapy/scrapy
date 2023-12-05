import os

from queuelib.rrqueue import RoundRobinQueue
from queuelib.queue import (
    FifoMemoryQueue,
    LifoMemoryQueue,
    FifoDiskQueue,
    LifoDiskQueue,
    FifoSQLiteQueue,
    LifoSQLiteQueue,
)

from queuelib.tests import QueuelibTestCase, track_closed


class RRQueueTestMixin:
    def setUp(self):
        super().setUp()
        self.q = RoundRobinQueue(self.qfactory)

    def qfactory(self, key):
        raise NotImplementedError

    def test_len_nonzero(self):
        assert not self.q
        self.assertEqual(len(self.q), 0)
        self.q.push(b"a", "3")
        assert self.q
        self.q.push(b"b", "1")
        self.q.push(b"c", "2")
        self.q.push(b"d", "1")
        self.assertEqual(len(self.q), 4)
        self.q.pop()
        self.q.pop()
        self.q.pop()
        self.q.pop()
        assert not self.q
        self.assertEqual(len(self.q), 0)

    def test_close(self):
        self.q.push(b"a", "3")
        self.q.push(b"b", "1")
        self.q.push(b"c", "2")
        self.q.push(b"d", "1")
        iqueues = self.q.queues.values()
        self.assertEqual(sorted(self.q.close()), ["1", "2", "3"])
        assert all(q.closed for q in iqueues)

    def test_close_return_active(self):
        self.q.push(b"b", "1")
        self.q.push(b"c", "2")
        self.q.push(b"a", "3")
        self.q.pop()
        self.assertEqual(sorted(self.q.close()), ["2", "3"])


class FifoTestMixin:
    def test_push_pop_peek_key(self):
        self.assertEqual(self.q.peek(), None)
        self.q.push(b"a", "1")
        self.q.push(b"b", "1")
        self.q.push(b"c", "2")
        self.q.push(b"d", "2")
        self.assertEqual(self.q.peek(), b"a")
        self.assertEqual(self.q.pop(), b"a")
        self.assertEqual(self.q.peek(), b"c")
        self.assertEqual(self.q.pop(), b"c")
        self.assertEqual(self.q.peek(), b"b")
        self.assertEqual(self.q.pop(), b"b")
        self.assertEqual(self.q.peek(), b"d")
        self.assertEqual(self.q.pop(), b"d")
        self.assertEqual(self.q.peek(), None)
        self.assertEqual(self.q.pop(), None)


class LifoTestMixin:
    def test_push_pop_peek_key(self):
        self.assertEqual(self.q.peek(), None)
        self.q.push(b"a", "1")
        self.q.push(b"b", "1")
        self.q.push(b"c", "2")
        self.q.push(b"d", "2")
        self.assertEqual(self.q.peek(), b"b")
        self.assertEqual(self.q.pop(), b"b")
        self.assertEqual(self.q.peek(), b"d")
        self.assertEqual(self.q.pop(), b"d")
        self.assertEqual(self.q.peek(), b"a")
        self.assertEqual(self.q.pop(), b"a")
        self.assertEqual(self.q.peek(), b"c")
        self.assertEqual(self.q.pop(), b"c")
        self.assertEqual(self.q.peek(), None)
        self.assertEqual(self.q.pop(), None)


class FifoMemoryRRQueueTest(RRQueueTestMixin, FifoTestMixin, QueuelibTestCase):
    def qfactory(self, key):
        return track_closed(FifoMemoryQueue)()


class LifoMemoryRRQueueTest(RRQueueTestMixin, LifoTestMixin, QueuelibTestCase):
    def qfactory(self, key):
        return track_closed(LifoMemoryQueue)()


class DiskTestMixin:
    def test_nonserializable_object_one(self):
        self.assertRaises(TypeError, self.q.push, lambda x: x, "0")
        self.assertEqual(self.q.close(), [])

    def test_nonserializable_object_many_close(self):
        self.q.push(b"a", "3")
        self.q.push(b"b", "1")
        self.assertRaises(TypeError, self.q.push, lambda x: x, "0")
        self.q.push(b"c", "2")
        self.assertEqual(self.q.pop(), b"a")
        self.assertEqual(sorted(self.q.close()), ["1", "2"])

    def test_nonserializable_object_many_pop(self):
        self.q.push(b"a", "3")
        self.q.push(b"b", "1")
        self.assertRaises(TypeError, self.q.push, lambda x: x, "0")
        self.q.push(b"c", "2")
        self.assertEqual(self.q.pop(), b"a")
        self.assertEqual(self.q.pop(), b"b")
        self.assertEqual(self.q.pop(), b"c")
        self.assertEqual(self.q.pop(), None)
        self.assertEqual(self.q.close(), [])


class FifoDiskRRQueueTest(RRQueueTestMixin, FifoTestMixin, DiskTestMixin, QueuelibTestCase):
    def qfactory(self, key):
        path = os.path.join(self.qdir, str(key))
        return track_closed(FifoDiskQueue)(path)


class LifoDiskRRQueueTest(RRQueueTestMixin, LifoTestMixin, DiskTestMixin, QueuelibTestCase):
    def qfactory(self, key):
        path = os.path.join(self.qdir, str(key))
        return track_closed(LifoDiskQueue)(path)


class FifoSQLiteRRQueueTest(RRQueueTestMixin, FifoTestMixin, DiskTestMixin, QueuelibTestCase):
    def qfactory(self, key):
        path = os.path.join(self.qdir, str(key))
        return track_closed(FifoSQLiteQueue)(path)


class LifoSQLiteRRQueueTest(RRQueueTestMixin, LifoTestMixin, DiskTestMixin, QueuelibTestCase):
    def qfactory(self, key):
        path = os.path.join(self.qdir, str(key))
        return track_closed(LifoSQLiteQueue)(path)


class RRQueueStartDomainsTestMixin:
    def setUp(self):
        super().setUp()
        self.q = RoundRobinQueue(self.qfactory, start_domains=["1", "2"])

    def qfactory(self, key):
        raise NotImplementedError

    def test_push_pop_peek_key(self):
        self.q.push(b"c", "1")
        self.q.push(b"d", "2")
        self.assertEqual(self.q.peek(), b"d")
        self.assertEqual(self.q.pop(), b"d")
        self.assertEqual(self.q.peek(), b"c")
        self.assertEqual(self.q.pop(), b"c")
        self.assertEqual(self.q.peek(), None)
        self.assertEqual(self.q.pop(), None)

    def test_push_pop_peek_key_reversed(self):
        self.q.push(b"d", "2")
        self.q.push(b"c", "1")
        self.assertEqual(self.q.peek(), b"d")
        self.assertEqual(self.q.pop(), b"d")
        self.assertEqual(self.q.peek(), b"c")
        self.assertEqual(self.q.pop(), b"c")
        self.assertEqual(self.q.peek(), None)
        self.assertEqual(self.q.pop(), None)


class FifoMemoryRRQueueStartDomainsTest(RRQueueStartDomainsTestMixin, QueuelibTestCase):
    def qfactory(self, key):
        return track_closed(FifoMemoryQueue)()


class LifoMemoryRRQueueStartDomainsTest(RRQueueStartDomainsTestMixin, QueuelibTestCase):
    def qfactory(self, key):
        return track_closed(LifoMemoryQueue)()


class FifoDiskRRQueueStartDomainsTest(RRQueueStartDomainsTestMixin, QueuelibTestCase):
    def qfactory(self, key):
        path = os.path.join(self.qdir, str(key))
        return track_closed(FifoDiskQueue)(path)


class LifoDiskRRQueueStartDomainsTest(RRQueueStartDomainsTestMixin, QueuelibTestCase):
    def qfactory(self, key):
        path = os.path.join(self.qdir, str(key))
        return track_closed(LifoDiskQueue)(path)


class FifoSQLiteRRQueueStartDomainsTest(RRQueueStartDomainsTestMixin, QueuelibTestCase):
    def qfactory(self, key):
        path = os.path.join(self.qdir, str(key))
        return track_closed(FifoSQLiteQueue)(path)


class LifoSQLiteRRQueueStartDomainsTest(RRQueueStartDomainsTestMixin, QueuelibTestCase):
    def qfactory(self, key):
        path = os.path.join(self.qdir, str(key))
        return track_closed(LifoSQLiteQueue)(path)
