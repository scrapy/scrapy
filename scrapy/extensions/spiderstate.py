from __future__ import annotations

import pickle
import warnings
from pathlib import Path
from typing import TYPE_CHECKING

from scrapy import Spider, signals
from scrapy.exceptions import NotConfigured, ScrapyDeprecationWarning
from scrapy.utils.job import job_dir

if TYPE_CHECKING:
    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.crawler import Crawler


class SpiderState:
    """Store and load spider state during a scraping job"""

    def __init__(self, jobdir: str | None = None):
        self.jobdir: str | None = jobdir
        self.crawler: Crawler | None = None

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        jobdir = job_dir(crawler.settings)
        if not jobdir:
            raise NotConfigured

        obj = cls(jobdir)
        obj.crawler = crawler
        crawler.signals.connect(obj._spider_closed, signal=signals.spider_closed)
        crawler.signals.connect(obj._spider_opened, signal=signals.spider_opened)
        return obj

    def _load_state(self, spider: Spider) -> None:
        if Path(self.statefn).exists():
            with Path(self.statefn).open("rb") as f:
                spider.state = pickle.load(f)  # type: ignore[attr-defined]  # noqa: S301
        else:
            spider.state = {}  # type: ignore[attr-defined]

    def _persist_state(self, spider: Spider) -> None:
        with Path(self.statefn).open("wb") as f:
            assert hasattr(spider, "state")
            pickle.dump(spider.state, f, protocol=4)

    async def _spider_opened(self, spider: Spider) -> None:
        self._load_state(spider)
        assert self.crawler is not None
        await self.crawler.signals.send_catch_log_async(
            signals.spider_state_loaded,
            state=spider.state,  # type: ignore[attr-defined]
        )

    async def _spider_closed(self, spider: Spider) -> None:
        assert self.crawler is not None
        await self.crawler.signals.send_catch_log_async(
            signals.spider_state_saving,
            state=spider.state,  # type: ignore[attr-defined]
        )
        self._persist_state(spider)

    def spider_opened(self, spider: Spider) -> None:
        warnings.warn(
            f"{type(self).__qualname__}.spider_opened() is deprecated, "
            "use the spider_state_loaded signal instead.",
            category=ScrapyDeprecationWarning,
            stacklevel=2,
        )
        self._load_state(spider)
        assert self.crawler is not None
        self.crawler.signals.send_catch_log(
            signals.spider_state_loaded,
            state=spider.state,  # type: ignore[attr-defined]
        )

    def spider_closed(self, spider: Spider) -> None:
        warnings.warn(
            f"{type(self).__qualname__}.spider_closed() is deprecated, "
            "use the spider_state_saving signal instead.",
            category=ScrapyDeprecationWarning,
            stacklevel=2,
        )
        assert self.crawler is not None
        self.crawler.signals.send_catch_log(
            signals.spider_state_saving,
            state=spider.state,  # type: ignore[attr-defined]
        )
        self._persist_state(spider)

    @property
    def statefn(self) -> str:
        assert self.jobdir
        return str(Path(self.jobdir, "spider.state"))
