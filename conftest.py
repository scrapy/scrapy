import glob
import six
import pytest


def _py_files(folder):
    return glob.glob(folder + "/*.py") + glob.glob(folder + "/*/*.py")


collect_ignore = [
    "scrapy/conf.py",
    "scrapy/stats.py",
    "scrapy/project.py",
    "scrapy/utils/decorator.py",
    "scrapy/statscol.py",
    "scrapy/squeue.py",
    "scrapy/log.py",
    "scrapy/dupefilter.py",
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
