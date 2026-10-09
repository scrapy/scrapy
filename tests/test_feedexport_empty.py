from __future__ import annotations

import logging
import tempfile
from logging import getLogger
from typing import TYPE_CHECKING

from w3lib.url import file_uri_to_path

from tests.utils.decorators import coroutine_test
from tests.utils.feedexport import export_by_format, unique_path

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

    from tests.mockserver.http import MockServer


class LogOnStoreFileStorage:
    """
    This storage logs inside `store` method.
    It can be used to make sure `store` method is invoked.
    """

    def __init__(self, uri, feed_options=None):
        self.path = file_uri_to_path(uri)
        self.logger = getLogger()

    def open(self, spider):
        return tempfile.NamedTemporaryFile(prefix="feed-")

    def store(self, file):
        self.logger.info("Storage.store is called")
        file.close()


@coroutine_test
async def test_export_no_items_not_store_empty(
    mockserver: MockServer, tmp_path: Path
) -> None:
    for fmt in ("json", "jsonlines", "xml", "csv"):
        settings = {
            "FEEDS": {
                unique_path(tmp_path): {"format": fmt},
            },
            "FEED_STORE_EMPTY": False,
        }
        data = await export_by_format(mockserver, [], settings)
        assert data[fmt] is None


@coroutine_test
async def test_export_no_items_store_empty(
    mockserver: MockServer, tmp_path: Path
) -> None:
    formats = (
        ("json", b"[]"),
        ("jsonlines", b""),
        ("xml", b'<?xml version="1.0" encoding="utf-8"?>\n<items></items>'),
        ("csv", b""),
    )

    for fmt, expctd in formats:
        settings = {
            "FEEDS": {
                unique_path(tmp_path): {"format": fmt},
            },
            "FEED_STORE_EMPTY": True,
            "FEED_EXPORT_INDENT": None,
        }
        data = await export_by_format(mockserver, [], settings)
        assert expctd == data[fmt]


@coroutine_test
async def test_export_no_items_multiple_feeds(
    caplog: pytest.LogCaptureFixture, mockserver: MockServer, tmp_path: Path
) -> None:
    """Make sure that `storage.store` is not called."""
    settings = {
        "FEEDS": {
            unique_path(tmp_path): {"format": "json"},
            unique_path(tmp_path): {"format": "xml"},
            unique_path(tmp_path): {"format": "csv"},
        },
        "FEED_STORAGES": {"file": LogOnStoreFileStorage},
        "FEED_STORE_EMPTY": False,
    }

    with caplog.at_level(logging.INFO):
        await export_by_format(mockserver, [], settings)

    assert caplog.text.count("Storage.store is called") == 0
