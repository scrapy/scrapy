from unittest.mock import MagicMock

import pytest

from scrapy import signals
from scrapy.exceptions import NotConfigured
from scrapy.extensions import statsmailer
from scrapy.mail import MailSender
from scrapy.signalmanager import SignalManager
from scrapy.statscollectors import StatsCollector
from scrapy.utils.spider import DefaultSpider


@pytest.fixture
def dummy_stats():
    class DummyStats(StatsCollector):
        def __init__(self):
            # pylint: disable=super-init-not-called
            self._stats = {"global_item_scraped_count": 42}

        def get_stats(self):
            return {"item_scraped_count": 10, **self._stats}

    return DummyStats()


def test_from_crawler_without_recipients_raises_notconfigured():
    crawler = MagicMock()
    crawler.settings.getlist.return_value = []
    crawler.stats = MagicMock()

    with pytest.raises(NotConfigured):
        statsmailer.StatsMailer.from_crawler(crawler)


def test_from_crawler_with_recipients_initializes_extension(dummy_stats, monkeypatch):
    crawler = MagicMock()
    crawler.settings.getlist.return_value = ["test@example.com"]
    crawler.stats = dummy_stats
    crawler.signals = SignalManager(crawler)

    mailer = MagicMock(spec=MailSender)
    monkeypatch.setattr(statsmailer.MailSender, "from_crawler", lambda _: mailer)

    ext = statsmailer.StatsMailer.from_crawler(crawler)

    assert isinstance(ext, statsmailer.StatsMailer)
    assert ext.recipients == ["test@example.com"]
    assert ext.mail is mailer


def test_from_crawler_connects_spider_closed_signal(dummy_stats, monkeypatch):
    crawler = MagicMock()
    crawler.settings.getlist.return_value = ["test@example.com"]
    crawler.stats = dummy_stats
    crawler.signals = SignalManager(crawler)

    mailer = MagicMock(spec=MailSender)
    monkeypatch.setattr(statsmailer.MailSender, "from_crawler", lambda _: mailer)

    statsmailer.StatsMailer.from_crawler(crawler)

    connected = crawler.signals.send_catch_log(
        signals.spider_closed, spider=DefaultSpider(name="dummy")
    )
    assert connected is not None


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
