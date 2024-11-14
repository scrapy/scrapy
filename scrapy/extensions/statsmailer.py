"""
StatsMailer extension sends an email when a spider finishes scraping.

Use STATSMAILER_RCPTS setting to enable and give the recipient mail address
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from scrapy import Spider, signals
from scrapy.exceptions import NotConfigured
from scrapy.mail import MailSender

if TYPE_CHECKING:
    from twisted.internet.defer import Deferred

    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.crawler import Crawler
    from scrapy.statscollectors import StatsCollector


class StatsMailer:
    def __init__(self, stats: StatsCollector, recipients: list[str], mail: MailSender):
        self.stats: StatsCollector = stats
        self.recipients: list[str] = recipients
        self.mail: MailSender = mail

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        recipients: list[str] = crawler.settings.getlist("STATSMAILER_RCPTS")
        if not recipients:
            raise NotConfigured
        mail: MailSender = MailSender.from_crawler(crawler)
        assert crawler.stats
        o = cls(crawler.stats, recipients, mail)
        crawler.signals.connect(o.spider_closed, signal=signals.spider_closed)
        return o

    def spider_closed(self, spider: Spider) -> Deferred[None] | None:
        spider_stats = self.stats.get_stats(spider)
        body = "Global stats\n\n"
        body += "\n".join(f"{k:<50} : {v}" for k, v in self.stats.get_stats().items())
        body += f"\n\n{spider.name} stats\n\n"
        body += "\n".join(f"{k:<50} : {v}" for k, v in spider_stats.items())
        return self.mail.send(self.recipients, f"Scrapy stats for: {spider.name}", body)
