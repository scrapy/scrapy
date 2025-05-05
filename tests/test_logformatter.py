import logging

import pytest
from testfixtures import LogCapture
from twisted.internet import defer
from twisted.python.failure import Failure
from twisted.trial.unittest import TestCase

from scrapy.exceptions import DropItem
from scrapy.http import Request, Response
from scrapy.item import Field, Item
from scrapy.logformatter import LogFormatter
from scrapy.spiders import Spider
from scrapy.utils.test import get_crawler
from tests.mockserver import MockServer
from tests.spiders import ItemSpider


class CustomItem(Item):
    name = Field()

    def __str__(self):
        return f"name: {self['name']}"


class TestLogFormatter:
    def setup_method(self):
        self.formatter = LogFormatter()
        self.spider = Spider("default")
        self.spider.crawler = get_crawler()

    def test_crawled_with_referer(self):
        req = Request("http://www.example.com")
        res = Response("http://www.example.com")
        logkws = self.formatter.crawled(req, res, self.spider)
        logline = logkws["msg"] % logkws["args"]
        assert logline == "Crawled (200) <GET http://www.example.com> (referer: None)"

    def test_crawled_without_referer(self):
        req = Request(
            "http://www.example.com", headers={"referer": "http://example.com"}
        )
        res = Response("http://www.example.com", flags=["cached"])
        logkws = self.formatter.crawled(req, res, self.spider)
        logline = logkws["msg"] % logkws["args"]
        assert (
            logline
            == "Crawled (200) <GET http://www.example.com> (referer: http://example.com) ['cached']"
        )

    def test_flags_in_request(self):
        req = Request("http://www.example.com", flags=["test", "flag"])
        res = Response("http://www.example.com")
        logkws = self.formatter.crawled(req, res, self.spider)
        logline = logkws["msg"] % logkws["args"]
        assert (
            logline
            == "Crawled (200) <GET http://www.example.com> ['test', 'flag'] (referer: None)"
        )

    def test_dropped(self):
        item = {}
        exception = Exception("\u2018")
        response = Response("http://www.example.com")
        logkws = self.formatter.dropped(item, exception, response, self.spider)
        logline = logkws["msg"] % logkws["args"]
        lines = logline.splitlines()
        assert all(isinstance(x, str) for x in lines)
        assert lines == ["Dropped: \u2018", "{}"]

    def test_dropitem_default_log_level(self):
        item = {}
        exception = DropItem("Test drop")
        response = Response("http://www.example.com")
        spider = Spider("foo")
        spider.crawler = get_crawler(Spider)

        logkws = self.formatter.dropped(item, exception, response, spider)
        assert logkws["level"] == logging.WARNING

        spider.crawler.settings.frozen = False
        spider.crawler.settings["DEFAULT_DROPITEM_LOG_LEVEL"] = logging.INFO
        spider.crawler.settings.frozen = True
        logkws = self.formatter.dropped(item, exception, response, spider)
        assert logkws["level"] == logging.INFO

        spider.crawler.settings.frozen = False
        spider.crawler.settings["DEFAULT_DROPITEM_LOG_LEVEL"] = "INFO"
        spider.crawler.settings.frozen = True
        logkws = self.formatter.dropped(item, exception, response, spider)
        assert logkws["level"] == logging.INFO

        spider.crawler.settings.frozen = False
        spider.crawler.settings["DEFAULT_DROPITEM_LOG_LEVEL"] = 10
        spider.crawler.settings.frozen = True
        logkws = self.formatter.dropped(item, exception, response, spider)
        assert logkws["level"] == logging.DEBUG

        spider.crawler.settings.frozen = False
        spider.crawler.settings["DEFAULT_DROPITEM_LOG_LEVEL"] = 0
        spider.crawler.settings.frozen = True
        logkws = self.formatter.dropped(item, exception, response, spider)
        assert logkws["level"] == logging.NOTSET

        unsupported_value = object()
        spider.crawler.settings.frozen = False
        spider.crawler.settings["DEFAULT_DROPITEM_LOG_LEVEL"] = unsupported_value
        spider.crawler.settings.frozen = True
        logkws = self.formatter.dropped(item, exception, response, spider)
        assert logkws["level"] == unsupported_value

        with pytest.raises(TypeError):
            logging.log(logkws["level"], "message")

    def test_dropitem_custom_log_level(self):
        item = {}
        response = Response("http://www.example.com")

        exception = DropItem("Test drop", log_level="INFO")
        logkws = self.formatter.dropped(item, exception, response, self.spider)
        assert logkws["level"] == logging.INFO

        exception = DropItem("Test drop", log_level="ERROR")
        logkws = self.formatter.dropped(item, exception, response, self.spider)
        assert logkws["level"] == logging.ERROR

    def test_item_error(self):
        # In practice, the complete traceback is shown by passing the
        # 'exc_info' argument to the logging function
        item = {"key": "value"}
        exception = Exception()
        response = Response("http://www.example.com")
        logkws = self.formatter.item_error(item, exception, response, self.spider)
        logline = logkws["msg"] % logkws["args"]
        assert logline == "Error processing {'key': 'value'}"

    def test_spider_error(self):
        # In practice, the complete traceback is shown by passing the
        # 'exc_info' argument to the logging function
        failure = Failure(Exception())
        request = Request(
            "http://www.example.com", headers={"Referer": "http://example.org"}
        )
        response = Response("http://www.example.com", request=request)
        logkws = self.formatter.spider_error(failure, request, response, self.spider)
        logline = logkws["msg"] % logkws["args"]
        assert (
            logline
            == "Spider error processing <GET http://www.example.com> (referer: http://example.org)"
        )

    def test_download_error_short(self):
        # In practice, the complete traceback is shown by passing the
        # 'exc_info' argument to the logging function
        failure = Failure(Exception())
        request = Request("http://www.example.com")
        logkws = self.formatter.download_error(failure, request, self.spider)
        logline = logkws["msg"] % logkws["args"]
        assert logline == "Error downloading <GET http://www.example.com>"

    def test_download_error_long(self):
        # In practice, the complete traceback is shown by passing the
        # 'exc_info' argument to the logging function
        failure = Failure(Exception())
        request = Request("http://www.example.com")
        logkws = self.formatter.download_error(
            failure, request, self.spider, "Some message"
        )
        logline = logkws["msg"] % logkws["args"]
        assert logline == "Error downloading <GET http://www.example.com>: Some message"

    def test_scraped(self):
        item = CustomItem()
        item["name"] = "\xa3"
        response = Response("http://www.example.com")
        logkws = self.formatter.scraped(item, response, self.spider)
        logline = logkws["msg"] % logkws["args"]
        lines = logline.splitlines()
        assert all(isinstance(x, str) for x in lines)
        assert lines == ["Scraped from <200 http://www.example.com>", "name: \xa3"]


class LogFormatterSubclass(LogFormatter):
    def crawled(self, request, response, spider):
        kwargs = super().crawled(request, response, spider)
        CRAWLEDMSG = "Crawled (%(status)s) %(request)s (referer: %(referer)s) %(flags)s"
        log_args = kwargs["args"]
        log_args["flags"] = str(request.flags)
        return {
            "level": kwargs["level"],
            "msg": CRAWLEDMSG,
            "args": log_args,
        }


class TestLogformatterSubclass(TestLogFormatter):
    def setup_method(self):
        self.formatter = LogFormatterSubclass()
        self.spider = Spider("default")
        self.spider.crawler = get_crawler(Spider)

    def test_crawled_with_referer(self):
        req = Request("http://www.example.com")
        res = Response("http://www.example.com")
        logkws = self.formatter.crawled(req, res, self.spider)
        logline = logkws["msg"] % logkws["args"]
        assert (
            logline == "Crawled (200) <GET http://www.example.com> (referer: None) []"
        )

    def test_crawled_without_referer(self):
        req = Request(
            "http://www.example.com",
            headers={"referer": "http://example.com"},
            flags=["cached"],
        )
        res = Response("http://www.example.com")
        logkws = self.formatter.crawled(req, res, self.spider)
        logline = logkws["msg"] % logkws["args"]
        assert (
            logline
            == "Crawled (200) <GET http://www.example.com> (referer: http://example.com) ['cached']"
        )

    def test_flags_in_request(self):
        req = Request("http://www.example.com", flags=["test", "flag"])
        res = Response("http://www.example.com")
        logkws = self.formatter.crawled(req, res, self.spider)
        logline = logkws["msg"] % logkws["args"]
        assert (
            logline
            == "Crawled (200) <GET http://www.example.com> (referer: None) ['test', 'flag']"
        )


class SkipMessagesLogFormatter(LogFormatter):
    def crawled(self, *args, **kwargs):
        return None

    def scraped(self, *args, **kwargs):
        return None

    def dropped(self, *args, **kwargs):
        return None


class DropSomeItemsPipeline:
    drop = True

    def process_item(self, item, spider):
        if self.drop:
            self.drop = False
            raise DropItem("Ignoring item")
        self.drop = True


class TestShowOrSkipMessages(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mockserver = MockServer()
        cls.mockserver.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.mockserver.__exit__(None, None, None)

    def setUp(self):
        self.base_settings = {
            "LOG_LEVEL": "DEBUG",
            "ITEM_PIPELINES": {
                DropSomeItemsPipeline: 300,
            },
        }

    @defer.inlineCallbacks
    def test_show_messages(self):
        crawler = get_crawler(ItemSpider, self.base_settings)
        with LogCapture() as lc:
            yield crawler.crawl(mockserver=self.mockserver)
        assert "Scraped from <200 http://127.0.0.1:" in str(lc)
        assert "Crawled (200) <GET http://127.0.0.1:" in str(lc)
        assert "Dropped: Ignoring item" in str(lc)

    @defer.inlineCallbacks
    def test_skip_messages(self):
        settings = self.base_settings.copy()
        settings["LOG_FORMATTER"] = SkipMessagesLogFormatter
        crawler = get_crawler(ItemSpider, settings)
        with LogCapture() as lc:
            yield crawler.crawl(mockserver=self.mockserver)
        assert "Scraped from <200 http://127.0.0.1:" not in str(lc)
        assert "Crawled (200) <GET http://127.0.0.1:" not in str(lc)
        assert "Dropped: Ignoring item" not in str(lc)
