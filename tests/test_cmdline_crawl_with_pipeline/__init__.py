from __future__ import annotations

import sys
from pathlib import Path
from subprocess import PIPE, Popen


def _execute(spname: str) -> int:
    args = (sys.executable, "-m", "scrapy.cmdline", "crawl", spname)
    cwd = Path(__file__).resolve().parent
    proc = Popen(args, stdout=PIPE, stderr=PIPE, cwd=cwd)
    proc.communicate()
    return proc.returncode


def test_open_spider_normally_in_pipeline():
    returncode = _execute("normal")
    assert returncode == 0


def test_exception_at_open_spider_in_pipeline():
    returncode = _execute("exception")
    # An exception in pipeline's open_spider should result in a non-zero exit code
    assert returncode == 1
