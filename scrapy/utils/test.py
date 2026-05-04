"""
This module contains some assorted functions used in tests
"""

from __future__ import annotations

import asyncio
import os
import warnings
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar, cast

from twisted.web.client import Agent

from scrapy.crawler import AsyncCrawlerRunner, CrawlerRunner, CrawlerRunnerBase
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils.reactor import is_asyncio_reactor_installed, is_reactor_installed
from scrapy.utils.spider import DefaultSpider

if TYPE_CHECKING:
    from collections.abc import Awaitable

    from twisted.internet.defer import Deferred
    from twisted.web.client import Response as TxResponse

    from scrapy import Spider
    from scrapy.crawler import Crawler


_T = TypeVar("_T")


def get_reactor_settings() -> dict[str, Any]:
    """Return a settings dict that works with the installed reactor.

    ``Crawler._apply_settings()`` checks that the installed reactor matches the
    settings, so tests that run the crawler in the current process may need to
    pass a correct :setting:`TWISTED_REACTOR` setting value when creating it.
    """
    settings: dict[str, Any] = {}
    if is_reactor_installed():
        if not is_asyncio_reactor_installed():
            settings["TWISTED_REACTOR"] = None
    else:
        # We are either running Scrapy tests for the reactorless mode, or
        # running some 3rd-party library tests for the reactorless mode, or
        # running some 3rd-party library tests without initializing a reactor
        # properly. The first two cases are fine, but we cannot distinguish the
        # last one from them.
        settings["TWISTED_REACTOR_ENABLED"] = False
        settings["DOWNLOAD_HANDLERS"] = {
            "ftp": None,
            "http": "scrapy.core.downloader.handlers._httpx.HttpxDownloadHandler",
            "https": "scrapy.core.downloader.handlers._httpx.HttpxDownloadHandler",
        }
    return settings


def get_crawler(
    spidercls: type[Spider] | None = None,
    settings_dict: dict[str, Any] | None = None,
    prevent_warnings: bool = True,
) -> Crawler:
    """Return an unconfigured Crawler object. If settings_dict is given, it
    will be used to populate the crawler settings with a project level
    priority.
    """
    # When needed, useful settings can be added here, e.g. ones that prevent
    # deprecation warnings.
    settings: dict[str, Any] = {
        **get_reactor_settings(),
        **(settings_dict or {}),
    }
    runner: CrawlerRunnerBase
    if is_reactor_installed():
        runner = CrawlerRunner(settings)
    else:
        runner = AsyncCrawlerRunner(settings)
    crawler = runner.create_crawler(spidercls or DefaultSpider)
    crawler._apply_settings()
    return crawler


def get_pythonpath() -> str:
    """Return a PYTHONPATH suitable to use in processes so that they find this
    installation of Scrapy"""
    scrapy_path = import_module("scrapy").__path__[0]
    return str(Path(scrapy_path).parent) + os.pathsep + os.environ.get("PYTHONPATH", "")


def get_testenv() -> dict[str, str]:
    """Return a OS environment dict suitable to fork processes that need to import
    this installation of Scrapy, instead of a system installed one.
    """
    env = os.environ.copy()
    env["PYTHONPATH"] = get_pythonpath()
    return env


def get_from_asyncio_queue(value: _T) -> Awaitable[_T]:
    q: asyncio.Queue[_T] = asyncio.Queue()
    getter = q.get()
    q.put_nowait(value)
    return getter


def get_web_client_agent_req(url: str) -> Deferred[TxResponse]:  # pragma: no cover
    warnings.warn(
        "The get_web_client_agent_req() function is deprecated"
        " and will be removed in a future version of Scrapy.",
        category=ScrapyDeprecationWarning,
        stacklevel=2,
    )

    from twisted.internet import reactor

    agent = Agent(reactor)
    return cast("Deferred[TxResponse]", agent.request(b"GET", url.encode("utf-8")))
