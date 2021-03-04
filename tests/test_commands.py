import inspect
import json
import optparse
import os
import platform
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from itertools import chain
from os.path import exists, join, abspath, getmtime
from pathlib import Path
from shutil import rmtree, copytree
from stat import S_IWRITE as ANYONE_WRITE_PERMISSION
from tempfile import mkdtemp
from threading import Timer
from unittest import skipIf

from pytest import mark
from twisted import version as twisted_version
from twisted.python.versions import Version
from twisted.trial import unittest

import scrapy
from scrapy.commands import ScrapyCommand
from scrapy.commands.startproject import IGNORE
from scrapy.settings import Settings
from scrapy.utils.python import to_unicode
from scrapy.utils.test import get_testenv

from tests.test_crawler import ExceptionSpider, NoRequestsSpider


class CommandSettings(unittest.TestCase):

    def setUp(self):
        self.command = ScrapyCommand()
        self.command.settings = Settings()
        self.parser = optparse.OptionParser(
            formatter=optparse.TitledHelpFormatter(),
            conflict_handler='resolve',
        )
        self.command.add_options(self.parser)

    def test_settings_json_string(self):
        feeds_json = '{"data.json": {"format": "json"}, "data.xml": {"format": "xml"}}'
        opts, args = self.parser.parse_args(args=['-s', f'FEEDS={feeds_json}', 'spider.py'])
        self.command.process_options(args, opts)
        self.assertIsInstance(self.command.settings['FEEDS'], scrapy.settings.BaseSettings)
        self.assertEqual(dict(self.command.settings['FEEDS']), json.loads(feeds_json))


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

    def proc(self, *new_args, **popen_kwargs):
        args = (sys.executable, '-m', 'scrapy.cmdline') + new_args
        p = subprocess.Popen(args, cwd=self.cwd, env=self.env,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             **popen_kwargs)

        def kill_proc():
            p.kill()
            p.communicate()
            assert False, 'Command took too much time to complete'

        timer = Timer(15, kill_proc)
        try:
            timer.start()
            stdout, stderr = p.communicate()
        finally:
            timer.cancel()

        return p, to_unicode(stdout), to_unicode(stderr)


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

    def test_startproject_with_project_dir(self):
        project_dir = mkdtemp()
        self.assertEqual(0, self.call('startproject', self.project_name, project_dir))

        assert exists(join(abspath(project_dir), 'scrapy.cfg'))
        assert exists(join(abspath(project_dir), 'testproject'))
        assert exists(join(join(abspath(project_dir), self.project_name), '__init__.py'))
        assert exists(join(join(abspath(project_dir), self.project_name), 'items.py'))
        assert exists(join(join(abspath(project_dir), self.project_name), 'pipelines.py'))
        assert exists(join(join(abspath(project_dir), self.project_name), 'settings.py'))
        assert exists(join(join(abspath(project_dir), self.project_name), 'spiders', '__init__.py'))

        self.assertEqual(0, self.call('startproject', self.project_name, project_dir + '2'))

        self.assertEqual(1, self.call('startproject', self.project_name, project_dir))
        self.assertEqual(1, self.call('startproject', self.project_name + '2', project_dir))
        self.assertEqual(1, self.call('startproject', 'wrong---project---name'))
        self.assertEqual(1, self.call('startproject', 'sys'))
        self.assertEqual(2, self.call('startproject'))
        self.assertEqual(2, self.call('startproject', self.project_name, project_dir, 'another_params'))


def get_permissions_dict(path, renamings=None, ignore=None):

    def get_permissions(path):
        return oct(os.stat(path).st_mode)

    renamings = renamings or tuple()
    permissions_dict = {
        '.': get_permissions(path),
    }
    for root, dirs, files in os.walk(path):
        nodes = list(chain(dirs, files))
        if ignore:
            ignored_names = ignore(root, nodes)
            nodes = [node for node in nodes if node not in ignored_names]
        for node in nodes:
            absolute_path = os.path.join(root, node)
            relative_path = os.path.relpath(absolute_path, path)
            for search_string, replacement in renamings:
                relative_path = relative_path.replace(
                    search_string,
                    replacement
                )
            permissions = get_permissions(absolute_path)
            permissions_dict[relative_path] = permissions
    return permissions_dict


class StartprojectTemplatesTest(ProjectTest):

    maxDiff = None

    def setUp(self):
        super().setUp()
        self.tmpl = join(self.temp_path, 'templates')
        self.tmpl_proj = join(self.tmpl, 'project')

    def test_startproject_template_override(self):
        copytree(join(scrapy.__path__[0], 'templates'), self.tmpl)
        with open(join(self.tmpl_proj, 'root_template'), 'w'):
            pass
        assert exists(join(self.tmpl_proj, 'root_template'))

        args = ['--set', f'TEMPLATES_DIR={self.tmpl}']
        p, out, err = self.proc('startproject', self.project_name, *args)
        self.assertIn(f"New Scrapy project '{self.project_name}', "
                      "using template directory", out)
        self.assertIn(self.tmpl_proj, out)
        assert exists(join(self.proj_path, 'root_template'))

    def test_startproject_permissions_from_writable(self):
        """Check that generated files have the right permissions when the
        template folder has the same permissions as in the project, i.e.
        everything is writable."""
        scrapy_path = scrapy.__path__[0]
        project_template = os.path.join(scrapy_path, 'templates', 'project')
        project_name = 'startproject1'
        renamings = (
            ('module', project_name),
            ('.tmpl', ''),
        )
        expected_permissions = get_permissions_dict(
            project_template,
            renamings,
            IGNORE,
        )

        destination = mkdtemp()
        process = subprocess.Popen(
            (
                sys.executable,
                '-m',
                'scrapy.cmdline',
                'startproject',
                project_name,
            ),
            cwd=destination,
            env=self.env,
        )
        process.wait()

        project_dir = os.path.join(destination, project_name)
        actual_permissions = get_permissions_dict(project_dir)

        self.assertEqual(actual_permissions, expected_permissions)

    def test_startproject_permissions_from_read_only(self):
        """Check that generated files have the right permissions when the
        template folder has been made read-only, which is something that some
        systems do.

        See https://github.com/scrapy/scrapy/pull/4604
        """
        scrapy_path = scrapy.__path__[0]
        templates_dir = os.path.join(scrapy_path, 'templates')
        project_template = os.path.join(templates_dir, 'project')
        project_name = 'startproject2'
        renamings = (
            ('module', project_name),
            ('.tmpl', ''),
        )
        expected_permissions = get_permissions_dict(
            project_template,
            renamings,
            IGNORE,
        )

        def _make_read_only(path):
            current_permissions = os.stat(path).st_mode
            os.chmod(path, current_permissions & ~ANYONE_WRITE_PERMISSION)

        read_only_templates_dir = str(Path(mkdtemp()) / 'templates')
        copytree(templates_dir, read_only_templates_dir)

        for root, dirs, files in os.walk(read_only_templates_dir):
            for node in chain(dirs, files):
                _make_read_only(os.path.join(root, node))

        destination = mkdtemp()
        process = subprocess.Popen(
            (
                sys.executable,
                '-m',
                'scrapy.cmdline',
                'startproject',
                project_name,
                '--set',
                f'TEMPLATES_DIR={read_only_templates_dir}',
            ),
            cwd=destination,
            env=self.env,
        )
        process.wait()

        project_dir = os.path.join(destination, project_name)
        actual_permissions = get_permissions_dict(project_dir)

        self.assertEqual(actual_permissions, expected_permissions)

    def test_startproject_permissions_unchanged_in_destination(self):
        """Check that pre-existing folders and files in the destination folder
        do not see their permissions modified."""
        scrapy_path = scrapy.__path__[0]
        project_template = os.path.join(scrapy_path, 'templates', 'project')
        project_name = 'startproject3'
        renamings = (
            ('module', project_name),
            ('.tmpl', ''),
        )
        expected_permissions = get_permissions_dict(
            project_template,
            renamings,
            IGNORE,
        )

        destination = mkdtemp()
        project_dir = os.path.join(destination, project_name)

        existing_nodes = {
            oct(permissions)[2:] + extension: permissions
            for extension in ('', '.d')
            for permissions in (
                0o444, 0o555, 0o644, 0o666, 0o755, 0o777,
            )
        }
        os.mkdir(project_dir)
        project_dir_path = Path(project_dir)
        for node, permissions in existing_nodes.items():
            path = project_dir_path / node
            if node.endswith('.d'):
                path.mkdir(mode=permissions)
            else:
                path.touch(mode=permissions)
            expected_permissions[node] = oct(path.stat().st_mode)

        process = subprocess.Popen(
            (
                sys.executable,
                '-m',
                'scrapy.cmdline',
                'startproject',
                project_name,
                '.',
            ),
            cwd=project_dir,
            env=self.env,
        )
        process.wait()

        actual_permissions = get_permissions_dict(project_dir)

        self.assertEqual(actual_permissions, expected_permissions)

    def test_startproject_permissions_umask_022(self):
        """Check that generated files have the right permissions when the
        system uses a umask value that causes new files to have different
        permissions than those from the template folder."""
        @contextmanager
        def umask(new_mask):
            cur_mask = os.umask(new_mask)
            yield
            os.umask(cur_mask)

        scrapy_path = scrapy.__path__[0]
        project_template = os.path.join(
            scrapy_path,
            'templates',
            'project'
        )
        project_name = 'umaskproject'
        renamings = (
            ('module', project_name),
            ('.tmpl', ''),
        )
        expected_permissions = get_permissions_dict(
            project_template,
            renamings,
            IGNORE,
        )

        with umask(0o002):
            destination = mkdtemp()
            process = subprocess.Popen(
                (
                    sys.executable,
                    '-m',
                    'scrapy.cmdline',
                    'startproject',
                    project_name,
                ),
                cwd=destination,
                env=self.env,
            )
            process.wait()

            project_dir = os.path.join(destination, project_name)
            actual_permissions = get_permissions_dict(project_dir)

            self.assertEqual(actual_permissions, expected_permissions)


class CommandTest(ProjectTest):

    def setUp(self):
        super().setUp()
        self.call('startproject', self.project_name)
        self.cwd = join(self.temp_path, self.project_name)
        self.env['SCRAPY_SETTINGS_MODULE'] = f'{self.project_name}.settings'


class GenspiderCommandTest(CommandTest):

    def test_arguments(self):
        # only pass one argument. spider script shouldn't be created
        self.assertEqual(2, self.call('genspider', 'test_name'))
        assert not exists(join(self.proj_mod_path, 'spiders', 'test_name.py'))
        # pass two arguments <name> <domain>. spider script should be created
        self.assertEqual(0, self.call('genspider', 'test_name', 'test.com'))
        assert exists(join(self.proj_mod_path, 'spiders', 'test_name.py'))

    def test_template(self, tplname='crawl'):
        args = [f'--template={tplname}'] if tplname else []
        spname = 'test_spider'
        spmodule = f"{self.project_name}.spiders.{spname}"
        p, out, err = self.proc('genspider', spname, 'test.com', *args)
        self.assertIn(f"Created spider {spname!r} using template {tplname!r} in module:{os.linesep}  {spmodule}", out)
        self.assertTrue(exists(join(self.proj_mod_path, 'spiders', 'test_spider.py')))
        modify_time_before = getmtime(join(self.proj_mod_path, 'spiders', 'test_spider.py'))
        p, out, err = self.proc('genspider', spname, 'test.com', *args)
        self.assertIn(f"Spider {spname!r} already exists in module", out)
        modify_time_after = getmtime(join(self.proj_mod_path, 'spiders', 'test_spider.py'))
        self.assertEqual(modify_time_after, modify_time_before)

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
        assert not exists(join(self.proj_mod_path, 'spiders', f'{self.project_name}.py'))

    def test_same_filename_as_existing_spider(self, force=False):
        file_name = 'example'
        file_path = join(self.proj_mod_path, 'spiders', f'{file_name}.py')
        self.assertEqual(0, self.call('genspider', file_name, 'example.com'))
        assert exists(file_path)

        # change name of spider but not its file name
        with open(file_path, 'r+') as spider_file:
            file_data = spider_file.read()
            file_data = file_data.replace("name = \'example\'", "name = \'renamed\'")
            spider_file.seek(0)
            spider_file.write(file_data)
            spider_file.truncate()
        modify_time_before = getmtime(file_path)
        file_contents_before = file_data

        if force:
            p, out, err = self.proc('genspider', '--force', file_name, 'example.com')
            self.assertIn(f"Created spider {file_name!r} using template \'basic\' in module", out)
            modify_time_after = getmtime(file_path)
            self.assertNotEqual(modify_time_after, modify_time_before)
            file_contents_after = open(file_path, 'r').read()
            self.assertNotEqual(file_contents_after, file_contents_before)
        else:
            p, out, err = self.proc('genspider', file_name, 'example.com')
            self.assertIn(f"{file_path} already exists", out)
            modify_time_after = getmtime(file_path)
            self.assertEqual(modify_time_after, modify_time_before)
            file_contents_after = open(file_path, 'r').read()
            self.assertEqual(file_contents_after, file_contents_before)

    def test_same_filename_as_existing_spider_force(self):
        self.test_same_filename_as_existing_spider(force=True)


class GenspiderStandaloneCommandTest(ProjectTest):

    def test_generate_standalone_spider(self):
        self.call('genspider', 'example', 'example.com')
        assert exists(join(self.temp_path, 'example.py'))

    def test_same_name_as_existing_file(self, force=False):
        file_name = 'example'
        file_path = join(self.temp_path, file_name + '.py')
        p, out, err = self.proc('genspider', file_name, 'example.com')
        self.assertIn(f"Created spider {file_name!r} using template \'basic\' ", out)
        assert exists(file_path)
        modify_time_before = getmtime(file_path)
        file_contents_before = open(file_path, 'r').read()

        if force:
            # use different template to ensure contents were changed
            p, out, err = self.proc('genspider', '--force', '-t', 'crawl', file_name, 'example.com')
            self.assertIn(f"Created spider {file_name!r} using template \'crawl\' ", out)
            modify_time_after = getmtime(file_path)
            self.assertNotEqual(modify_time_after, modify_time_before)
            file_contents_after = open(file_path, 'r').read()
            self.assertNotEqual(file_contents_after, file_contents_before)
        else:
            p, out, err = self.proc('genspider', file_name, 'example.com')
            self.assertIn(f"{join(self.temp_path, file_name + '.py')} already exists", out)
            modify_time_after = getmtime(file_path)
            self.assertEqual(modify_time_after, modify_time_before)
            file_contents_after = open(file_path, 'r').read()
            self.assertEqual(file_contents_after, file_contents_before)

    def test_same_name_as_existing_file_force(self):
        self.test_same_name_as_existing_file(force=True)


class MiscCommandsTest(CommandTest):

    def test_list(self):
        self.assertEqual(0, self.call('list'))


class RunSpiderCommandTest(CommandTest):

    spider_filename = 'myspider.py'

    debug_log_spider = """
import scrapy

class MySpider(scrapy.Spider):
    name = 'myspider'

    def start_requests(self):
        self.logger.debug("It Works!")
        return []
"""

    badspider = """
import scrapy

class BadSpider(scrapy.Spider):
    name = "bad"
    def start_requests(self):
        raise Exception("oops!")
        """

    @contextmanager
    def _create_file(self, content, name=None):
        tmpdir = self.mktemp()
        os.mkdir(tmpdir)
        if name:
            fname = abspath(join(tmpdir, name))
        else:
            fname = abspath(join(tmpdir, self.spider_filename))
        with open(fname, 'w') as f:
            f.write(content)
        try:
            yield fname
        finally:
            rmtree(tmpdir)

    def runspider(self, code, name=None, args=()):
        with self._create_file(code, name) as fname:
            return self.proc('runspider', fname, *args)

    def get_log(self, code, name=None, args=()):
        p, stdout, stderr = self.runspider(code, name, args=args)
        return stderr

    def test_runspider(self):
        log = self.get_log(self.debug_log_spider)
        self.assertIn("DEBUG: It Works!", log)
        self.assertIn("INFO: Spider opened", log)
        self.assertIn("INFO: Closing spider (finished)", log)
        self.assertIn("INFO: Spider closed (finished)", log)

    def test_run_fail_spider(self):
        proc, _, _ = self.runspider("import scrapy\n" + inspect.getsource(ExceptionSpider))
        ret = proc.returncode
        self.assertNotEqual(ret, 0)

    def test_run_good_spider(self):
        proc, _, _ = self.runspider("import scrapy\n" + inspect.getsource(NoRequestsSpider))
        ret = proc.returncode
        self.assertEqual(ret, 0)

    def test_runspider_log_level(self):
        log = self.get_log(self.debug_log_spider,
                           args=('-s', 'LOG_LEVEL=INFO'))
        self.assertNotIn("DEBUG: It Works!", log)
        self.assertIn("INFO: Spider opened", log)

    def test_runspider_dnscache_disabled(self):
        # see https://github.com/scrapy/scrapy/issues/2811
        # The spider below should not be able to connect to localhost:12345,
        # which is intended,
        # but this should not be because of DNS lookup error
        # assumption: localhost will resolve in all cases (true?)
        dnscache_spider = """
import scrapy

class MySpider(scrapy.Spider):
    name = 'myspider'
    start_urls = ['http://localhost:12345']

    def parse(self, response):
        return {'test': 'value'}
"""
        log = self.get_log(dnscache_spider, args=('-s', 'DNSCACHE_ENABLED=False'))
        self.assertNotIn("DNSLookupError", log)
        self.assertIn("INFO: Spider opened", log)

    def test_runspider_log_short_names(self):
        log1 = self.get_log(self.debug_log_spider,
                            args=('-s', 'LOG_SHORT_NAMES=1'))
        self.assertIn("[myspider] DEBUG: It Works!", log1)
        self.assertIn("[scrapy]", log1)
        self.assertNotIn("[scrapy.core.engine]", log1)

        log2 = self.get_log(self.debug_log_spider,
                            args=('-s', 'LOG_SHORT_NAMES=0'))
        self.assertIn("[myspider] DEBUG: It Works!", log2)
        self.assertNotIn("[scrapy]", log2)
        self.assertIn("[scrapy.core.engine]", log2)

    def test_runspider_no_spider_found(self):
        log = self.get_log("from scrapy.spiders import Spider\n")
        self.assertIn("No spider found in file", log)

    def test_runspider_file_not_found(self):
        _, _, log = self.proc('runspider', 'some_non_existent_file')
        self.assertIn("File not found: some_non_existent_file", log)

    def test_runspider_unable_to_load(self):
        log = self.get_log('', name='myspider.txt')
        self.assertIn('Unable to load', log)

    def test_start_requests_errors(self):
        log = self.get_log(self.badspider, name='badspider.py')
        self.assertIn("start_requests", log)
        self.assertIn("badspider.py", log)

    # https://twistedmatrix.com/trac/ticket/9766
    @skipIf(platform.system() == 'Windows' and sys.version_info >= (3, 8),
            "the asyncio reactor is broken on Windows when running Python ≥ 3.8")
    def test_asyncio_enabled_true(self):
        log = self.get_log(self.debug_log_spider, args=[
            '-s', 'TWISTED_REACTOR=twisted.internet.asyncioreactor.AsyncioSelectorReactor'
        ])
        self.assertIn("Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor", log)

    def test_asyncio_enabled_false(self):
        log = self.get_log(self.debug_log_spider, args=[])
        self.assertNotIn("Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor", log)

    @mark.skipif(sys.implementation.name == 'pypy', reason='uvloop does not support pypy properly')
    @mark.skipif(platform.system() == 'Windows', reason='uvloop does not support Windows')
    @mark.skipif(twisted_version == Version('twisted', 21, 2, 0), reason='https://twistedmatrix.com/trac/ticket/10106')
    def test_custom_asyncio_loop_enabled_true(self):
        log = self.get_log(self.debug_log_spider, args=[
            '-s',
            'TWISTED_REACTOR=twisted.internet.asyncioreactor.AsyncioSelectorReactor',
            '-s',
            'ASYNCIO_EVENT_LOOP=uvloop.Loop',
        ])
        self.assertIn("Using asyncio event loop: uvloop.Loop", log)

    # https://twistedmatrix.com/trac/ticket/9766
    @skipIf(platform.system() == 'Windows' and sys.version_info >= (3, 8),
            "the asyncio reactor is broken on Windows when running Python ≥ 3.8")
    def test_custom_asyncio_loop_enabled_false(self):
        log = self.get_log(self.debug_log_spider, args=[
            '-s', 'TWISTED_REACTOR=twisted.internet.asyncioreactor.AsyncioSelectorReactor'
        ])
        import asyncio
        loop = asyncio.new_event_loop()
        self.assertIn("Using asyncio event loop: %s.%s" % (loop.__module__, loop.__class__.__name__), log)

    def test_output(self):
        spider_code = """
import scrapy

class MySpider(scrapy.Spider):
    name = 'myspider'

    def start_requests(self):
        self.logger.debug('FEEDS: {}'.format(self.settings.getdict('FEEDS')))
        return []
"""
        args = ['-o', 'example.json']
        log = self.get_log(spider_code, args=args)
        self.assertIn("[myspider] DEBUG: FEEDS: {'example.json': {'format': 'json'}}", log)

    def test_overwrite_output(self):
        spider_code = """
import json
import scrapy

class MySpider(scrapy.Spider):
    name = 'myspider'

    def start_requests(self):
        self.logger.debug(
            'FEEDS: {}'.format(
                json.dumps(self.settings.getdict('FEEDS'), sort_keys=True)
            )
        )
        return []
"""
        with open(os.path.join(self.cwd, "example.json"), "w") as f1:
            f1.write("not empty")
        args = ['-O', 'example.json']
        log = self.get_log(spider_code, args=args)
        self.assertIn('[myspider] DEBUG: FEEDS: {"example.json": {"format": "json", "overwrite": true}}', log)
        with open(os.path.join(self.cwd, "example.json")) as f2:
            first_line = f2.readline()
        self.assertNotEqual(first_line, "not empty")

    def test_output_and_overwrite_output(self):
        spider_code = """
import scrapy

class MySpider(scrapy.Spider):
    name = 'myspider'

    def start_requests(self):
        return []
"""
        args = ['-o', 'example1.json', '-O', 'example2.json']
        log = self.get_log(spider_code, args=args)
        self.assertIn("error: Please use only one of -o/--output and -O/--overwrite-output", log)


class WindowsRunSpiderCommandTest(RunSpiderCommandTest):

    spider_filename = 'myspider.pyw'

    def setUp(self):
        super(WindowsRunSpiderCommandTest, self).setUp()

    def test_start_requests_errors(self):
        log = self.get_log(self.badspider, name='badspider.pyw')
        self.assertIn("start_requests", log)
        self.assertIn("badspider.pyw", log)

    @skipIf(platform.system() != 'Windows', "Windows required for .pyw files")
    def test_run_good_spider(self):
        super().test_run_good_spider()

    @skipIf(platform.system() != 'Windows', "Windows required for .pyw files")
    def test_runspider(self):
        super().test_runspider()

    @skipIf(platform.system() != 'Windows', "Windows required for .pyw files")
    def test_runspider_dnscache_disabled(self):
        super().test_runspider_dnscache_disabled()

    @skipIf(platform.system() != 'Windows', "Windows required for .pyw files")
    def test_runspider_log_level(self):
        super().test_runspider_log_level()

    @skipIf(platform.system() != 'Windows', "Windows required for .pyw files")
    def test_runspider_log_short_names(self):
        super().test_runspider_log_short_names()

    @skipIf(platform.system() != 'Windows', "Windows required for .pyw files")
    def test_runspider_no_spider_found(self):
        super().test_runspider_no_spider_found()

    @skipIf(platform.system() != 'Windows', "Windows required for .pyw files")
    def test_output(self):
        super().test_output()

    @skipIf(platform.system() != 'Windows', "Windows required for .pyw files")
    def test_overwrite_output(self):
        super().test_overwrite_output()

    def test_runspider_unable_to_load(self):
        raise unittest.SkipTest("Already Tested in 'RunSpiderCommandTest' ")


class BenchCommandTest(CommandTest):

    def test_run(self):
        _, _, log = self.proc('bench', '-s', 'LOGSTATS_INTERVAL=0.001',
                              '-s', 'CLOSESPIDER_TIMEOUT=0.01')
        self.assertIn('INFO: Crawled', log)
        self.assertNotIn('Unhandled Error', log)


class CrawlCommandTest(CommandTest):

    def crawl(self, code, args=()):
        fname = abspath(join(self.proj_mod_path, 'spiders', 'myspider.py'))
        with open(fname, 'w') as f:
            f.write(code)
        return self.proc('crawl', 'myspider', *args)

    def get_log(self, code, args=()):
        _, _, stderr = self.crawl(code, args=args)
        return stderr

    def test_no_output(self):
        spider_code = """
import scrapy

class MySpider(scrapy.Spider):
    name = 'myspider'

    def start_requests(self):
        self.logger.debug('It works!')
        return []
"""
        log = self.get_log(spider_code)
        self.assertIn("[myspider] DEBUG: It works!", log)

    def test_output(self):
        spider_code = """
import scrapy

class MySpider(scrapy.Spider):
    name = 'myspider'

    def start_requests(self):
        self.logger.debug('FEEDS: {}'.format(self.settings.getdict('FEEDS')))
        return []
"""
        args = ['-o', 'example.json']
        log = self.get_log(spider_code, args=args)
        self.assertIn("[myspider] DEBUG: FEEDS: {'example.json': {'format': 'json'}}", log)

    def test_overwrite_output(self):
        spider_code = """
import json
import scrapy

class MySpider(scrapy.Spider):
    name = 'myspider'

    def start_requests(self):
        self.logger.debug(
            'FEEDS: {}'.format(
                json.dumps(self.settings.getdict('FEEDS'), sort_keys=True)
            )
        )
        return []
"""
        with open(os.path.join(self.cwd, "example.json"), "w") as f1:
            f1.write("not empty")
        args = ['-O', 'example.json']
        log = self.get_log(spider_code, args=args)
        self.assertIn('[myspider] DEBUG: FEEDS: {"example.json": {"format": "json", "overwrite": true}}', log)
        with open(os.path.join(self.cwd, "example.json")) as f2:
            first_line = f2.readline()
        self.assertNotEqual(first_line, "not empty")

    def test_output_and_overwrite_output(self):
        spider_code = """
import scrapy

class MySpider(scrapy.Spider):
    name = 'myspider'

    def start_requests(self):
        return []
"""
        args = ['-o', 'example1.json', '-O', 'example2.json']
        log = self.get_log(spider_code, args=args)
        self.assertIn("error: Please use only one of -o/--output and -O/--overwrite-output", log)
