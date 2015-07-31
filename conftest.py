import glob
import six
import pytest


def _py_files(folder):
    return glob.glob(folder + "/*.py") + glob.glob(folder + "/*/*.py")


collect_ignore = [
    # deprecated or moved modules
    "scrapy/conf.py",
    "scrapy/stats.py",
    "scrapy/project.py",
    "scrapy/utils/decorator.py",
    "scrapy/statscol.py",
    "scrapy/squeue.py",
    "scrapy/log.py",
    "scrapy/dupefilter.py",
    "scrapy/command.py",
    "scrapy/linkextractor.py",
    "scrapy/spider.py",

    # not a test, but looks like a test
    "scrapy/utils/testsite.py",

] + _py_files("scrapy/contrib") + _py_files("scrapy/contrib_exp")


if six.PY3:
    for line in open('tests/py3-ignores.txt'):
        file_path = line.strip()
        if len(file_path) > 0 and file_path[0] != '#':
            collect_ignore.append(file_path)


@pytest.fixture()
def chdir(tmpdir):
    """Change to pytest-provided temporary directory"""
    tmpdir.chdir()
