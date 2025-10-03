"""Test that certain resources are not leaked during earlier tests."""

from __future__ import annotations

import logging

from scrapy.utils.log import LogCounterHandler


def test_counter_handler() -> None:
    """Test that LogCounterHandler is always properly removed.

    It's added in Crawler.crawl{,_async}() and removed on engine_stopped.
    """
    c = sum(1 for h in logging.root.handlers if isinstance(h, LogCounterHandler))
    assert c == 0
