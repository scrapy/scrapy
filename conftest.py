import glob
import six
import pytest
from twisted import version as twisted_version


def _py_files(folder):
    return glob.glob(folder + "/*.py") + glob.glob(folder + "/*/*.py")


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
    for line in open('tests/py3-ignores.txt'):
        file_path = line.strip()
        if file_path and file_path[0] != '#':
            collect_ignore.append(file_path)


@pytest.fixture()
def chdir(tmpdir):
    """Change to pytest-provided temporary directory"""
    tmpdir.chdir()
