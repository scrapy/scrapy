import unittest
from datetime import datetime
from decimal import Decimal

from scrapy.http import Request
from scrapyd.sqlite import SqlitePriorityQueue, JsonSqlitePriorityQueue, \
    PickleSqlitePriorityQueue, SqliteDict, JsonSqliteDict, PickleSqliteDict


class SqliteDictTest(unittest.TestCase):

    dict_class = SqliteDict
    test_dict = {'hello': 'world', 'int': 1, 'float': 1.5}

    def test_basic_types(self):
        test = self.test_dict
        d = self.dict_class()
        d.update(test)
        self.failUnlessEqual(d.items(), test.items())
        d.clear()
        self.failIf(d.items())

    def test_in(self):
        d = self.dict_class()
        self.assertFalse('test' in d)
        d['test'] = 123
        self.assertTrue('test' in d)

    def test_keyerror(self):
        d = self.dict_class()
        self.assertRaises(KeyError, d.__getitem__, 'test')

    def test_replace(self):
        d = self.dict_class()
        self.assertEqual(d.get('test'), None)
        d['test'] = 123
        self.assertEqual(d.get('test'), 123)
        d['test'] = 456
        self.assertEqual(d.get('test'), 456)


class JsonSqliteDictTest(SqliteDictTest):

    dict_class = JsonSqliteDict
    test_dict = SqliteDictTest.test_dict.copy()
    test_dict.update({'list': ['a', 'world'], 'dict': {'some': 'dict'}})


class PickleSqliteDictTest(JsonSqliteDictTest):

    dict_class = PickleSqliteDict
    test_dict = JsonSqliteDictTest.test_dict.copy()
    test_dict.update({'decimal': Decimal("10"), 'datetime': datetime.now()})

    def test_request_persistance(self):
        r1 = Request("http://www.example.com", body="some")
        d = self.dict_class()
        d['request'] = r1
        r2 = d['request']
        self.failUnless(isinstance(r2, Request))
        self.failUnlessEqual(r1.url, r2.url)
        self.failUnlessEqual(r1.body, r2.body)


class SqlitePriorityQueueTest(unittest.TestCase):

    queue_class = SqlitePriorityQueue

    supported_values = ["bytes", u"\xa3", 123, 1.2, True]

    def setUp(self):
        self.q = self.queue_class()

    def test_empty(self):
        self.failUnless(self.q.pop() is None)

    def test_one(self):
        msg = "a message"
        self.q.put(msg)
        self.failIf("_id" in msg)
        self.failUnlessEqual(self.q.pop(), msg)
        self.failUnless(self.q.pop() is None)

    def test_multiple(self):
        msg1 = "first message"
        msg2 = "second message"
        self.q.put(msg1)
        self.q.put(msg2)
        out = []
        out.append(self.q.pop())
        out.append(self.q.pop())
        self.failUnless(msg1 in out)
        self.failUnless(msg2 in out)
        self.failUnless(self.q.pop() is None)

    def test_priority(self):
        msg1 = "message 1"
        msg2 = "message 2"
        msg3 = "message 3"
        msg4 = "message 4"
        self.q.put(msg1, priority=1.0)
        self.q.put(msg2, priority=5.0)
        self.q.put(msg3, priority=3.0)
        self.q.put(msg4, priority=2.0)
        self.failUnlessEqual(self.q.pop(), msg2)
        self.failUnlessEqual(self.q.pop(), msg3)
        self.failUnlessEqual(self.q.pop(), msg4)
        self.failUnlessEqual(self.q.pop(), msg1)

    def test_iter_len_clear(self):
        self.failUnlessEqual(len(self.q), 0)
        self.failUnlessEqual(list(self.q), [])
        msg1 = "message 1"
        msg2 = "message 2"
        msg3 = "message 3"
        msg4 = "message 4"
        self.q.put(msg1, priority=1.0)
        self.q.put(msg2, priority=5.0)
        self.q.put(msg3, priority=3.0)
        self.q.put(msg4, priority=2.0)
        self.failUnlessEqual(len(self.q), 4)
        self.failUnlessEqual(list(self.q), \
            [(msg2, 5.0), (msg3, 3.0), (msg4, 2.0), (msg1, 1.0)])
        self.q.clear()
        self.failUnlessEqual(len(self.q), 0)
        self.failUnlessEqual(list(self.q), [])

    def test_remove(self):
        self.failUnlessEqual(len(self.q), 0)
        self.failUnlessEqual(list(self.q), [])
        msg1 = "good message 1"
        msg2 = "bad message 2"
        msg3 = "good message 3"
        msg4 = "bad message 4"
        self.q.put(msg1)
        self.q.put(msg2)
        self.q.put(msg3)
        self.q.put(msg4)
        self.q.remove(lambda x: x.startswith("bad"))
        self.failUnlessEqual(list(self.q), [(msg1, 0.0), (msg3, 0.0)])

    def test_types(self):
        for x in self.supported_values:
            self.q.put(x)
            self.failUnlessEqual(self.q.pop(), x)


class JsonSqlitePriorityQueueTest(SqlitePriorityQueueTest):

    queue_class = JsonSqlitePriorityQueue

    supported_values = SqlitePriorityQueueTest.supported_values + [
        ["a", "list", 1],
        {"a": "dict"},
    ]


class PickleSqlitePriorityQueueTest(JsonSqlitePriorityQueueTest):

    queue_class = PickleSqlitePriorityQueue

    supported_values = JsonSqlitePriorityQueueTest.supported_values + [
        Decimal("10"),
        datetime.now(),
    ]

    def test_request_persistance(self):
        r1 = Request("http://www.example.com", body="some")
        self.q.put(r1)
        r2 = self.q.pop()
        self.failUnless(isinstance(r2, Request))
        self.failUnlessEqual(r1.url, r2.url)
        self.failUnlessEqual(r1.body, r2.body)
