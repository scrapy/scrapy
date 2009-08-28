import sys
import os
import subprocess
from os.path import exists, join
from shutil import rmtree
from tempfile import mkdtemp
import unittest


class ProjectTest(unittest.TestCase):
    project_name = 'testproject'

    def setUp(self):
        self.temp_path = mkdtemp()
        self.cwd = self.temp_path
        self.proj_path = join(self.temp_path, self.project_name)
        self.proj_mod_path = join(self.proj_path, self.project_name)

    def tearDown(self):
        rmtree(self.temp_path)

    def call(self, new_args, **kwargs):
        out = os.tmpfile()
        env = getattr(self, 'env', os.environ)
        args = [sys.executable, '-m', 'scrapy.command.cmdline']
        args.extend(new_args)
        return subprocess.call(args, stdout=out, stderr=out, cwd=self.cwd, \
            env=env, **kwargs)


class StartprojectTest(ProjectTest):
    
    def test_startproject(self):
        ret = self.call(['startproject', self.project_name])
        self.assertEqual(ret, 0)

        assert exists(join(self.proj_path, 'scrapy-ctl.py'))
        assert exists(join(self.proj_path, 'testproject'))
        assert exists(join(self.proj_mod_path, '__init__.py'))
        assert exists(join(self.proj_mod_path, 'items.py'))
        assert exists(join(self.proj_mod_path, 'pipelines.py'))
        assert exists(join(self.proj_mod_path, 'settings.py'))
        assert exists(join(self.proj_mod_path, 'spiders', '__init__.py'))

        ret = self.call(['startproject', self.project_name])
        self.assertEqual(ret, 1)

        ret = self.call(['startproject', 'wrong---project---name'])
        self.assertEqual(ret, 1)


class CommandTest(ProjectTest):

    def setUp(self):
        super(CommandTest, self).setUp()

        self.call(['startproject', self.project_name])

        self.cwd = join(self.temp_path, self.project_name)

        self.env = os.environ.copy()
        self.env.pop('SCRAPY_SETTINGS_DISABLED', None)
        self.env['SCRAPY_SETTINGS_MODULE'] = '%s.settings' % self.project_name


class MiscCommandsTest(CommandTest):

    def test_crawl(self):
        ret = self.call(['crawl'])
        self.assertEqual(ret, 0)

    def test_genspider_subcommands(self):
        ret = self.call(['genspider', '--list'])
        self.assertEqual(ret, 0)

        ret = self.call(['genspider', '--dump'])
        self.assertEqual(ret, 0)

        ret = self.call(['genspider', '--dump', '--template=basic'])
        self.assertEqual(ret, 0)

    def test_list(self):
        ret = self.call(['list'])
        self.assertEqual(ret, 0)


class BaseGenspiderTest(CommandTest):
    template = 'basic'

    def test_genspider(self):
        ret = self.call(['genspider', 'testspider', 'test.com',
                          '--template=%s' % self.template])
        self.assertEqual(ret, 0)
        assert exists(join(self.proj_mod_path, 'spiders', 'testspider.py'))

        ret = self.call(['genspider', 'otherspider', 'test.com'])
        self.assertEqual(ret, 1)

    
class CrawlGenspiderTest(BaseGenspiderTest):
    template = 'crawl'


class CsvFeedGenspiderTest(BaseGenspiderTest):
    template = 'csvfeed'


class XMLFeedGenspiderTest(BaseGenspiderTest):
    template = 'xmlfeed'


if __name__ == '__main__':
    unittest.main()
