import os

from twisted.trial import unittest

from zope.interface.verify import verifyObject

from scrapyd.interfaces import IEnvironment
from scrapyd.config import Config
from scrapyd.environ import Environment

class EggStorageTest(unittest.TestCase):

    def setUp(self):
        d = self.mktemp()
        os.mkdir(d)
        config = Config(values={'eggs_dir': d, 'logs_dir': d})
        self.environ = Environment(config)

    def test_interface(self):
        verifyObject(IEnvironment, self.environ)

    def test_get_environment(self):
        msg = {'project': 'mybot'}
        slot = 3
        env = self.environ.get_environment(msg, slot)
        self.assertEqual(env['SCRAPY_PROJECT'], 'mybot')
        self.assert_(env['SCRAPY_SQLITE_DB'].endswith('mybot.db'))
        self.assert_(env['SCRAPY_LOG_FILE'].endswith('slot3.log'))
