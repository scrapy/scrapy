import collections

from twisted.trial import unittest

from scrapy.utils.asyncgen import as_async_generator, collect_asyncgen
from scrapy.utils.defer import deferred_f_from_coro_f
from scrapy.utils.middlewares import process_iterable_helper


def predicate1(o):
    return bool(o % 2)


def predicate2(o):
    return o < 10


def processor(o):
    return o * 2


class ProcessIterableHelperNormalTest(unittest.TestCase):

    def test_normal_in_predicate(self):
        iterable1 = iter([1, 2, 3])
        iterable2 = process_iterable_helper(iterable1, in_predicate=predicate1)
        self.assertIsInstance(iterable2, collections.abc.Iterable)
        list2 = list(iterable2)
        self.assertEqual(list2, [1, 3])

    def test_normal_out_predicate(self):
        iterable1 = iter([1, 2, 10, 3, 15])
        iterable2 = process_iterable_helper(iterable1, out_predicate=predicate2)
        self.assertIsInstance(iterable2, collections.abc.Iterable)
        list2 = list(iterable2)
        self.assertEqual(list2, [1, 2, 3])

    def test_normal_processor(self):
        iterable1 = iter([1, 2, 3])
        iterable2 = process_iterable_helper(iterable1, processor=processor)
        self.assertIsInstance(iterable2, collections.abc.Iterable)
        list2 = list(iterable2)
        self.assertEqual(list2, [2, 4, 6])

    def test_normal_combined(self):
        iterable1 = iter([1, 2, 10, 3, 6, 18, 5, 15])
        iterable2 = process_iterable_helper(iterable1, in_predicate=predicate1,
                                            out_predicate=predicate2, processor=processor)
        self.assertIsInstance(iterable2, collections.abc.Iterable)
        list2 = list(iterable2)
        self.assertEqual(list2, [2, 6])


class ProcessIterableHelperAsyncTest(unittest.TestCase):

    @deferred_f_from_coro_f
    async def test_async_in_predicate(self):
        iterable1 = as_async_generator([1, 2, 3])
        iterable2 = process_iterable_helper(iterable1, in_predicate=predicate1)
        self.assertIsInstance(iterable2, collections.abc.AsyncIterable)
        list2 = await collect_asyncgen(iterable2)
        self.assertEqual(list2, [1, 3])

    @deferred_f_from_coro_f
    async def test_async_out_predicate(self):
        iterable1 = as_async_generator([1, 2, 10, 3, 15])
        iterable2 = process_iterable_helper(iterable1, out_predicate=predicate2)
        self.assertIsInstance(iterable2, collections.abc.AsyncIterable)
        list2 = await collect_asyncgen(iterable2)
        self.assertEqual(list2, [1, 2, 3])

    @deferred_f_from_coro_f
    async def test_async_processor(self):
        iterable1 = as_async_generator([1, 2, 3])
        iterable2 = process_iterable_helper(iterable1, processor=processor)
        self.assertIsInstance(iterable2, collections.abc.AsyncIterable)
        list2 = await collect_asyncgen(iterable2)
        self.assertEqual(list2, [2, 4, 6])

    @deferred_f_from_coro_f
    async def test_async_combined(self):
        iterable1 = as_async_generator([1, 2, 10, 3, 6, 18, 5, 15])
        iterable2 = process_iterable_helper(iterable1, in_predicate=predicate1,
                                            out_predicate=predicate2, processor=processor)
        self.assertIsInstance(iterable2, collections.abc.AsyncIterable)
        list2 = await collect_asyncgen(iterable2)
        self.assertEqual(list2, [2, 6])
