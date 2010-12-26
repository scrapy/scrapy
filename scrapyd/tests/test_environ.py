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
        config.cp.add_section('settings')
        config.cp.set('settings', 'newbot', 'newbot.settings')
        self.environ = Environment(config, initenv={})

    def test_interface(self):
        verifyObject(IEnvironment, self.environ)

    def test_get_environment_with_eggfile(self):
        msg = {'_project': 'mybot', '_spider': 'myspider', '_job': 'ID'}
        slot = 3
        env = self.environ.get_environment(msg, slot, '/path/to/file.egg')
        self.assertEqual(env['SCRAPY_PROJECT'], 'mybot')
        self.assertEqual(env['SCRAPY_SLOT'], '3')
        self.assertEqual(env['SCRAPY_SPIDER'], 'myspider')
        self.assertEqual(env['SCRAPY_JOB'], 'ID')
        self.assert_(env['SCRAPY_SQLITE_DB'].endswith('mybot.db'))
        self.assert_(env['SCRAPY_LOG_FILE'].endswith('/mybot/myspider/ID.log'))
        self.assert_(env['SCRAPY_EGGFILE'].endswith('/path/to/file.egg'))
        self.failIf('SCRAPY_SETTINGS_MODULE' in env)

    def test_get_environment_without_eggfile(self):
        msg = {'_project': 'newbot', '_spider': 'myspider', '_job': 'ID'}
        slot = 3
        env = self.environ.get_environment(msg, slot, None)
        self.assertEqual(env['SCRAPY_PROJECT'], 'newbot')
        self.assertEqual(env['SCRAPY_SLOT'], '3')
        self.assertEqual(env['SCRAPY_SPIDER'], 'myspider')
        self.assertEqual(env['SCRAPY_JOB'], 'ID')
        self.assert_(env['SCRAPY_SQLITE_DB'].endswith('newbot.db'))
        self.assert_(env['SCRAPY_LOG_FILE'].endswith('/newbot/myspider/ID.log'))
        self.assertEqual(env['SCRAPY_SETTINGS_MODULE'], 'newbot.settings')
        self.failIf('SCRAPY_EGGFILE' in env)
