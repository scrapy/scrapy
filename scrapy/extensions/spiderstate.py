import pickle
from pathlib import Path

from scrapy import signals
from scrapy.exceptions import NotConfigured
from scrapy.utils.job import job_dir


class SpiderState:
    """Store and load spider state during a scraping job"""

    def __init__(self, jobdir=None):
        self.jobdir = jobdir

    @classmethod
    def from_crawler(cls, crawler):
        jobdir = job_dir(crawler.settings)
        if not jobdir:
            raise NotConfigured

        obj = cls(jobdir)
        crawler.signals.connect(obj.spider_closed, signal=signals.spider_closed)
        crawler.signals.connect(obj.spider_opened, signal=signals.spider_opened)
        return obj

    def spider_closed(self, spider):
        if self.jobdir:
            with Path(self.statefn).open("wb") as f:
                pickle.dump(spider.state, f, protocol=4)

    def spider_opened(self, spider):
        if self.jobdir and Path(self.statefn).exists():
            with Path(self.statefn).open("rb") as f:
                spider.state = pickle.load(f)
        else:
            spider.state = {}

    @property
    def statefn(self) -> str:
        return str(Path(self.jobdir, "spider.state"))
