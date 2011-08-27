from __future__ import with_statement

import os
from cStringIO import StringIO

from twisted.trial import unittest

from scrapy.utils.py26 import get_data
from scrapyd.interfaces import IEggStorage
from scrapyd.utils import get_crawl_args, get_spider_list
from scrapyd import get_application

__package__ = 'scrapyd.tests' # required for compatibility with python 2.5

class UtilsTest(unittest.TestCase):

    def test_get_crawl_args(self):
        msg = {'_project': 'lolo', '_spider': 'lala'}
        self.assertEqual(get_crawl_args(msg), ['lala'])
        msg = {'_project': 'lolo', '_spider': 'lala', 'arg1': u'val1'}
        cargs = get_crawl_args(msg)
        self.assertEqual(cargs, ['lala', '-a', 'arg1=val1'])
        assert all(isinstance(x, str) for x in cargs), cargs

    def test_get_crawl_args_with_settings(self):
        msg = {'_project': 'lolo', '_spider': 'lala', 'arg1': u'val1', 'settings': {'ONE': 'two'}}
        cargs = get_crawl_args(msg)
        self.assertEqual(cargs, ['lala', '-a', 'arg1=val1', '--set', 'ONE=two'])
        assert all(isinstance(x, str) for x in cargs), cargs

class GetSpiderListTest(unittest.TestCase):

    def test_get_spider_list(self):
        path = os.path.abspath(self.mktemp())
        j = os.path.join
        eggs_dir = j(path, 'eggs')
        os.makedirs(eggs_dir)
        dbs_dir = j(path, 'dbs')
        os.makedirs(dbs_dir)
        logs_dir = j(path, 'logs')
        os.makedirs(logs_dir)
        os.chdir(path)
        with open('scrapyd.conf', 'w') as f:
            f.write("[scrapyd]\n")
            f.write("eggs_dir = %s\n" % eggs_dir)
            f.write("dbs_dir = %s\n" % dbs_dir)
            f.write("logs_dir = %s\n" % logs_dir)
        app = get_application()
        eggstorage = app.getComponent(IEggStorage)
        eggfile = StringIO(get_data(__package__, 'mybot.egg'))
        eggstorage.put(eggfile, 'mybot', 'r1')
        self.assertEqual(sorted(get_spider_list('mybot')), ['spider1', 'spider2'])

