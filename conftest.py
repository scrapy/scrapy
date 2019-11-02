import six
import pytest


collect_ignore = [
    # not a test, but looks like a test
    "scrapy/utils/testsite.py",
]


if six.PY3:
    for line in open('tests/py3-ignores.txt'):
        file_path = line.strip()
        if file_path and file_path[0] != '#':
            collect_ignore.append(file_path)


@pytest.fixture()
def chdir(tmpdir):
    """Change to pytest-provided temporary directory"""
    tmpdir.chdir()
