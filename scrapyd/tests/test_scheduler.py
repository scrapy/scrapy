import os

from twisted.trial import unittest

from zope.interface.verify import verifyObject

from scrapyd.interfaces import ISpiderScheduler
from scrapyd.config import Config
from scrapyd.scheduler import SpiderScheduler
from scrapyd.utils import get_spider_queues

class SpiderSchedulerTest(unittest.TestCase):

    def setUp(self):
        d = self.mktemp()
        eggs_dir = self.eggs_dir = os.path.join(d, 'eggs')
        dbs_dir = os.path.join(d, 'dbs')
        os.mkdir(d)
        os.makedirs(eggs_dir)
        os.makedirs(dbs_dir)
        os.makedirs(os.path.join(eggs_dir, 'mybot1'))
        os.makedirs(os.path.join(eggs_dir, 'mybot2'))
        config = Config(values={'eggs_dir': eggs_dir, 'dbs_dir': dbs_dir})
        self.queues = get_spider_queues(config)
        self.sched = SpiderScheduler(config)

    def test_interface(self):
        verifyObject(ISpiderScheduler, self.sched)

    def test_list_update_projects(self):
        self.assertEqual(sorted(self.sched.list_projects()), sorted(['mybot1', 'mybot2']))
        os.makedirs(os.path.join(self.eggs_dir, 'mybot3'))
        self.sched.update_projects()
        self.assertEqual(sorted(self.sched.list_projects()), sorted(['mybot1', 'mybot2', 'mybot3']))

    def test_schedule(self):
        q = self.queues['mybot1']
        self.failIf(q.count())
        self.sched.schedule('mybot1', 'myspider1', a='b')
        self.sched.schedule('mybot2', 'myspider2', c='d')
        self.assertEqual(q.pop(), {'name': 'myspider1', 'a': 'b'})
        q = self.queues['mybot2']
        self.assertEqual(q.pop(), {'name': 'myspider2', 'c': 'd'})

