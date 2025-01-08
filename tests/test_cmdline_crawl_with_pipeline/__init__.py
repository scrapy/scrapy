import sys
import unittest
from pathlib import Path
from subprocess import PIPE, Popen


class CmdlineCrawlPipelineTest(unittest.TestCase):
    def _execute(self, spname):
        args = (sys.executable, "-m", "scrapy.cmdline", "crawl", spname)
        cwd = Path(__file__).resolve().parent
        proc = Popen(args, stdout=PIPE, stderr=PIPE, cwd=cwd)
        proc.communicate()
        return proc.returncode

    def test_open_spider_normally_in_pipeline(self):
        self.assertEqual(self._execute("normal"), 0)

    def test_exception_at_open_spider_in_pipeline(self):
        self.assertEqual(self._execute("exception"), 1)
