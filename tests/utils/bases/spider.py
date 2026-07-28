from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any
from unittest import mock

import pytest

from scrapy import signals
from scrapy.crawler import Crawler
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.settings import Settings
from scrapy.utils.test import get_crawler, get_reactor_settings
from tests.utils.decorators import inline_callbacks_test

if TYPE_CHECKING:
    from scrapy.spiders import Spider


class TestSpiderBase(ABC):
    @property
    @abstractmethod
    def spider_class(self) -> type[Spider]:
        raise NotImplementedError

    def test_base_spider(self):
        spider = self.spider_class("example.com")
        assert spider.name == "example.com"
        assert spider.start_urls == []

    def test_spider_args(self):
        """``__init__`` method arguments are assigned to spider attributes"""
        spider = self.spider_class("example.com", foo="bar")
        assert spider.foo == "bar"

    def test_spider_without_name(self):
        """``__init__`` raises when the name is not provided."""
        msg = "must have a name"
        with pytest.raises(ValueError, match=msg):
            self.spider_class()
        with pytest.raises(ValueError, match=msg):
            self.spider_class(somearg="foo")

    def test_from_crawler_crawler_and_settings_population(self):
        crawler = get_crawler()
        spider = self.spider_class.from_crawler(crawler, "example.com")
        assert hasattr(spider, "crawler")
        assert spider.crawler is crawler
        assert hasattr(spider, "settings")
        assert spider.settings is crawler.settings

    def test_from_crawler_init_call(self):
        with mock.patch.object(
            self.spider_class, "__init__", return_value=None
        ) as mock_init:
            self.spider_class.from_crawler(get_crawler(), "example.com", foo="bar")
            mock_init.assert_called_once_with("example.com", foo="bar")

    def test_closed_signal_call(self):
        class TestSpider(self.spider_class):
            closed_called = False

            def closed(self, reason):
                self.closed_called = True

        crawler = get_crawler()
        spider = TestSpider.from_crawler(crawler, "example.com")
        crawler.signals.send_catch_log(signal=signals.spider_opened, spider=spider)
        crawler.signals.send_catch_log(
            signal=signals.spider_closed, spider=spider, reason=None
        )
        assert spider.closed_called

    def test_update_settings(self):
        spider_settings = {"TEST1": "spider", "TEST2": "spider"}
        project_settings = {"TEST1": "project", "TEST3": "project"}
        self.spider_class.custom_settings = spider_settings
        settings = Settings(project_settings, priority="project")

        self.spider_class.update_settings(settings)
        assert settings.get("TEST1") == "spider"
        assert settings.get("TEST2") == "spider"
        assert settings.get("TEST3") == "project"

    @inline_callbacks_test
    def test_settings_in_from_crawler(self):
        spider_settings = {"TEST1": "spider", "TEST2": "spider"}
        project_settings = {
            "TEST1": "project",
            "TEST3": "project",
            **get_reactor_settings(),
        }

        class TestSpider(self.spider_class):
            name = "test"
            custom_settings = spider_settings

            @classmethod
            def from_crawler(cls, crawler: Crawler, *args: Any, **kwargs: Any):
                spider = super().from_crawler(crawler, *args, **kwargs)
                spider.settings.set("TEST1", "spider_instance", priority="spider")
                return spider

        crawler = Crawler(TestSpider, project_settings)
        assert crawler.settings.get("TEST1") == "spider"
        assert crawler.settings.get("TEST2") == "spider"
        assert crawler.settings.get("TEST3") == "project"
        yield crawler.crawl()
        assert crawler.settings.get("TEST1") == "spider_instance"

    def test_logger(self, caplog: pytest.LogCaptureFixture) -> None:
        spider = self.spider_class("example.com")
        caplog.clear()
        with caplog.at_level(logging.INFO):
            spider.logger.info("test log msg")
        assert caplog.record_tuples == [("example.com", logging.INFO, "test log msg")]

        record = caplog.records[0]
        assert getattr(record, "spider", None) is spider

    def test_log(self):
        spider = self.spider_class("example.com")
        with (
            mock.patch("scrapy.spiders.Spider.logger") as mock_logger,
            pytest.warns(
                ScrapyDeprecationWarning, match=r"Spider.log\(\) is deprecated"
            ),
        ):
            spider.log("test log msg", "INFO")
        mock_logger.log.assert_called_once_with("INFO", "test log msg")
