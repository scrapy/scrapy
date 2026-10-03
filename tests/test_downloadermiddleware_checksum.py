from __future__ import annotations

import hashlib
import logging
from typing import TYPE_CHECKING, Any

import pytest
from itemadapter import ItemAdapter

from scrapy import Request, Spider, signals
from scrapy.downloadermiddlewares.checksum import ChecksumMiddleware
from scrapy.exceptions import ChecksumError
from scrapy.http import Response
from scrapy.pipelines.files import FilesPipeline
from scrapy.utils.spider import DefaultSpider
from scrapy.utils.test import get_crawler
from tests.utils.decorators import coroutine_test

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator
    from pathlib import Path

    from scrapy.pipelines.media import MediaPipeline
    from tests.mockserver.http import MockServer


BODY = b"file content to hash"
SHA256 = hashlib.sha256(BODY).hexdigest()
WRONG_SHA256 = "0" * 64


class TestChecksumMiddleware:
    def setup_method(self) -> None:
        self.crawler = get_crawler(DefaultSpider, {"RETRY_TIMES": 1})
        self.crawler.spider = self.crawler._create_spider()
        self.mw = ChecksumMiddleware.from_crawler(self.crawler)

    def _process(self, meta: dict[str, Any]) -> Request | Response:
        return self.mw.process_response(
            Request("https://example.com/file", meta=meta),
            Response("https://example.com/file", body=BODY),
        )

    def test_no_expected_checksum(self) -> None:
        assert isinstance(self._process({}), Response)

    @pytest.mark.parametrize(
        "expected", [SHA256, SHA256.upper(), bytes.fromhex(SHA256)]
    )
    def test_match(self, expected: str | bytes) -> None:
        result = self._process({"expected_checksum": {"sha256": expected}})
        assert isinstance(result, Response)

    def test_mismatch_retries(self) -> None:
        result = self._process({"expected_checksum": {"sha256": WRONG_SHA256}})
        assert isinstance(result, Request)
        assert result.meta["retry_times"] == 1
        assert self.crawler.stats
        assert self.crawler.stats.get_value("retry/reason_count/checksum/sha256") == 1

    def test_mismatch_gives_up(self) -> None:
        with pytest.raises(ChecksumError, match="sha256"):
            self._process(
                {"expected_checksum": {"sha256": WRONG_SHA256}, "retry_times": 1}
            )

    def test_dont_retry(self) -> None:
        with pytest.raises(ChecksumError, match="sha256"):
            self._process(
                {"expected_checksum": {"sha256": WRONG_SHA256}, "dont_retry": True}
            )

    def test_every_algorithm_checked(self) -> None:
        with pytest.raises(ChecksumError, match="sha256"):
            self._process(
                {
                    "expected_checksum": {
                        "sha512": hashlib.sha512(BODY).hexdigest(),
                        "sha256": WRONG_SHA256,
                    },
                    "dont_retry": True,
                }
            )


class ChecksumFilesPipeline(FilesPipeline):
    def get_media_requests(
        self, item: Any, info: MediaPipeline.SpiderInfo
    ) -> list[Request]:
        adapter = ItemAdapter(item)
        return [
            Request(url, meta={"expected_checksum": {"sha256": checksum}})
            for url, checksum in zip(
                adapter["file_urls"], adapter["file_sha256"], strict=True
            )
        ]


class FileItemSpider(Spider):
    name = "file_item"

    async def start(self) -> AsyncIterator[Request]:
        yield Request(self.good_url)  # type: ignore[attr-defined]

    def parse(self, response: Response) -> Iterator[Any]:
        yield {
            "file_urls": [self.good_url, self.bad_url],  # type: ignore[attr-defined]
            "file_sha256": [
                hashlib.sha256(b"Works").hexdigest(),
                WRONG_SHA256,
            ],
        }


class TestMediaPipelineIntegration:
    @coroutine_test
    async def test_files_pipeline(
        self, mockserver: MockServer, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        items = []

        def _on_item_scraped(item: Any) -> None:
            items.append(item)

        crawler = get_crawler(
            FileItemSpider,
            {
                "FILES_STORE": str(tmp_path),
                "ITEM_PIPELINES": {ChecksumFilesPipeline: 1},
                "RETRY_TIMES": 0,
            },
        )
        crawler.signals.connect(_on_item_scraped, signals.item_scraped)
        with caplog.at_level(logging.WARNING):
            await crawler.crawl_async(
                good_url=mockserver.url("/text"),
                bad_url=mockserver.url("/html"),
            )

        assert len(items) == 1
        assert [file["url"] for file in items[0]["files"]] == [mockserver.url("/text")]
        assert "does not match the expected checksum" in caplog.text
        assert len(list(tmp_path.glob("full/*"))) == 1
