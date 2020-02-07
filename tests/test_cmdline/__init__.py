import json
import os
import pstats
import shutil
import sys
import tempfile
import unittest
from io import StringIO
from subprocess import Popen, PIPE

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
        self.assertEqual(self._execute('settings', '--get', 'TEST1'), 'default')

    def test_override_settings_using_set_arg(self):
        self.assertEqual(self._execute('settings', '--get', 'TEST1', '-s',
                                       'TEST1=override'), 'override')

    def test_override_settings_using_envvar(self):
        self.env['SCRAPY_TEST1'] = 'override'
        self.assertEqual(self._execute('settings', '--get', 'TEST1'), 'override')

    def test_profiling(self):
        path = tempfile.mkdtemp()
        filename = os.path.join(path, 'res.prof')
        try:
            self._execute('version', '--profile', filename)
            self.assertTrue(os.path.exists(filename))
            out = StringIO()
            stats = pstats.Stats(filename, stream=out)
            stats.print_stats()
            out.seek(0)
            stats = out.read()
            self.assertIn(os.path.join('scrapy', 'commands', 'version.py'),
                          stats)
            self.assertIn('tottime', stats)
        finally:
            shutil.rmtree(path)

    def test_override_dict_settings(self):
        EXT_PATH = "tests.test_cmdline.extensions.DummyExtension"
        EXTENSIONS = {EXT_PATH: 200}
        settingsstr = self._execute('settings', '--get', 'EXTENSIONS', '-s',
                                    'EXTENSIONS=' + json.dumps(EXTENSIONS))
        # XXX: There's gotta be a smarter way to do this...
        self.assertNotIn("...", settingsstr)
        for char in ("'", "<", ">", 'u"'):
            settingsstr = settingsstr.replace(char, '"')
        settingsdict = json.loads(settingsstr)
        self.assertCountEqual(settingsdict.keys(), EXTENSIONS.keys())
        self.assertEqual(200, settingsdict[EXT_PATH])
