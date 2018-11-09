import glob
import sys

import six
import pytest
from twisted import version as twisted_version


def _py_files(folder):
    return glob.glob(folder + "/*.py") + glob.glob(folder + "/*/*.py")


def _parse_ignores(path):
    with open(path, 'rt') as f:
        for line in f:
            file_path = line.strip()
            if file_path and file_path[0] != '#':
                yield file_path


collect_ignore = [
    # deprecated or moved modules
    "scrapy/conf.py",
    "scrapy/log.py",

    # not a test, but looks like a test
    "scrapy/utils/testsite.py",

]

if (twisted_version.major, twisted_version.minor, twisted_version.micro) >= (15, 5, 0):
    collect_ignore += _py_files("scrapy/xlib/tx")


if six.PY3:
    collect_ignore.extend(_parse_ignores('tests/py3-ignores.txt'))

if sys.version_info[:2] < (3, 6):
    collect_ignore.extend(_parse_ignores('tests/pre-py36-ignores.txt'))


@pytest.fixture()
def chdir(tmpdir):
    """Change to pytest-provided temporary directory"""
    tmpdir.chdir()
