"""Test that certain resources are not leaked during earlier tests."""

from __future__ import annotations

import asyncio
import logging

import pytest

from scrapy.utils.log import LogCounterHandler


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


@pytest.mark.only_asyncio
def test_pending_asyncio_tasks() -> None:
    """Test that there are no pending asyncio tasks."""
    assert not asyncio.all_tasks()
