from pathlib import Path

import pytest

from tests.keys import generate_keys


def _py_files(folder):
    return (str(p) for p in Path(folder).rglob('*.py'))


collect_ignore = [
    # not a test, but looks like a test
    "scrapy/utils/testsite.py",
    # contains scripts to be run by tests/test_crawler.py::CrawlerProcessSubprocess
    *_py_files("tests/CrawlerProcess"),
    # contains scripts to be run by tests/test_crawler.py::CrawlerRunnerSubprocess
    *_py_files("tests/CrawlerRunner"),
]

for line in open('tests/ignores.txt'):
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


@pytest.fixture(scope='class')
def reactor_pytest(request):
    if not request.cls:
        # doctests
        return
    request.cls.reactor_pytest = request.config.getoption("--reactor")
    return request.cls.reactor_pytest


@pytest.fixture(autouse=True)
def only_asyncio(request, reactor_pytest):
    if request.node.get_closest_marker('only_asyncio') and reactor_pytest != 'asyncio':
        pytest.skip('This test is only run with --reactor=asyncio')


# Generate localhost certificate files, needed by some tests
generate_keys()
