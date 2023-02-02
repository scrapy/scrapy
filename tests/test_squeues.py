import pickle
import sys

from queuelib.tests import test_queue as t

from scrapy.http import Request
from scrapy.item import Field, Item
from scrapy.loader import ItemLoader
from scrapy.selector import Selector
from scrapy.squeues import (
    _MarshalFifoSerializationDiskQueue,
    _MarshalLifoSerializationDiskQueue,
    _PickleFifoSerializationDiskQueue,
    _PickleLifoSerializationDiskQueue,
)


class TestItem(Item):
    name = Field()


def _test_procesor(x):
    return x + x


class TestLoader(ItemLoader):
    default_item_class = TestItem
    name_out = staticmethod(_test_procesor)


def nonserializable_object_test(self):
    q = self.queue()
    self.assertRaises(ValueError, q.push, lambda x: x)
    # Selectors should fail (lxml.html.HtmlElement objects can't be pickled)
    sel = Selector(text="<html><body><p>some text</p></body></html>")
    self.assertRaises(ValueError, q.push, sel)


class FifoDiskQueueTestMixin:
    def test_serialize(self):
        q = self.queue()
        q.push("a")
        q.push(123)
        q.push({"a": "dict"})
        self.assertEqual(q.pop(), "a")
        self.assertEqual(q.pop(), 123)
        self.assertEqual(q.pop(), {"a": "dict"})

    test_nonserializable_object = nonserializable_object_test


class MarshalFifoDiskQueueTest(t.FifoDiskQueueTest, FifoDiskQueueTestMixin):
    chunksize = 100000

    def queue(self):
        return _MarshalFifoSerializationDiskQueue(self.qpath, chunksize=self.chunksize)


class ChunkSize1MarshalFifoDiskQueueTest(MarshalFifoDiskQueueTest):
    chunksize = 1


class ChunkSize2MarshalFifoDiskQueueTest(MarshalFifoDiskQueueTest):
    chunksize = 2


class ChunkSize3MarshalFifoDiskQueueTest(MarshalFifoDiskQueueTest):
    chunksize = 3


class ChunkSize4MarshalFifoDiskQueueTest(MarshalFifoDiskQueueTest):
    chunksize = 4


class PickleFifoDiskQueueTest(t.FifoDiskQueueTest, FifoDiskQueueTestMixin):
    chunksize = 100000

    def queue(self):
        return _PickleFifoSerializationDiskQueue(self.qpath, chunksize=self.chunksize)

    def test_serialize_item(self):
        q = self.queue()
        i = TestItem(name="foo")
        q.push(i)
        i2 = q.pop()
        assert isinstance(i2, TestItem)
        self.assertEqual(i, i2)

    def test_serialize_loader(self):
        q = self.queue()
        loader = TestLoader()
        q.push(loader)
        loader2 = q.pop()
        assert isinstance(loader2, TestLoader)
        assert loader2.default_item_class is TestItem
        self.assertEqual(loader2.name_out("x"), "xx")

    def test_serialize_request_recursive(self):
        q = self.queue()
        r = Request("http://www.example.com")
        r.meta["request"] = r
        q.push(r)
        r2 = q.pop()
        assert isinstance(r2, Request)
        self.assertEqual(r.url, r2.url)
        assert r2.meta["request"] is r2

    def test_non_pickable_object(self):
        q = self.queue()
        try:
            q.push(lambda x: x)
        except ValueError as exc:
            if hasattr(sys, "pypy_version_info"):
                self.assertIsInstance(exc.__context__, pickle.PicklingError)
            else:
                self.assertIsInstance(exc.__context__, AttributeError)
        sel = Selector(text="<html><body><p>some text</p></body></html>")
        try:
            q.push(sel)
        except ValueError as exc:
            self.assertIsInstance(exc.__context__, TypeError)


class ChunkSize1PickleFifoDiskQueueTest(PickleFifoDiskQueueTest):
    chunksize = 1


class ChunkSize2PickleFifoDiskQueueTest(PickleFifoDiskQueueTest):
    chunksize = 2


class ChunkSize3PickleFifoDiskQueueTest(PickleFifoDiskQueueTest):
    chunksize = 3


class ChunkSize4PickleFifoDiskQueueTest(PickleFifoDiskQueueTest):
    chunksize = 4


class LifoDiskQueueTestMixin:
    def test_serialize(self):
        q = self.queue()
        q.push("a")
        q.push(123)
        q.push({"a": "dict"})
        self.assertEqual(q.pop(), {"a": "dict"})
        self.assertEqual(q.pop(), 123)
        self.assertEqual(q.pop(), "a")

    test_nonserializable_object = nonserializable_object_test


class MarshalLifoDiskQueueTest(t.LifoDiskQueueTest, LifoDiskQueueTestMixin):
    def queue(self):
        return _MarshalLifoSerializationDiskQueue(self.qpath)


class PickleLifoDiskQueueTest(t.LifoDiskQueueTest, LifoDiskQueueTestMixin):
    def queue(self):
        return _PickleLifoSerializationDiskQueue(self.qpath)

    def test_serialize_item(self):
        q = self.queue()
        i = TestItem(name="foo")
        q.push(i)
        i2 = q.pop()
        assert isinstance(i2, TestItem)
        self.assertEqual(i, i2)

    def test_serialize_loader(self):
        q = self.queue()
        loader = TestLoader()
        q.push(loader)
        loader2 = q.pop()
        assert isinstance(loader2, TestLoader)
        assert loader2.default_item_class is TestItem
        self.assertEqual(loader2.name_out("x"), "xx")

    def test_serialize_request_recursive(self):
        q = self.queue()
        r = Request("http://www.example.com")
        r.meta["request"] = r
        q.push(r)
        r2 = q.pop()
        assert isinstance(r2, Request)
        self.assertEqual(r.url, r2.url)
        assert r2.meta["request"] is r2
