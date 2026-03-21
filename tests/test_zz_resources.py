"""Test that certain resources are not leaked during earlier tests."""

from __future__ import annotations

import asyncio
import logging

import pytest

from scrapy.utils.log import LogCounterHandler
from scrapy.utils.reactor import is_asyncio_reactor_installed, is_reactor_installed


def test_counter_handler() -> None:
    """Test that ``LogCounterHandler`` is always properly removed.

    It's added in ``Crawler.crawl{,_async}()`` and removed on engine_stopped.
    """
    c = sum(1 for h in logging.root.handlers if isinstance(h, LogCounterHandler))
    assert c == 0


def test_stderr_log_handler() -> None:
    """Test that the Scrapy root handler is always properly removed.

    It's added in ``configure_logging()``, called by ``{Async,}CrawlerProcess``
    (without ``install_root_handler=False``). It can be removed with
    ``_uninstall_scrapy_root_handler()`` if installing it was really neeeded.
    """
    c = sum(1 for h in logging.root.handlers if type(h) is logging.StreamHandler)  # pylint: disable=unidiomatic-typecheck
    assert c == 0


@pytest.mark.requires_reactor  # needs a running event loop for asyncio.all_tasks()
@pytest.mark.only_asyncio
def test_pending_asyncio_tasks() -> None:
    """Test that there are no pending asyncio tasks."""
    assert not asyncio.all_tasks()


def test_installed_reactor(reactor_pytest: str) -> None:
    """Test that the correct reactor is installed."""
    match reactor_pytest:
        case "asyncio":
            assert is_asyncio_reactor_installed()
        case "default":
            assert not is_asyncio_reactor_installed()
        case "none":
            assert not is_reactor_installed()
