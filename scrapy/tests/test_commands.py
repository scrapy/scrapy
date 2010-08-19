from __future__ import with_statement

import sys
import os
import subprocess
from os.path import exists, join, dirname, abspath
from shutil import rmtree
from tempfile import mkdtemp

from twisted.trial import unittest

import scrapy


class ProjectTest(unittest.TestCase):
    project_name = 'testproject'

    def setUp(self):
        self.temp_path = mkdtemp()
        self.cwd = self.temp_path
        self.proj_path = join(self.temp_path, self.project_name)
        self.proj_mod_path = join(self.proj_path, self.project_name)
        self.env = os.environ.copy()
        self.env['PYTHONPATH'] = dirname(scrapy.__path__[0])

    def tearDown(self):
        rmtree(self.temp_path)

    def call(self, *new_args, **kwargs):
        out = os.tmpfile()
        args = (sys.executable, '-m', 'scrapy.cmdline') + new_args
        return subprocess.call(args, stdout=out, stderr=out, cwd=self.cwd, \
            env=self.env, **kwargs)

    def call_get_proc(self, *new_args, **kwargs):
        out = os.tmpfile()
        args = (sys.executable, '-m', 'scrapy.cmdline') + new_args
        return subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, \
            cwd=self.cwd, env=self.env, **kwargs)


class StartprojectTest(ProjectTest):

    def test_startproject(self):
        self.assertEqual(0, self.call('startproject', self.project_name))

        assert exists(join(self.proj_path, 'scrapy.cfg'))
        assert exists(join(self.proj_path, 'testproject'))
        assert exists(join(self.proj_mod_path, '__init__.py'))
        assert exists(join(self.proj_mod_path, 'items.py'))
        assert exists(join(self.proj_mod_path, 'pipelines.py'))
        assert exists(join(self.proj_mod_path, 'settings.py'))
        assert exists(join(self.proj_mod_path, 'spiders', '__init__.py'))

        self.assertEqual(1, self.call('startproject', self.project_name))
        self.assertEqual(1, self.call('startproject', 'wrong---project---name'))


class CommandTest(ProjectTest):

    def setUp(self):
        super(CommandTest, self).setUp()
        self.call('startproject', self.project_name)
        self.cwd = join(self.temp_path, self.project_name)
        self.env.pop('SCRAPY_SETTINGS_DISABLED', None)
        self.env['SCRAPY_SETTINGS_MODULE'] = '%s.settings' % self.project_name


class GenspiderCommandTest(CommandTest):

    def test_arguments(self):
        # only pass one argument. spider script shouldn't be created
        self.assertEqual(0, self.call('genspider', 'test_name'))
        assert not exists(join(self.proj_mod_path, 'spiders', 'test_name.py'))
        # pass two arguments <name> <domain>. spider script should be created
        self.assertEqual(0, self.call('genspider', 'test_name', 'test.com'))
        assert exists(join(self.proj_mod_path, 'spiders', 'test_name.py'))

    def test_template_default(self, *args):
        self.assertEqual(0, self.call('genspider', 'test_spider', 'test.com', *args))
        assert exists(join(self.proj_mod_path, 'spiders', 'test_spider.py'))
        self.assertEqual(1, self.call('genspider', 'test_spider', 'test.com'))

    def test_template_basic(self):
        self.test_template_default('--template=basic')

    def test_template_csvfeed(self):
        self.test_template_default('--template=csvfeed')

    def test_template_xmlfeed(self):
        self.test_template_default('--template=xmlfeed')

    def test_template_crawl(self):
        self.test_template_default('--template=crawl')

    def test_list(self):
        self.assertEqual(0, self.call('genspider', '--list'))

    def test_dump(self):
        self.assertEqual(0, self.call('genspider', '--dump'))
        self.assertEqual(0, self.call('genspider', '--dump', '--template=basic'))


class MiscCommandsTest(CommandTest):

    def test_crawl(self):
        self.assertEqual(0, self.call('crawl'))

    def test_list(self):
        self.assertEqual(0, self.call('list'))

class RunSpiderCommandTest(CommandTest):

    def test_runspider(self):
        tmpdir = self.mktemp()
        os.mkdir(tmpdir)
        fname = abspath(join(tmpdir, 'myspider.py'))
        with open(fname, 'w') as f:
            f.write("""
from scrapy import log
from scrapy.spider import BaseSpider

class MySpider(BaseSpider):
    name = 'myspider'

    def start_requests(self):
        self.log("It Works!")
        return []
""")
        p = self.call_get_proc('runspider', fname)
        log = p.stderr.read()
        self.assert_("[myspider] DEBUG: It Works!" in log)
        self.assert_("[myspider] INFO: Spider opened" in log)
        self.assert_("[myspider] INFO: Closing spider (finished)" in log)
        self.assert_("[myspider] INFO: Spider closed (finished)" in log)

    def test_runspider_no_spider_found(self):
        tmpdir = self.mktemp()
        os.mkdir(tmpdir)
        fname = abspath(join(tmpdir, 'myspider.py'))
        with open(fname, 'w') as f:
            f.write("""
from scrapy import log
from scrapy.spider import BaseSpider
""")
        p = self.call_get_proc('runspider', fname)
        log = p.stderr.read()
        self.assert_("ERROR: No spider found in file" in log)

    def test_runspider_file_not_found(self):
        p = self.call_get_proc('runspider', 'some_non_existent_file')
        log = p.stderr.read()
        self.assert_("ERROR: File not found: some_non_existent_file" in log)

    def test_runspider_unable_to_load(self):
        tmpdir = self.mktemp()
        os.mkdir(tmpdir)
        fname = abspath(join(tmpdir, 'myspider.txt'))
        with open(fname, 'w') as f:
            f.write("")
        p = self.call_get_proc('runspider', fname)
        log = p.stderr.read()
        self.assert_("ERROR: Unable to load" in log)

