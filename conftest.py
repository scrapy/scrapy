import platform
import sys
from pathlib import Path

import pytest
from twisted import version as twisted_version
from twisted.python.versions import Version
from twisted.web.http import H2_ENABLED

from scrapy.utils.reactor import install_reactor
from tests.keys import generate_keys


def _py_files(folder):
    return (str(p) for p in Path(folder).rglob("*.py"))


collect_ignore = [
    # not a test, but looks like a test
    "scrapy/utils/testsite.py",
    "tests/ftpserver.py",
    "tests/mockserver.py",
    "tests/pipelines.py",
    "tests/spiders.py",
    # contains scripts to be run by tests/test_crawler.py::CrawlerProcessSubprocess
    *_py_files("tests/CrawlerProcess"),
    # contains scripts to be run by tests/test_crawler.py::CrawlerRunnerSubprocess
    *_py_files("tests/CrawlerRunner"),
]

with Path("tests/ignores.txt").open(encoding="utf-8") as reader:
    for line in reader:
        file_path = line.strip()
        if file_path and file_path[0] != "#":
            collect_ignore.append(file_path)

if not H2_ENABLED:
    collect_ignore.extend(
        (
            "scrapy/core/downloader/handlers/http2.py",
            *_py_files("scrapy/core/http2"),
        )
    )


@pytest.fixture()
def chdir(tmpdir):
    """Change to pytest-provided temporary directory"""
    tmpdir.chdir()


def pytest_addoption(parser):
    parser.addoption(
        "--reactor",
        default="default",
        choices=["default", "asyncio"],
    )


@pytest.fixture(scope="class")
def reactor_pytest(request):
    if not request.cls:
        # doctests
        return
    request.cls.reactor_pytest = request.config.getoption("--reactor")
    return request.cls.reactor_pytest


@pytest.fixture(autouse=True)
def only_asyncio(request, reactor_pytest):
    if request.node.get_closest_marker("only_asyncio") and reactor_pytest != "asyncio":
        pytest.skip("This test is only run with --reactor=asyncio")


@pytest.fixture(autouse=True)
def only_not_asyncio(request, reactor_pytest):
    if (
        request.node.get_closest_marker("only_not_asyncio")
        and reactor_pytest == "asyncio"
    ):
        pytest.skip("This test is only run without --reactor=asyncio")


@pytest.fixture(autouse=True)
def requires_uvloop(request):
    if not request.node.get_closest_marker("requires_uvloop"):
        return
    if sys.implementation.name == "pypy":
        pytest.skip("uvloop does not support pypy properly")
    if platform.system() == "Windows":
        pytest.skip("uvloop does not support Windows")
    if twisted_version == Version("twisted", 21, 2, 0):
        pytest.skip("https://twistedmatrix.com/trac/ticket/10106")
    if sys.version_info >= (3, 12):
        pytest.skip("uvloop doesn't support Python 3.12 yet")


def pytest_configure(config):
    if config.getoption("--reactor") == "asyncio":
        install_reactor("twisted.internet.asyncioreactor.AsyncioSelectorReactor")


# Generate localhost certificate files, needed by some tests
generate_keys()
