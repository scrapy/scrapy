from twisted.internet.defer import inlineCallbacks, maybeDeferred
from twisted.trial import unittest

from zope.interface.verify import verifyObject

from scrapyd.interfaces import ISpiderQueue
from scrapyd.spiderqueue import SqliteSpiderQueue

class SpiderQueueTest(unittest.TestCase):
    """This test case can be used easily for testing other SpiderQueue's by
    just changing the _get_queue() method. It also supports queues with
    deferred methods.
    """

    def setUp(self):
        self.q = self._get_queue()
        self.name = 'spider1'
        self.args = {'arg1': 'val1', 'arg2': 2}
        self.msg = self.args.copy()
        self.msg['name'] = self.name

    def _get_queue(self):
        return SqliteSpiderQueue(':memory:')

    def test_interface(self):
        verifyObject(ISpiderQueue, self.q)

    @inlineCallbacks
    def test_add_pop_count(self):
        c = yield maybeDeferred(self.q.count)
        self.assertEqual(c, 0)

        yield maybeDeferred(self.q.add, self.name, **self.args)

        c = yield maybeDeferred(self.q.count)
        self.assertEqual(c, 1)

        m = yield maybeDeferred(self.q.pop)
        self.assertEqual(m, self.msg)

        c = yield maybeDeferred(self.q.count)
        self.assertEqual(c, 0)

    @inlineCallbacks
    def test_list(self):
        l = yield maybeDeferred(self.q.list)
        self.assertEqual(l, [])

        yield maybeDeferred(self.q.add, self.name, **self.args)
        yield maybeDeferred(self.q.add, self.name, **self.args)

        l = yield maybeDeferred(self.q.list)
        self.assertEqual(l, [self.msg, self.msg])

    @inlineCallbacks
    def test_clear(self):
        yield maybeDeferred(self.q.add, self.name, **self.args)
        yield maybeDeferred(self.q.add, self.name, **self.args)

        c = yield maybeDeferred(self.q.count)
        self.assertEqual(c, 2)

        yield maybeDeferred(self.q.clear)

        c = yield maybeDeferred(self.q.count)
        self.assertEqual(c, 0)
