import six
import pytest

collect_ignore = ["scrapy/stats.py", "scrapy/project.py"]

if six.PY3:
    for line in open('tests/py3-ignores.txt'):
        file_path = line.strip()
        if len(file_path) > 0 and file_path[0] != '#':
            collect_ignore.append(file_path)


@pytest.fixture()
def chdir(tmpdir):
    """Change to pytest-provided temporary directory"""
    tmpdir.chdir()
