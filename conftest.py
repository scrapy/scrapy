from __future__ import annotations

import os
from importlib.util import find_spec
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from twisted.web.http import H2_ENABLED

from scrapy.core.engine import ExecutionEngine
from scrapy.utils.reactor import set_asyncio_event_loop_policy
from scrapy.utils.reactorless import install_reactor_import_hook
from tests.keys import generate_keys
from tests.mockserver.http import MockServer
from tests.mockserver.mitm_proxy import MitmProxy, mitmdump_cmd

if TYPE_CHECKING:
    from collections.abc import Generator


def _py_files(folder):
    return (str(p) for p in Path(folder).rglob("*.py"))


collect_ignore = [
    # may need extra deps
    "docs/_ext",
    # contains scripts to be run by tests/test_crawler_subprocess.py::AsyncCrawlerProcessSubprocess
    *_py_files("tests/AsyncCrawlerProcess"),
    # contains scripts to be run by tests/test_crawler_subprocess.py::AsyncCrawlerRunnerSubprocess
    *_py_files("tests/AsyncCrawlerRunner"),
    # contains scripts to be run by tests/test_crawler_subprocess.py::CrawlerProcessSubprocess
    *_py_files("tests/CrawlerProcess"),
    # contains scripts to be run by tests/test_crawler_subprocess.py::CrawlerRunnerSubprocess
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
            *_py_files("scrapy/core/_http2"),
        )
    )

if find_spec("httpx2") is None and find_spec("httpx") is None:
    collect_ignore.append("scrapy/core/downloader/handlers/_httpx.py")

if find_spec("pytest_codspeed") is None:
    collect_ignore.append("tests/benchmarks")


def pytest_addoption(parser, pluginmanager):
    if pluginmanager.hasplugin("twisted"):
        return
    # add the full choice set so that pytest doesn't complain about invalid choices in some cases
    parser.addoption(
        "--reactor",
        default="none",
        choices=["asyncio", "default", "none"],
    )


@pytest.fixture(autouse=True)
def fast_engine_heartbeat(monkeypatch: pytest.MonkeyPatch) -> None:
    """Shorten the interval at which the engine checks for work while idle.

    Whenever nothing else wakes the engine up, e.g. while a component sleeps,
    it stays idle until its next heartbeat, so tests that go through that wait
    pay the whole interval.
    """
    monkeypatch.setattr(ExecutionEngine, "_SLOT_HEARTBEAT_INTERVAL", 0.1)


@pytest.fixture(scope="session")
def mockserver() -> Generator[MockServer]:
    with MockServer() as mockserver:
        yield mockserver


@pytest.fixture(scope="session")
def _mitm_proxies() -> Generator[dict[str, tuple[MitmProxy, str]]]:
    proxies: dict[str, tuple[MitmProxy, str]] = {}
    try:
        yield proxies
    finally:
        for proxy, _url in proxies.values():
            proxy.stop()


@pytest.fixture  # function scope because it modifies os.environ
def proxy_server(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
    _mitm_proxies: dict[str, tuple[MitmProxy, str]],
) -> str:
    kind: str = request.param
    if kind not in _mitm_proxies:
        proxy = MitmProxy(mode="socks5" if kind == "socks5" else None)
        _mitm_proxies[kind] = (proxy, proxy.start())
    _, url = _mitm_proxies[kind]
    if kind == "https":
        url = url.replace("http://", "https://")
    monkeypatch.setenv("http_proxy", url)
    monkeypatch.setenv("https_proxy", url)
    return kind


@pytest.fixture(scope="session")
def reactor_pytest(request) -> str:
    return request.config.getoption("--reactor")


def pytest_configure(config):
    if config.getoption("--reactor") in {"asyncio", "none"}:
        # Needed on Windows to switch from proactor to selector, which supports
        # add_reader/add_writer (required by the Twisted asyncio reactor, and by
        # tests that register their own readers) and is what Twisted expects.
        set_asyncio_event_loop_policy()
    if config.getoption("--reactor") == "none":
        install_reactor_import_hook()


def pytest_collection_modifyitems(items):
    for item in items:
        if item.get_closest_marker("requires_internet"):
            # Requests to real websites fail every now and then in CI for
            # reasons unrelated to the code under test.
            item.add_marker(pytest.mark.flaky(reruns=2, reruns_delay=5))


def pytest_runtest_setup(item):
    # Skip tests based on reactor markers
    reactor = item.config.getoption("--reactor")

    if item.get_closest_marker("requires_reactor") and reactor == "none":
        pytest.skip('This test is only run when the --reactor value is not "none"')

    if item.get_closest_marker("only_asyncio") and reactor not in {"asyncio", "none"}:
        pytest.skip(
            'This test is only run when the --reactor value is "asyncio" (default) or "none"'
        )

    if item.get_closest_marker("only_not_asyncio") and reactor in {"asyncio", "none"}:
        pytest.skip(
            'This test is only run when the --reactor value is not "asyncio" (default) or "none"'
        )

    # Skip tests requiring optional dependencies
    optional_deps = [
        "uvloop",
        "botocore",
        "boto3",
        "aiobotocore",
        "aioboto3",
    ]

    for module in optional_deps:
        if item.get_closest_marker(f"requires_{module}") and find_spec(module) is None:
            pytest.skip(f"{module} is not installed")

    if item.get_closest_marker("requires_mitmproxy") and mitmdump_cmd() is None:
        pytest.skip("mitmdump is not available")


# Generate localhost certificate files, needed by some tests (but only once if xdist is used)
if "PYTEST_XDIST_WORKER" not in os.environ:
    generate_keys()
