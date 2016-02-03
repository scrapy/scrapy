import os
import sys
import subprocess
import tempfile
from os.path import exists, join, abspath
from shutil import rmtree, copytree
from tempfile import mkdtemp
from threading import Timer
import six

from twisted.trial import unittest
from twisted.internet import defer

import scrapy
from scrapy.utils.python import to_native_str
from scrapy.utils.test import get_testenv
from scrapy.utils.testsite import SiteTest
from scrapy.utils.testproc import ProcessTest


class ProjectTest(unittest.TestCase):
    project_name = 'testproject'

    def setUp(self):
        self.temp_path = mkdtemp()
        self.cwd = self.temp_path
        self.proj_path = join(self.temp_path, self.project_name)
        self.proj_mod_path = join(self.proj_path, self.project_name)
        self.env = get_testenv()

    def tearDown(self):
        rmtree(self.temp_path)

    def call(self, *new_args, **kwargs):
        with tempfile.TemporaryFile() as out:
            args = (sys.executable, '-m', 'scrapy.cmdline') + new_args
            return subprocess.call(args, stdout=out, stderr=out, cwd=self.cwd,
                env=self.env, **kwargs)

    def proc(self, *new_args, **kwargs):
        args = (sys.executable, '-m', 'scrapy.cmdline') + new_args
        p = subprocess.Popen(args, cwd=self.cwd, env=self.env,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             **kwargs)

        def kill_proc():
            p.kill()
            assert False, 'Command took too much time to complete'

        timer = Timer(15, kill_proc)
        try:
            timer.start()
            stdout, stderr = p.communicate()
        finally:
            timer.cancel()

        return to_native_str(stdout), to_native_str(stderr)


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
        self.assertEqual(1, self.call('startproject', 'sys'))


class StartprojectTemplatesTest(ProjectTest):

    def setUp(self):
        super(StartprojectTemplatesTest, self).setUp()
        self.tmpl = join(self.temp_path, 'templates')
        self.tmpl_proj = join(self.tmpl, 'project')

    def test_startproject_template_override(self):
        copytree(join(scrapy.__path__[0], 'templates'), self.tmpl)
        with open(join(self.tmpl_proj, 'root_template'), 'w'):
            pass
        assert exists(join(self.tmpl_proj, 'root_template'))

        args = ['--set', 'TEMPLATES_DIR=%s' % self.tmpl]
        out, err = self.proc('startproject', self.project_name, *args)
        self.assertIn("New Scrapy project '%s', using template directory" % self.project_name, out)
        self.assertIn(self.tmpl_proj, out)
        assert exists(join(self.proj_path, 'root_template'))


class CommandTest(ProjectTest):

    def setUp(self):
        super(CommandTest, self).setUp()
        self.call('startproject', self.project_name)
        self.cwd = join(self.temp_path, self.project_name)
        self.env['SCRAPY_SETTINGS_MODULE'] = '%s.settings' % self.project_name


class GenspiderCommandTest(CommandTest):

    def test_arguments(self):
        # only pass one argument. spider script shouldn't be created
        self.assertEqual(2, self.call('genspider', 'test_name'))
        assert not exists(join(self.proj_mod_path, 'spiders', 'test_name.py'))
        # pass two arguments <name> <domain>. spider script should be created
        self.assertEqual(0, self.call('genspider', 'test_name', 'test.com'))
        assert exists(join(self.proj_mod_path, 'spiders', 'test_name.py'))

    def test_template(self, tplname='crawl'):
        args = ['--template=%s' % tplname] if tplname else []
        spname = 'test_spider'
        out, err = self.proc('genspider', spname, 'test.com', *args)
        self.assertIn("Created spider %r using template %r in module" % (spname, tplname), out)
        self.assertTrue(exists(join(self.proj_mod_path, 'spiders', 'test_spider.py')))
        out, err = self.proc('genspider', spname, 'test.com', *args)
        self.assertIn("Spider %r already exists in module" % spname, out)

    def test_template_basic(self):
        self.test_template('basic')

    def test_template_csvfeed(self):
        self.test_template('csvfeed')

    def test_template_xmlfeed(self):
        self.test_template('xmlfeed')

    def test_list(self):
        self.assertEqual(0, self.call('genspider', '--list'))

    def test_dump(self):
        self.assertEqual(0, self.call('genspider', '--dump=basic'))
        self.assertEqual(0, self.call('genspider', '-d', 'basic'))

    def test_same_name_as_project(self):
        self.assertEqual(2, self.call('genspider', self.project_name))
        assert not exists(join(self.proj_mod_path, 'spiders', '%s.py' % self.project_name))


class MiscCommandsTest(CommandTest):

    def test_list(self):
        self.assertEqual(0, self.call('list'))


class RunSpiderCommandTest(CommandTest):

    def test_runspider(self):
        tmpdir = self.mktemp()
        os.mkdir(tmpdir)
        fname = abspath(join(tmpdir, 'myspider.py'))
        with open(fname, 'w') as f:
            f.write("""
import scrapy

class MySpider(scrapy.Spider):
    name = 'myspider'

    def start_requests(self):
        self.logger.debug("It Works!")
        return []
""")
        _, log = self.proc('runspider', fname)
        self.assertIn("DEBUG: It Works!", log)
        self.assertIn("INFO: Spider opened", log)
        self.assertIn("INFO: Closing spider (finished)", log)
        self.assertIn("INFO: Spider closed (finished)", log)

    def test_runspider_no_spider_found(self):
        tmpdir = self.mktemp()
        os.mkdir(tmpdir)
        fname = abspath(join(tmpdir, 'myspider.py'))
        with open(fname, 'w') as f:
            f.write("""
from scrapy.spiders import Spider
""")
        _, log = self.proc('runspider', fname)
        self.assertIn("No spider found in file", log)

    def test_runspider_file_not_found(self):
        _, log = self.proc('runspider', 'some_non_existent_file')
        self.assertIn("File not found: some_non_existent_file", log)

    def test_runspider_unable_to_load(self):
        tmpdir = self.mktemp()
        os.mkdir(tmpdir)
        fname = abspath(join(tmpdir, 'myspider.txt'))
        with open(fname, 'w') as f:
            f.write("")
        _, log = self.proc('runspider', fname)
        self.assertIn("Unable to load", log)


class ParseCommandTest(ProcessTest, SiteTest, CommandTest):
    command = 'parse'

    def setUp(self):
        super(ParseCommandTest, self).setUp()
        self.spider_name = 'parse_spider'
        fname = abspath(join(self.proj_mod_path, 'spiders', 'myspider.py'))
        with open(fname, 'w') as f:
            f.write("""
import scrapy

class MySpider(scrapy.Spider):
    name = '{0}'

    def parse(self, response):
        if getattr(self, 'test_arg', None):
            self.logger.debug('It Works!')
        return [scrapy.Item(), dict(foo='bar')]
""".format(self.spider_name))

        fname = abspath(join(self.proj_mod_path, 'pipelines.py'))
        with open(fname, 'w') as f:
            f.write("""
import logging

class MyPipeline(object):
    component_name = 'my_pipeline'

    def process_item(self, item, spider):
        logging.info('It Works!')
        return item
""")

        fname = abspath(join(self.proj_mod_path, 'settings.py'))
        with open(fname, 'a') as f:
            f.write("""
ITEM_PIPELINES = {'%s.pipelines.MyPipeline': 1}
""" % self.project_name)

    @defer.inlineCallbacks
    def test_spider_arguments(self):
        _, _, stderr = yield self.execute(['--spider', self.spider_name,
                                           '-a', 'test_arg=1',
                                           '-c', 'parse',
                                           self.url('/html')])
        self.assertIn("DEBUG: It Works!", to_native_str(stderr))

    @defer.inlineCallbacks
    def test_pipelines(self):
        _, _, stderr = yield self.execute(['--spider', self.spider_name,
                                           '--pipelines',
                                           '-c', 'parse',
                                           self.url('/html')])
        self.assertIn("INFO: It Works!", to_native_str(stderr))

    @defer.inlineCallbacks
    def test_parse_items(self):
        status, out, stderr = yield self.execute(
            ['--spider', self.spider_name, '-c', 'parse', self.url('/html')]
        )
        self.assertIn("""[{}, {'foo': 'bar'}]""", to_native_str(out))



class BenchCommandTest(CommandTest):

    def test_run(self):
        _, log = self.proc('bench', '-s', 'LOGSTATS_INTERVAL=0.001',
                           '-s', 'CLOSESPIDER_TIMEOUT=0.01')
        self.assertIn('INFO: Crawled', log)
        self.assertNotIn('Unhandled Error', log)
