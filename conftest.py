import pytest


collect_ignore = [
    # not a test, but looks like a test
    "scrapy/utils/testsite.py",
]


for line in open('tests/py3-ignores.txt'):
    file_path = line.strip()
    if file_path and file_path[0] != '#':
        collect_ignore.append(file_path)


@pytest.fixture()
def chdir(tmpdir):
    """Change to pytest-provided temporary directory"""
    tmpdir.chdir()


def pytest_collection_modifyitems(session, config, items):
    # Avoid executing tests when executing `--flake8` flag (pytest-flake8)
    try:
        from pytest_flake8 import Flake8Item
        if config.getoption('--flake8'):
            items[:] = [item for item in items if isinstance(item, Flake8Item)]
    except ImportError:
        pass
