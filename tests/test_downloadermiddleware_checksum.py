from __future__ import annotations

import hashlib
import logging
from gzip import compress
from typing import TYPE_CHECKING, Any

import pytest
from itemadapter import ItemAdapter

from scrapy import Request, Spider, signals
from scrapy.downloadermiddlewares.checksum import ChecksumMiddleware
from scrapy.exceptions import ChecksumError
from scrapy.http import Response
from scrapy.pipelines.files import FilesPipeline
from scrapy.utils.misc import build_from_crawler
from scrapy.utils.test import get_crawler
from tests.test_downloadermiddleware import TestManagerBase
from tests.utils.decorators import coroutine_test

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator
    from pathlib import Path

    from scrapy.pipelines.media import MediaPipeline
    from tests.mockserver.http import MockServer


BODY = b"file content to hash"
SHA256 = hashlib.sha256(BODY).hexdigest()
WRONG_SHA256 = "0" * 64


URL = "https://example.com/file"


def _process(meta: dict[str, Any]) -> Response:
    mw = build_from_crawler(ChecksumMiddleware, get_crawler(Spider))
    return mw.process_response(Request(URL, meta=meta), Response(URL, body=BODY))


def test_no_expected_checksum() -> None:
    assert isinstance(_process({}), Response)


@pytest.mark.parametrize("expected", [SHA256, SHA256.upper(), bytes.fromhex(SHA256)])
def test_match(expected: str | bytes) -> None:
    assert isinstance(_process({"expected_checksum": {"sha256": expected}}), Response)


def test_mismatch() -> None:
    with pytest.raises(ChecksumError, match="sha256"):
        _process({"expected_checksum": {"sha256": WRONG_SHA256}})


def test_every_algorithm_checked() -> None:
    with pytest.raises(ChecksumError, match="sha256"):
        _process(
            {
                "expected_checksum": {
                    "sha512": hashlib.sha512(BODY).hexdigest(),
                    "sha256": WRONG_SHA256,
                }
            }
        )


class TestChain(TestManagerBase):
    settings_dict = {"DOWNLOADER_MIDDLEWARE_RESPONSE_EXCEPTIONS": True}

    @coroutine_test
    async def test_retry(self) -> None:
        req = Request(URL, meta={"expected_checksum": {"sha256": WRONG_SHA256}})
        async with self.get_mwman() as mwman:
            result = await self._download(mwman, req, Response(URL, body=BODY))
        assert isinstance(result, Request)
        assert result.meta["retry_times"] == 1

    @coroutine_test
    async def test_dont_retry(self) -> None:
        req = Request(
            URL,
            meta={"expected_checksum": {"sha256": WRONG_SHA256}, "dont_retry": True},
        )
        async with self.get_mwman() as mwman:
            with pytest.raises(ChecksumError):
                await self._download(mwman, req, Response(URL, body=BODY))

    @coroutine_test
    async def test_compressed(self) -> None:
        req = Request(URL, meta={"expected_checksum": {"sha256": SHA256}})
        resp = Response(URL, body=compress(BODY), headers={"Content-Encoding": "gzip"})
        async with self.get_mwman() as mwman:
            result = await self._download(mwman, req, resp)
        assert isinstance(result, Response)
        assert result.body == BODY


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
    good_url: str
    bad_url: str

    async def start(self) -> AsyncIterator[Request]:
        yield Request(self.good_url)

    def parse(self, response: Response) -> Iterator[Any]:
        yield {
            "file_urls": [self.good_url, self.bad_url],
            "file_sha256": [
                hashlib.sha256(b"Works").hexdigest(),
                WRONG_SHA256,
            ],
        }


@coroutine_test
async def test_files_pipeline(
    mockserver: MockServer, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    items: list[Any] = []

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
