import os

from twisted.trial import unittest
from twisted.internet.defer import Deferred

from zope.interface.verify import verifyObject

from scrapyd.interfaces import IPoller
from scrapyd.config import Config
from scrapyd.poller import QueuePoller
from scrapyd.utils import get_spider_queues

class QueuePollerTest(unittest.TestCase):

    def setUp(self):
        d = self.mktemp()
        eggs_dir = os.path.join(d, 'eggs')
        dbs_dir = os.path.join(d, 'dbs')
        os.makedirs(eggs_dir)
        os.makedirs(dbs_dir)
        os.makedirs(os.path.join(eggs_dir, 'mybot1'))
        os.makedirs(os.path.join(eggs_dir, 'mybot2'))
        config = Config(values={'eggs_dir': eggs_dir, 'dbs_dir': dbs_dir})
        self.queues = get_spider_queues(config)
        self.poller = QueuePoller(config)

    def test_interface(self):
        verifyObject(IPoller, self.poller)

    def test_poll_next(self):
        self.queues['mybot1'].add('spider1')
        self.queues['mybot2'].add('spider2')
        d1 = self.poller.next()
        d2 = self.poller.next()
        self.failUnless(isinstance(d1, Deferred))
        self.failIf(hasattr(d1, 'result'))
        self.poller.poll()
        self.queues['mybot1'].pop()
        self.poller.poll()
        self.failUnlessEqual(d1.result, {'_project': 'mybot1', '_spider': 'spider1'})
        self.failUnlessEqual(d2.result, {'_project': 'mybot2', '_spider': 'spider2'})
