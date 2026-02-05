from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from scrapy.utils.test import get_crawler
from tests.spiders import SimpleSpider
from tests.utils.decorators import coroutine_test

if TYPE_CHECKING:
    from tests.mockserver.http import MockServer


@pytest.mark.requires_http_handler
@coroutine_test
async def test_scraper_exception(
    mockserver: MockServer,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    crawler = get_crawler(SimpleSpider)
    monkeypatch.setattr(
        "scrapy.core.engine.Scraper.handle_spider_output_async",
        lambda *args, **kwargs: 1 / 0,
    )
    await crawler.crawl_async(url=mockserver.url("/"))
    assert "Scraper bug processing" in caplog.text
