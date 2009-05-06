import copy
import unittest

from scrapy.utils.datatypes import PriorityQueue, PriorityStack, CaselessDict

# (ITEM, PRIORITY)
INPUT = [(1, -5), (30, -1), (80, -3), (4, 1), (6, 3), (20, 0), (50, -1)]

class PriorityQueueTestCase(unittest.TestCase):

    output = [(1, -5), (80, -3), (30, -1), (50, -1), (20, 0), (4, 1), (6, 3)]

    def test_popping(self):
        pq = PriorityQueue()
        for item, pr in INPUT:
            pq.push(item, pr)
        l = []
        while pq:
            l.append(pq.pop())
        self.assertEquals(l, self.output)

    def test_iter(self):
        pq = PriorityQueue()
        for item, pr in INPUT:
            pq.push(item, pr)
        result = [x for x in pq]
        self.assertEquals(result, self.output)

    def test_nonzero(self):
        pq = PriorityQueue()
        pq.push(80, -1)
        pq.push(20, 0)
        pq.push(30, 1)

        pq.pop()
        self.assertEquals(bool(pq), True)
        pq.pop()
        self.assertEquals(bool(pq), True)
        pq.pop()
        self.assertEquals(bool(pq), False)

    def test_len(self):
        pq = PriorityQueue()
        pq.push(80, -1)
        pq.push(20, 0)
        pq.push(30, 1)

        self.assertEquals(len(pq), 3)
        pq.pop()
        self.assertEquals(len(pq), 2)
        pq.pop()
        self.assertEquals(len(pq), 1)
        pq.pop()
        self.assertEquals(len(pq), 0)

class PriorityStackTestCase(unittest.TestCase):

    output = [(1, -5), (80, -3), (50, -1), (30, -1), (20, 0), (4, 1), (6, 3)]

    def test_popping(self):
        pq = PriorityStack()
        for item, pr in INPUT:
            pq.push(item, pr)
        l = []
        while pq:
            l.append(pq.pop())
        self.assertEquals(l, self.output)

    def test_iter(self):
        pq = PriorityStack()
        for item, pr in INPUT:
            pq.push(item, pr)
        result = [x for x in pq]
        self.assertEquals(result, self.output)


class CaselessDictTest(unittest.TestCase):

    def test_init(self):
        seq = {'red': 1, 'black': 3}
        d = CaselessDict(seq)
        self.assertEqual(d['red'], 1)
        self.assertEqual(d['black'], 3)

        seq = (('red', 1), ('black', 3))
        d = CaselessDict(seq)
        self.assertEqual(d['red'], 1)
        self.assertEqual(d['black'], 3)

    def test_caseless(self):
        d = CaselessDict()
        d['key_Lower'] = 1
        self.assertEqual(d['KEy_loWer'], 1)
        self.assertEqual(d.get('KEy_loWer'), 1)

        d['KEY_LOWER'] = 3
        self.assertEqual(d['key_Lower'], 3)
        self.assertEqual(d.get('key_Lower'), 3)

    def test_delete(self):
        d = CaselessDict({'key_lower': 1})
        del d['key_LOWER']
        self.assertRaises(KeyError, d.__getitem__, 'key_LOWER')
        self.assertRaises(KeyError, d.__getitem__, 'key_lower')

    def test_getdefault(self):
        d = CaselessDict()
        self.assertEqual(d.get('c', 5), 5)
        d['c'] = 10
        self.assertEqual(d.get('c', 5), 10)

    def test_setdefault(self):
        d = CaselessDict({'a': 1, 'b': 2})

        r = d.setdefault('A', 5)
        self.assertEqual(r, 1)
        self.assertEqual(d['A'], 1)

        r = d.setdefault('c', 5)
        self.assertEqual(r, 5)
        self.assertEqual(d['C'], 5)

    def test_fromkeys(self):
        keys = ('a', 'b')

        d = CaselessDict.fromkeys(keys)
        self.assertEqual(d['A'], None)
        self.assertEqual(d['B'], None)

        d = CaselessDict.fromkeys(keys, 1)
        self.assertEqual(d['A'], 1)
        self.assertEqual(d['B'], 1)

        instance = CaselessDict()
        d = instance.fromkeys(keys)
        self.assertEqual(d['A'], None)
        self.assertEqual(d['B'], None)

        d = instance.fromkeys(keys, 1)
        self.assertEqual(d['A'], 1)
        self.assertEqual(d['B'], 1)

    def test_contains(self):
        d = CaselessDict()
        d['a'] = 1
        assert 'a' in d
        assert d.has_key('a')

    def test_pop(self):
        d = CaselessDict()
        d['a'] = 1
        self.assertEqual(d.pop('A'), 1)
        self.assertRaises(KeyError, d.pop, 'A')

    def test_normkey(self):
        class MyDict(CaselessDict):
            def normkey(self, key):
                return key.title()

        d = MyDict()
        d['key-one'] = 2
        self.assertEqual(list(d.keys()), ['Key-One'])

    def test_normvalue(self):
        class MyDict(CaselessDict):
            def normvalue(self, value):
                if value is not None:
                    return value + 1

        d = MyDict({'key': 1})
        self.assertEqual(d['key'], 2)
        self.assertEqual(d.get('key'), 2)

        d = MyDict()
        d['key'] = 1
        self.assertEqual(d['key'], 2)
        self.assertEqual(d.get('key'), 2)

        d = MyDict()
        d.setdefault('key', 1)
        self.assertEqual(d['key'], 2)
        self.assertEqual(d.get('key'), 2)

        d = MyDict()
        d.update({'key': 1})
        self.assertEqual(d['key'], 2)
        self.assertEqual(d.get('key'), 2)

        d = MyDict.fromkeys(('key',), 1)
        self.assertEqual(d['key'], 2)
        self.assertEqual(d.get('key'), 2)

    def test_copy(self):
        h1 = CaselessDict({'header1': 'value'})
        h2 = copy.copy(h1)
        self.assertEqual(h1, h2)
        self.assertEqual(h1.get('header1'), h2.get('header1'))
        assert isinstance(h2, CaselessDict)


if __name__ == "__main__":
    unittest.main()

