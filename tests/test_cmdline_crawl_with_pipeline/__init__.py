import sys
from pathlib import Path
from subprocess import PIPE, Popen

class TestCmdlineCrawlPipeline:
    def _execute(self, spname):
        args = (sys.executable, "-m", "scrapy.cmdline", "crawl", spname)
        cwd = Path(__file__).resolve().parent
        proc = Popen(args, stdout=PIPE, stderr=PIPE, cwd=cwd)
        _, stderr = proc.communicate()
        return proc.returncode, stderr

    def test_open_spider_normally_in_pipeline(self):
        returncode, _ = self._execute("normal")
        assert returncode == 0

    def test_exception_at_open_spider_in_pipeline(self):
        returncode, _ = self._execute("exception")
        # An exception in pipeline's open_spider should result in a non-zero exit code
        assert returncode == 1
