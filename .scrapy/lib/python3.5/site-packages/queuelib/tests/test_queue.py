import os
import glob
import pytest

from queuelib.queue import (
    FifoMemoryQueue, LifoMemoryQueue, FifoDiskQueue, LifoDiskQueue,
    FifoSQLiteQueue, LifoSQLiteQueue,
)
from queuelib.tests import QueuelibTestCase


class BaseQueueTest(object):

    def queue(self):
        return NotImplementedError()

    def test_empty(self):
        """Empty queue test"""
        q = self.queue()
        assert q.pop() is None

    def test_single_pushpop(self):
        q = self.queue()
        q.push(b'a')
        assert q.pop() == b'a'

    def test_binary_element(self):
        elem = (
            b'\x80\x02}q\x01(U\x04bodyq\x02U\x00U\t_encodingq\x03U\x05utf-'
            b'8q\x04U\x07cookiesq\x05}q\x06U\x04metaq\x07}q\x08U\x07header'
            b'sq\t}U\x03urlq\nX\x15\x00\x00\x00file:///tmp/tmphDJYsgU\x0bd'
            b'ont_filterq\x0b\x89U\x08priorityq\x0cK\x00U\x08callbackq\rNU'
            b'\x06methodq\x0eU\x03GETq\x0fU\x07errbackq\x10Nu.'
        )
        q = self.queue()
        q.push(elem)
        assert q.pop() == elem

    def test_len(self):
        q = self.queue()
        self.assertEqual(len(q), 0)
        q.push(b'a')
        self.assertEqual(len(q), 1)
        q.push(b'b')
        q.push(b'c')
        self.assertEqual(len(q), 3)
        q.pop()
        q.pop()
        q.pop()
        self.assertEqual(len(q), 0)


class FifoTestMixin(BaseQueueTest):

    def test_push_pop1(self):
        """Basic push/pop test"""
        q = self.queue()
        q.push(b'a')
        q.push(b'b')
        q.push(b'c')
        self.assertEqual(q.pop(), b'a')
        self.assertEqual(q.pop(), b'b')
        self.assertEqual(q.pop(), b'c')
        self.assertEqual(q.pop(), None)

    def test_push_pop2(self):
        """Test interleaved push and pops"""
        q = self.queue()
        q.push(b'a')
        q.push(b'b')
        q.push(b'c')
        q.push(b'd')
        self.assertEqual(q.pop(), b'a')
        self.assertEqual(q.pop(), b'b')
        q.push(b'e')
        self.assertEqual(q.pop(), b'c')
        self.assertEqual(q.pop(), b'd')
        self.assertEqual(q.pop(), b'e')


class LifoTestMixin(BaseQueueTest):

    def test_push_pop1(self):
        """Basic push/pop test"""
        q = self.queue()
        q.push(b'a')
        q.push(b'b')
        q.push(b'c')
        self.assertEqual(q.pop(), b'c')
        self.assertEqual(q.pop(), b'b')
        self.assertEqual(q.pop(), b'a')
        self.assertEqual(q.pop(), None)

    def test_push_pop2(self):
        """Test interleaved push and pops"""
        q = self.queue()
        q.push(b'a')
        q.push(b'b')
        q.push(b'c')
        q.push(b'd')
        self.assertEqual(q.pop(), b'd')
        self.assertEqual(q.pop(), b'c')
        q.push(b'e')
        self.assertEqual(q.pop(), b'e')
        self.assertEqual(q.pop(), b'b')
        self.assertEqual(q.pop(), b'a')


class PersistentTestMixin(object):

    chunksize = 100000

    @pytest.mark.xfail(reason="Reenable once Scrapy.squeues stop"
                       " extending from queuelib testsuite")
    def test_non_bytes_raises_typeerror(self):
        q = self.queue()
        self.assertRaises(TypeError, q.push, 0)
        self.assertRaises(TypeError, q.push, u'')
        self.assertRaises(TypeError, q.push, None)
        self.assertRaises(TypeError, q.push, lambda x: x)

    def test_text_in_windows(self):
        e1 = b'\r\n'
        q = self.queue()
        q.push(e1)
        q.close()
        q = self.queue()
        e2 = q.pop()
        self.assertEqual(e1, e2)

    def test_close_open(self):
        """Test closing and re-opening keeps state"""
        q = self.queue()
        q.push(b'a')
        q.push(b'b')
        q.push(b'c')
        q.push(b'd')
        q.pop()
        q.pop()
        q.close()
        del q

        q = self.queue()
        self.assertEqual(len(q), 2)
        q.push(b'e')
        q.pop()
        q.pop()
        q.close()
        del q

        q = self.queue()
        assert q.pop() is not None
        self.assertEqual(len(q), 0)

    def test_cleanup(self):
        """Test queue dir is removed if queue is empty"""
        q = self.queue()
        values = [b'0', b'1', b'2', b'3', b'4']
        assert os.path.exists(self.qpath)
        for x in values:
            q.push(x)

        for x in values:
            q.pop()
        q.close()
        assert not os.path.exists(self.qpath)


class FifoMemoryQueueTest(FifoTestMixin, QueuelibTestCase):

    def queue(self):
        return FifoMemoryQueue()


class LifoMemoryQueueTest(LifoTestMixin, QueuelibTestCase):

    def queue(self):
        return LifoMemoryQueue()


class FifoDiskQueueTest(FifoTestMixin, PersistentTestMixin, QueuelibTestCase):

    def queue(self):
        return FifoDiskQueue(self.qpath, chunksize=self.chunksize)

    def test_chunks(self):
        """Test chunks are created and removed"""
        values = [b'0', b'1', b'2', b'3', b'4']
        q = self.queue()
        for x in values:
            q.push(x)

        chunks = glob.glob(os.path.join(self.qpath, 'q*'))
        self.assertEqual(len(chunks), 5 // self.chunksize + 1)
        for x in values:
            q.pop()

        chunks = glob.glob(os.path.join(self.qpath, 'q*'))
        self.assertEqual(len(chunks), 1)


class ChunkSize1FifoDiskQueueTest(FifoDiskQueueTest):
    chunksize = 1


class ChunkSize2FifoDiskQueueTest(FifoDiskQueueTest):
    chunksize = 2


class ChunkSize3FifoDiskQueueTest(FifoDiskQueueTest):
    chunksize = 3


class ChunkSize4FifoDiskQueueTest(FifoDiskQueueTest):
    chunksize = 4


class LifoDiskQueueTest(LifoTestMixin, PersistentTestMixin, QueuelibTestCase):

    def queue(self):
        return LifoDiskQueue(self.qpath)

    def test_file_size_shrinks(self):
        """Test size of queue file shrinks when popping items"""
        q = self.queue()
        q.push(b'a')
        q.push(b'b')
        q.close()
        size = os.path.getsize(self.qpath)
        q = self.queue()
        q.pop()
        q.close()
        assert os.path.getsize(self.qpath), size


class FifoSQLiteQueueTest(FifoTestMixin, PersistentTestMixin, QueuelibTestCase):

    def queue(self):
        return FifoSQLiteQueue(self.qpath)


class LifoSQLiteQueueTest(LifoTestMixin, PersistentTestMixin, QueuelibTestCase):

    def queue(self):
        return LifoSQLiteQueue(self.qpath)
