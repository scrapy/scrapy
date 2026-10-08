from __future__ import annotations

import logging
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any

import pytest

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.extensions.feedexport import BlockingFeedStorage, FileFeedStorage
from scrapy.utils.test import get_crawler
from tests.utils.decorators import coroutine_test
from tests.utils.feedexport import crawl_items, path_to_url, printf_escape

if TYPE_CHECKING:
    from scrapy.crawler import Crawler
    from tests.mockserver.http import MockServer


class DelayedFileStorage(BlockingFeedStorage):
    """Feed storage that, like the S3 or GCS ones, can only detect a conflict
    when the feed is delivered, at the end of the crawl or of a batch."""

    supported_modes = frozenset({"append", "create", "overwrite"})

    def __init__(self, uri: str, *, feed_options: dict[str, Any] | None = None):
        self.path = Path(uri.split("://", 1)[1])
        self.mode = (feed_options or {}).get("mode")

    def _store_in_thread(self, file: IO[bytes]) -> None:
        file.seek(0)
        try:
            if self.mode == "create" and self.path.exists():
                raise FileExistsError(str(self.path))
            self.path.write_bytes(file.read())
        finally:
            file.close()


class CreateOnlyFileStorage(FileFeedStorage):
    supported_modes = frozenset({"create"})


class LegacyFileStorage(FileFeedStorage):
    """Feed storage that predates the mode feed option."""

    supported_modes = None  # type: ignore[assignment]


class TestFeedMode:
    """End-to-end tests of the mode feed option and the FEED_MODE setting."""

    @pytest.fixture(autouse=True)
    def _setup(self, mockserver: MockServer, tmp_path: Path) -> None:
        self.mockserver = mockserver
        self.temp_dir = tmp_path

    def _path(self, content: bytes | None = None) -> Path:
        path = self.temp_dir / "items.jl"
        if content is not None:
            path.write_bytes(content)
        return path

    async def _crawl(
        self,
        path: Path,
        mode: str | None = None,
        settings: dict[str, Any] | None = None,
        item_count: int = 1,
        scheme: str | None = None,
    ) -> Crawler:
        feed_options: dict[str, Any] = {"format": "jl"}
        if mode is not None:
            feed_options["mode"] = mode
        if scheme is not None:
            # as_posix() keeps the URI valid on Windows, where paths have a
            # drive and backslashes.
            uri = f"{scheme}://{path.as_posix()}"
        elif "%(batch_id)d" in str(path):
            # A batch URI template must keep its %(batch_id)d placeholder, so it
            # is used as a path, which is neither quoted nor printf-escaped.
            uri = str(path)
        else:
            uri = printf_escape(path_to_url(path))
        return await crawl_items(
            self.mockserver,
            [{"foo": "bar"}] * item_count,
            {"FEEDS": {uri: feed_options}, **(settings or {})},
        )

    @coroutine_test
    async def test_create(self) -> None:
        path = self._path()
        await self._crawl(path, "create")
        assert path.read_bytes() == b'{"foo": "bar"}\n'

    @coroutine_test
    async def test_create_existing(self, caplog: pytest.LogCaptureFixture) -> None:
        path = self._path(b"old content")
        with caplog.at_level(logging.ERROR):
            crawler = await self._crawl(path, "create", item_count=3)
        assert path.read_bytes() == b"old content"
        # Reported once, not once per item.
        assert caplog.text.count("because it already exists") == 1
        assert crawler.stats
        stats = crawler.stats.get_stats()
        assert stats.get("feedexport/conflicts/FileFeedStorage") == 1
        assert "feedexport/success_count/FileFeedStorage" not in stats

    @coroutine_test
    async def test_create_existing_multiple_feeds(self) -> None:
        """A conflicting target only affects its own feed: the crawl runs and
        the other feeds are written."""
        existing = self._path(b"old content")
        missing = self.temp_dir / "missing.jl"
        crawler = await crawl_items(
            self.mockserver,
            [{"foo": "bar"}],
            {
                "FEEDS": {
                    printf_escape(path_to_url(existing)): {"format": "jl"},
                    printf_escape(path_to_url(missing)): {"format": "jl"},
                },
                "FEED_MODE": "create",
            },
        )
        assert existing.read_bytes() == b"old content"
        assert missing.read_bytes() == b'{"foo": "bar"}\n'
        assert crawler.stats
        stats = crawler.stats.get_stats()
        assert stats.get("feedexport/conflicts/FileFeedStorage") == 1
        assert stats.get("feedexport/success_count/FileFeedStorage") == 1
        assert stats.get("finish_reason") == "finished"

    @coroutine_test
    async def test_create_existing_all_feeds(self, caplog: pytest.LogCaptureFixture):
        """A crawl that cannot write any feed still runs, like any other crawl
        whose feeds cannot be written."""
        existing1 = self._path(b"old content")
        existing2 = self.temp_dir / "items2.jl"
        existing2.write_bytes(b"old content")
        with caplog.at_level(logging.ERROR):
            crawler = await crawl_items(
                self.mockserver,
                [{"foo": "bar"}],
                {
                    "FEEDS": {
                        printf_escape(path_to_url(existing1)): {"format": "jl"},
                        printf_escape(path_to_url(existing2)): {"format": "jl"},
                    },
                    "FEED_MODE": "create",
                },
            )
        assert existing1.read_bytes() == b"old content"
        assert existing2.read_bytes() == b"old content"
        assert caplog.text.count("because it already exists") == 2
        assert crawler.stats
        stats = crawler.stats.get_stats()
        assert stats.get("feedexport/conflicts/FileFeedStorage") == 2
        assert stats.get("finish_reason") == "finished"
        assert "feedexport/success_count/FileFeedStorage" not in stats

    @coroutine_test
    async def test_overwrite_existing(self) -> None:
        path = self._path(b"old content")
        await self._crawl(path, "overwrite")
        assert path.read_bytes() == b'{"foo": "bar"}\n'

    @coroutine_test
    async def test_append_existing(self) -> None:
        path = self._path(b"old content\n")
        await self._crawl(path, "append")
        assert path.read_bytes() == b'old content\n{"foo": "bar"}\n'

    @coroutine_test
    async def test_unset_mode(self) -> None:
        path = self._path()
        with pytest.warns(ScrapyDeprecationWarning, match="FEED_MODE"):
            await self._crawl(path, settings={"FEED_MODE": None})
        assert path.read_bytes() == b'{"foo": "bar"}\n'

    @coroutine_test
    async def test_unset_mode_existing_target(self) -> None:
        path = self._path(b"old content\n")
        with pytest.warns(ScrapyDeprecationWarning, match="FEED_MODE"):
            await self._crawl(path, settings={"FEED_MODE": None})
        # The legacy behavior is kept.
        assert path.read_bytes() == b'old content\n{"foo": "bar"}\n'

    @coroutine_test
    async def test_explicit_mode_existing_target(self, recwarn) -> None:
        path = self._path(b"old content\n")
        await self._crawl(path, "append")
        assert not [
            warning
            for warning in recwarn
            if issubclass(warning.category, ScrapyDeprecationWarning)
            and "FEED_MODE" in str(warning.message)
        ]

    @coroutine_test
    async def test_create_existing_later_batch(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """When the target of a later batch exists, that batch is skipped, and
        the following ones are still written."""
        (self.temp_dir / "items-2.jl").write_bytes(b"old content")
        with caplog.at_level(logging.ERROR):
            crawler = await self._crawl(
                self.temp_dir / "items-%(batch_id)d.jl",
                "create",
                {"FEED_EXPORT_BATCH_ITEM_COUNT": 1},
                item_count=3,
            )
        assert (self.temp_dir / "items-1.jl").read_bytes() == b'{"foo": "bar"}\n'
        assert (self.temp_dir / "items-2.jl").read_bytes() == b"old content"
        # The skipped items are counted, so the following batch covers the same
        # items that it would have covered otherwise.
        assert (self.temp_dir / "items-3.jl").read_bytes() == b'{"foo": "bar"}\n'
        assert not (self.temp_dir / "items-4.jl").exists()
        # A single error, instead of one per item after the conflicting one.
        assert caplog.text.count("because it already exists") == 1
        assert crawler.stats
        stats = crawler.stats.get_stats()
        assert stats.get("feedexport/conflicts/FileFeedStorage") == 1
        assert stats.get("feedexport/success_count/FileFeedStorage") == 2
        assert stats.get("finish_reason") == "finished"

    @coroutine_test
    async def test_create_existing_later_batch_delayed(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """When the feed is only delivered at the end of each batch, the
        conflict is detected then, and only that batch is lost."""
        (self.temp_dir / "items-2.jl").write_bytes(b"old content")
        with caplog.at_level(logging.ERROR):
            crawler = await self._crawl(
                self.temp_dir / "items-%(batch_id)d.jl",
                "create",
                {
                    "FEED_EXPORT_BATCH_ITEM_COUNT": 1,
                    "FEED_STORAGES": {
                        "delayed": "tests.test_feedexport_mode.DelayedFileStorage"
                    },
                },
                item_count=3,
                scheme="delayed",
            )
        assert (self.temp_dir / "items-1.jl").read_bytes() == b'{"foo": "bar"}\n'
        assert (self.temp_dir / "items-2.jl").read_bytes() == b"old content"
        assert (self.temp_dir / "items-3.jl").read_bytes() == b'{"foo": "bar"}\n'
        assert caplog.text.count("because it already exists") == 1
        assert crawler.stats
        stats = crawler.stats.get_stats()
        assert stats.get("feedexport/conflicts/DelayedFileStorage") == 1
        assert stats.get("feedexport/failed_count/DelayedFileStorage") == 1
        assert stats.get("feedexport/success_count/DelayedFileStorage") == 2

    @coroutine_test
    async def test_feed_mode_setting(self) -> None:
        path = self._path(b"old content")
        await self._crawl(path, settings={"FEED_MODE": "overwrite"})
        assert path.read_bytes() == b'{"foo": "bar"}\n'

    @coroutine_test
    async def test_mode_overrides_feed_mode_setting(self) -> None:
        path = self._path(b"old content\n")
        await self._crawl(path, "append", {"FEED_MODE": "overwrite"})
        assert path.read_bytes() == b'old content\n{"foo": "bar"}\n'


class TestFeedModeInit:
    def test_invalid_mode(self):
        """An invalid mode prevents the crawl from running."""
        settings = {
            "FEEDS": {"file:///tmp/items.json": {"format": "json", "mode": "x"}}
        }
        with pytest.raises(ValueError, match="Invalid feed mode: 'x'"):
            get_crawler(settings_dict=settings)

    def test_unsupported_mode(self):
        settings = {
            "FEEDS": {"file:///tmp/items.json": {"format": "json"}},
            "FEED_STORAGES": {
                "file": "tests.test_feedexport_mode.CreateOnlyFileStorage"
            },
            "FEED_MODE": "append",
        }
        with pytest.raises(
            ValueError,
            match="CreateOnlyFileStorage does not support the 'append' feed mode",
        ):
            get_crawler(settings_dict=settings)

    def test_undeclared_mode_support(self, caplog: pytest.LogCaptureFixture):
        settings = {
            "FEEDS": {"file:///tmp/items.json": {"format": "json"}},
            "FEED_STORAGES": {"file": "tests.test_feedexport_mode.LegacyFileStorage"},
            "FEED_MODE": "create",
        }
        with caplog.at_level(logging.WARNING):
            get_crawler(settings_dict=settings)
        assert "does not declare which feed modes it supports" in caplog.text

    def test_undeclared_mode_support_unset_mode(self, caplog: pytest.LogCaptureFixture):
        settings = {
            "FEEDS": {"file:///tmp/items.json": {"format": "json"}},
            "FEED_STORAGES": {"file": "tests.test_feedexport_mode.LegacyFileStorage"},
            "FEED_MODE": None,
        }
        with (
            caplog.at_level(logging.WARNING),
            pytest.warns(ScrapyDeprecationWarning, match="FEED_MODE"),
        ):
            get_crawler(settings_dict=settings)
        assert "does not declare which feed modes it supports" not in caplog.text
