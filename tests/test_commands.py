import os
import sys
import subprocess
import tempfile
from time import sleep
from os.path import exists, join, abspath
from shutil import rmtree, copytree
from tempfile import mkdtemp
from contextlib import contextmanager

from twisted.trial import unittest
from twisted.internet import defer

import scrapy
from scrapy.utils.python import to_native_str
from scrapy.utils.python import retry_on_eintr
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

        waited = 0
        interval = 0.2
        while p.poll() is None:
            sleep(interval)
            waited += interval
            if waited > 15:
                p.kill()
                assert False, 'Command took too much time to complete'

        return p


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
        p = self.proc('startproject', self.project_name, *args)
        out = to_native_str(retry_on_eintr(p.stdout.read))
        self.assertIn("New Scrapy project %r, using template directory" % self.project_name, out)
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
        p = self.proc('genspider', spname, 'test.com', *args)
        out = to_native_str(retry_on_eintr(p.stdout.read))
        self.assertIn("Created spider %r using template %r in module" % (spname, tplname), out)
        self.assertTrue(exists(join(self.proj_mod_path, 'spiders', 'test_spider.py')))
        p = self.proc('genspider', spname, 'test.com', *args)
        out = to_native_str(retry_on_eintr(p.stdout.read))
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

    @contextmanager
    def _create_file(self, content, name):
        tmpdir = self.mktemp()
        os.mkdir(tmpdir)
        fname = abspath(join(tmpdir, name))
        with open(fname, 'w') as f:
            f.write(content)
        try:
            yield fname
        finally:
            rmtree(tmpdir)

    def runspider(self, code, name='myspider.py'):
        with self._create_file(code, name) as fname:
            return self.proc('runspider', fname)

    def test_runspider(self):
        spider = """
import scrapy

class MySpider(scrapy.Spider):
    name = 'myspider'

    def start_requests(self):
        self.logger.debug("It Works!")
        return []
"""
        p = self.runspider(spider)
        log = to_native_str(p.stderr.read())

        self.assertIn("DEBUG: It Works!", log)
        self.assertIn("INFO: Spider opened", log)
        self.assertIn("INFO: Closing spider (finished)", log)
        self.assertIn("INFO: Spider closed (finished)", log)

    def test_runspider_no_spider_found(self):
        p = self.runspider("from scrapy.spiders import Spider\n")
        log = to_native_str(p.stderr.read())
        self.assertIn("No spider found in file", log)

    def test_runspider_file_not_found(self):
        p = self.proc('runspider', 'some_non_existent_file')
        log = to_native_str(p.stderr.read())
        self.assertIn("File not found: some_non_existent_file", log)

    def test_runspider_unable_to_load(self):
        p = self.runspider('', 'myspider.txt')
        log = to_native_str(p.stderr.read())
        self.assertIn('Unable to load', log)

    def test_start_requests_errors(self):
        p = self.runspider("""
import scrapy

class BadSpider(scrapy.Spider):
    name = "bad"
    def start_requests(self):
        raise Exception("oops!")
        """, name="badspider.py")
        log = to_native_str(p.stderr.read())
        print(log)
        self.assertIn("start_requests", log)
        self.assertIn("badspider.py", log)


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
        p = self.proc('bench', '-s', 'LOGSTATS_INTERVAL=0.001',
                '-s', 'CLOSESPIDER_TIMEOUT=0.01')
        log = to_native_str(p.stderr.read())
        self.assertIn('INFO: Crawled', log)
        self.assertNotIn('Unhandled Error', log)
