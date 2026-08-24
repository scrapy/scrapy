import warnings
from typing import Any
from unittest.mock import MagicMock

import pytest

from scrapy import Spider, signals
from scrapy.exceptions import NotConfigured, ScrapyDeprecationWarning
from scrapy.statscollectors import StatsCollector
from scrapy.utils.misc import build_from_crawler
from scrapy.utils.spider import DefaultSpider
from scrapy.utils.test import get_crawler

with warnings.catch_warnings():
    warnings.filterwarnings(
        "ignore",
        r"The scrapy\.extensions\.statsmailer module is deprecated",
        ScrapyDeprecationWarning,
    )
    warnings.filterwarnings(
        "ignore",
        r"The scrapy\.mail module is deprecated",
        ScrapyDeprecationWarning,
    )
    from scrapy.extensions import statsmailer
    from scrapy.mail import MailSender


@pytest.fixture
def dummy_stats():
    class DummyStats(StatsCollector):
        def __init__(self) -> None:
            # pylint: disable=super-init-not-called
            self._stats = {"global_item_scraped_count": 42}

        def get_stats(self, spider: Spider | None = None) -> dict[str, Any]:
            return {"item_scraped_count": 10, **self._stats}

    return DummyStats()


def test_from_crawler_without_recipients_raises_notconfigured():
    crawler = MagicMock()
    crawler.settings.getlist.return_value = []
    crawler.stats = MagicMock()

    with pytest.raises(NotConfigured):
        build_from_crawler(statsmailer.StatsMailer, crawler)


def test_from_crawler_with_recipients_initializes_extension(monkeypatch):
    crawler = get_crawler(settings_dict={"STATSMAILER_RCPTS": ["test@example.com"]})

    mailer = MagicMock(spec=MailSender)
    monkeypatch.setattr(MailSender, "from_crawler", lambda _: mailer)

    ext = build_from_crawler(statsmailer.StatsMailer, crawler)

    assert isinstance(ext, statsmailer.StatsMailer)
    assert ext.recipients == ["test@example.com"]
    assert ext.mail is mailer


def test_from_crawler_connects_spider_closed_signal(monkeypatch):
    crawler = get_crawler(settings_dict={"STATSMAILER_RCPTS": ["test@example.com"]})

    mailer = MagicMock(spec=MailSender)
    monkeypatch.setattr(MailSender, "from_crawler", lambda _: mailer)

    ext = build_from_crawler(statsmailer.StatsMailer, crawler)

    crawler.signals.send_catch_log(
        signals.spider_closed, spider=DefaultSpider(name="dummy")
    )
    assert ext.mail.send.call_count == 1


def test_spider_closed_sends_email(dummy_stats):
    recipients = ["test@example.com"]
    mail = MagicMock(spec=MailSender)
    ext = statsmailer.StatsMailer(dummy_stats, recipients, mail)

    spider = DefaultSpider(name="dummy")
    ext.spider_closed(spider)

    args, _ = mail.send.call_args
    to, subject, body = args
    assert to == recipients
    assert "Scrapy stats for: dummy" in subject
    assert "global_item_scraped_count" in body
    assert "item_scraped_count" in body
