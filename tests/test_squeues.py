import pickle

from queuelib.tests import test_queue as t
from scrapy.squeues import (
    MarshalFifoDiskQueueNonRequest as MarshalFifoDiskQueue,
    MarshalLifoDiskQueueNonRequest as MarshalLifoDiskQueue,
    PickleFifoDiskQueueNonRequest as PickleFifoDiskQueue,
    PickleLifoDiskQueueNonRequest as PickleLifoDiskQueue
)
from scrapy.item import Item, Field
from scrapy.http import Request
from scrapy.loader import ItemLoader
from scrapy.selector import Selector


class TestItem(Item):
    name = Field()


def _test_procesor(x):
    return x + x


class TestLoader(ItemLoader):
    default_item_class = TestItem
    name_out = staticmethod(_test_procesor)


def nonserializable_object_test(self):
    q = self.queue()
    try:
        pickle.dumps(lambda x: x)
    except Exception:
        # Trigger Twisted bug #7989
        import twisted.persisted.styles  # NOQA
        self.assertRaises(ValueError, q.push, lambda x: x)
    else:
        # Use a different unpickleable object
        class A:
            pass

        a = A()
        a.__reduce__ = a.__reduce_ex__ = None
        self.assertRaises(ValueError, q.push, a)
    # Selectors should fail (lxml.html.HtmlElement objects can't be pickled)
    sel = Selector(text='<html><body><p>some text</p></body></html>')
    self.assertRaises(ValueError, q.push, sel)


class MarshalFifoDiskQueueTest(t.FifoDiskQueueTest):

    chunksize = 100000

    def queue(self):
        return MarshalFifoDiskQueue(self.qpath, chunksize=self.chunksize)

    def test_serialize(self):
        q = self.queue()
        q.push('a')
        q.push(123)
        q.push({'a': 'dict'})
        self.assertEqual(q.pop(), 'a')
        self.assertEqual(q.pop(), 123)
        self.assertEqual(q.pop(), {'a': 'dict'})

    test_nonserializable_object = nonserializable_object_test


class ChunkSize1MarshalFifoDiskQueueTest(MarshalFifoDiskQueueTest):
    chunksize = 1


class ChunkSize2MarshalFifoDiskQueueTest(MarshalFifoDiskQueueTest):
    chunksize = 2


class ChunkSize3MarshalFifoDiskQueueTest(MarshalFifoDiskQueueTest):
    chunksize = 3


class ChunkSize4MarshalFifoDiskQueueTest(MarshalFifoDiskQueueTest):
    chunksize = 4


class PickleFifoDiskQueueTest(MarshalFifoDiskQueueTest):

    chunksize = 100000

    def queue(self):
        return PickleFifoDiskQueue(self.qpath, chunksize=self.chunksize)

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


class ChunkSize1PickleFifoDiskQueueTest(PickleFifoDiskQueueTest):
    chunksize = 1


class ChunkSize2PickleFifoDiskQueueTest(PickleFifoDiskQueueTest):
    chunksize = 2


class ChunkSize3PickleFifoDiskQueueTest(PickleFifoDiskQueueTest):
    chunksize = 3


class ChunkSize4PickleFifoDiskQueueTest(PickleFifoDiskQueueTest):
    chunksize = 4


class MarshalLifoDiskQueueTest(t.LifoDiskQueueTest):

    def queue(self):
        return MarshalLifoDiskQueue(self.qpath)

    def test_serialize(self):
        q = self.queue()
        q.push('a')
        q.push(123)
        q.push({'a': 'dict'})
        self.assertEqual(q.pop(), {'a': 'dict'})
        self.assertEqual(q.pop(), 123)
        self.assertEqual(q.pop(), 'a')

    test_nonserializable_object = nonserializable_object_test


class PickleLifoDiskQueueTest(MarshalLifoDiskQueueTest):

    def queue(self):
        return PickleLifoDiskQueue(self.qpath)

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
