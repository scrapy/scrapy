from __future__ import annotations

import pickle  # nosec
from pathlib import Path
from typing import TYPE_CHECKING

from scrapy import Spider, signals
from scrapy.exceptions import NotConfigured
from scrapy.utils.job import job_dir

if TYPE_CHECKING:
    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.crawler import Crawler


class SpiderState:
    """Store and load spider state during a scraping job"""

    def __init__(self, jobdir: str | None = None):
        self.jobdir: str | None = jobdir

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        jobdir = job_dir(crawler.settings)
        if not jobdir:
            raise NotConfigured

        obj = cls(jobdir)
        crawler.signals.connect(obj.spider_closed, signal=signals.spider_closed)
        crawler.signals.connect(obj.spider_opened, signal=signals.spider_opened)
        return obj

    def spider_closed(self, spider: Spider) -> None:
        if self.jobdir:
            with Path(self.statefn).open("wb") as f:
                assert hasattr(spider, "state")  # set in spider_opened
                pickle.dump(spider.state, f, protocol=4)

    def spider_opened(self, spider: Spider) -> None:
        if self.jobdir and Path(self.statefn).exists():
            with Path(self.statefn).open("rb") as f:
                spider.state = pickle.load(f)  # type: ignore[attr-defined]  # nosec
        else:
            spider.state = {}  # type: ignore[attr-defined]

    @property
    def statefn(self) -> str:
        assert self.jobdir
        return str(Path(self.jobdir, "spider.state"))
