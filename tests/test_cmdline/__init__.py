import sys
from subprocess import Popen, PIPE
import unittest

from scrapy.utils.test import get_testenv

class CmdlineTest(unittest.TestCase):

    def setUp(self):
        self.env = get_testenv()
        self.env['SCRAPY_SETTINGS_MODULE'] = 'tests.test_cmdline.settings'

    def _execute(self, *new_args, **kwargs):
        encoding = getattr(sys.stdout, 'encoding') or 'utf-8'
        args = (sys.executable, '-m', 'scrapy.cmdline') + new_args
        proc = Popen(args, stdout=PIPE, stderr=PIPE, env=self.env, **kwargs)
        comm = proc.communicate()[0].strip()
        return comm.decode(encoding)

    def test_default_settings(self):
        self.assertEqual(self._execute('settings', '--get', 'TEST1'), \
                         'default')

    def test_override_settings_using_set_arg(self):
        self.assertEqual(self._execute('settings', '--get', 'TEST1', '-s', 'TEST1=override'), \
                         'override')

    def test_override_settings_using_envvar(self):
        self.env['SCRAPY_TEST1'] = 'override'
        self.assertEqual(self._execute('settings', '--get', 'TEST1'), \
                         'override')

