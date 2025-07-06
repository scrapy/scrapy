from pathlib import Path

import pytest
from twisted.web.http import H2_ENABLED

from scrapy.utils.reactor import set_asyncio_event_loop_policy
from tests.keys import generate_keys


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
def reactor_pytest(request) -> str:
    return request.config.getoption("--reactor")


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
    try:
        import uvloop  # noqa: PLC0415

        del uvloop
    except ImportError:
        pytest.skip("uvloop is not installed")


@pytest.fixture(autouse=True)
def requires_botocore(request):
    if not request.node.get_closest_marker("requires_botocore"):
        return
    try:
        import botocore  # noqa: PLC0415

        del botocore
    except ImportError:
        pytest.skip("botocore is not installed")


@pytest.fixture(autouse=True)
def requires_boto3(request):
    if not request.node.get_closest_marker("requires_boto3"):
        return
    try:
        import boto3  # noqa: PLC0415

        del boto3
    except ImportError:
        pytest.skip("boto3 is not installed")


def pytest_configure(config):
    if config.getoption("--reactor") == "asyncio":
        # Needed on Windows to switch from proactor to selector for Twisted reactor compatibility.
        # If we decide to run tests with both, we will need to add a new option and check it here.
        set_asyncio_event_loop_policy()


# Generate localhost certificate files, needed by some tests
generate_keys()
