from __future__ import annotations

import importlib
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from twisted.web.http import H2_ENABLED

from scrapy.utils.reactor import set_asyncio_event_loop_policy
from tests.keys import generate_keys
from tests.mockserver.http import MockServer

if TYPE_CHECKING:
    from collections.abc import Generator


def _py_files(folder):
    return (str(p) for p in Path(folder).rglob("*.py"))


collect_ignore = [
    # may need extra deps
    "docs/_ext",
    # not a test, but looks like a test
    "scrapy/utils/testproc.py",
    "scrapy/utils/testsite.py",
    "tests/ftpserver.py",
    "tests/mockserver.py",
    "tests/pipelines.py",
    "tests/spiders.py",
    # contains scripts to be run by tests/test_crawler.py::AsyncCrawlerProcessSubprocess
    *_py_files("tests/AsyncCrawlerProcess"),
    # contains scripts to be run by tests/test_crawler.py::AsyncCrawlerRunnerSubprocess
    *_py_files("tests/AsyncCrawlerRunner"),
    # contains scripts to be run by tests/test_crawler.py::CrawlerProcessSubprocess
    *_py_files("tests/CrawlerProcess"),
    # contains scripts to be run by tests/test_crawler.py::CrawlerRunnerSubprocess
    *_py_files("tests/CrawlerRunner"),
]

base_dir = Path(__file__).parent
ignore_file_path = base_dir / "tests" / "ignores.txt"
with ignore_file_path.open(encoding="utf-8") as reader:
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


@pytest.fixture(scope="session")
def mockserver() -> Generator[MockServer]:
    with MockServer() as mockserver:
        yield mockserver


@pytest.fixture(scope="session")
def reactor_pytest(request) -> str:
    return request.config.getoption("--reactor")


def pytest_configure(config):
    if config.getoption("--reactor") == "asyncio":
        # Needed on Windows to switch from proactor to selector for Twisted reactor compatibility.
        # If we decide to run tests with both, we will need to add a new option and check it here.
        set_asyncio_event_loop_policy()


def pytest_runtest_setup(item):
    # Skip tests based on reactor markers
    reactor = item.config.getoption("--reactor")

    if item.get_closest_marker("only_asyncio") and reactor != "asyncio":
        pytest.skip("This test is only run with --reactor=asyncio")

    if item.get_closest_marker("only_not_asyncio") and reactor == "asyncio":
        pytest.skip("This test is only run without --reactor=asyncio")

    # Skip tests requiring optional dependencies
    optional_deps = [
        "uvloop",
        "botocore",
        "boto3",
        "mitmproxy",
    ]

    for module in optional_deps:
        if item.get_closest_marker(f"requires_{module}"):
            try:
                importlib.import_module(module)
            except ImportError:
                pytest.skip(f"{module} is not installed")


# Generate localhost certificate files, needed by some tests
generate_keys()
