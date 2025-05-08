import logging
import platform
import re
import signal
import subprocess
import sys
import warnings
from pathlib import Path
from typing import Any

import pytest
from packaging.version import parse as parse_version
from pexpect.popen_spawn import PopenSpawn
from twisted.internet.defer import Deferred, inlineCallbacks
from twisted.trial import unittest
from w3lib import __version__ as w3lib_version
from zope.interface.exceptions import MultipleInvalid

import scrapy
from scrapy import Spider
from scrapy.crawler import Crawler, CrawlerProcess, CrawlerRunner
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.extensions.throttle import AutoThrottle
from scrapy.settings import Settings, default_settings
from scrapy.spiderloader import SpiderLoader
from scrapy.utils.log import configure_logging, get_scrapy_root_handler
from scrapy.utils.spider import DefaultSpider
from scrapy.utils.test import get_crawler, get_reactor_settings
from tests.mockserver import MockServer, get_mockserver_env

BASE_SETTINGS: dict[str, Any] = {}


def get_raw_crawler(spidercls=None, settings_dict=None):
    """get_crawler alternative that only calls the __init__ method of the
    crawler."""
    settings = Settings()
    settings.setdict(get_reactor_settings())
    settings.setdict(settings_dict or {})
    return Crawler(spidercls or DefaultSpider, settings)


class TestBaseCrawler(unittest.TestCase):
    def assertOptionIsDefault(self, settings, key):
        assert isinstance(settings, Settings)
        assert settings[key] == getattr(default_settings, key)


class TestCrawler(TestBaseCrawler):
    def test_populate_spidercls_settings(self):
        spider_settings = {"TEST1": "spider", "TEST2": "spider"}
        project_settings = {
            **BASE_SETTINGS,
            "TEST1": "project",
            "TEST3": "project",
            **get_reactor_settings(),
        }

        class CustomSettingsSpider(DefaultSpider):
            custom_settings = spider_settings

        settings = Settings()
        settings.setdict(project_settings, priority="project")
        crawler = Crawler(CustomSettingsSpider, settings)
        crawler._apply_settings()

        assert crawler.settings.get("TEST1") == "spider"
        assert crawler.settings.get("TEST2") == "spider"
        assert crawler.settings.get("TEST3") == "project"

        assert not settings.frozen
        assert crawler.settings.frozen

    def test_crawler_accepts_dict(self):
        crawler = get_crawler(DefaultSpider, {"foo": "bar"})
        assert crawler.settings["foo"] == "bar"
        self.assertOptionIsDefault(crawler.settings, "RETRY_ENABLED")

    def test_crawler_accepts_None(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ScrapyDeprecationWarning)
            crawler = Crawler(DefaultSpider)
        self.assertOptionIsDefault(crawler.settings, "RETRY_ENABLED")

    def test_crawler_rejects_spider_objects(self):
        with pytest.raises(ValueError, match="spidercls argument must be a class"):
            Crawler(DefaultSpider())

    @inlineCallbacks
    def test_crawler_crawl_twice_unsupported(self):
        crawler = get_raw_crawler(NoRequestsSpider, BASE_SETTINGS)
        yield crawler.crawl()
        with pytest.raises(RuntimeError, match="more than once on the same instance"):
            yield crawler.crawl()

    def test_get_addon(self):
        class ParentAddon:
            pass

        class TrackingAddon(ParentAddon):
            instances = []

            def __init__(self):
                TrackingAddon.instances.append(self)

            def update_settings(self, settings):
                pass

        settings = {
            **BASE_SETTINGS,
            "ADDONS": {
                TrackingAddon: 0,
            },
        }
        crawler = get_crawler(settings_dict=settings)
        assert len(TrackingAddon.instances) == 1
        expected = TrackingAddon.instances[-1]

        addon = crawler.get_addon(TrackingAddon)
        assert addon == expected

        addon = crawler.get_addon(DefaultSpider)
        assert addon is None

        addon = crawler.get_addon(ParentAddon)
        assert addon == expected

        class ChildAddon(TrackingAddon):
            pass

        addon = crawler.get_addon(ChildAddon)
        assert addon is None

    @inlineCallbacks
    def test_get_downloader_middleware(self):
        class ParentDownloaderMiddleware:
            pass

        class TrackingDownloaderMiddleware(ParentDownloaderMiddleware):
            instances = []

            def __init__(self):
                TrackingDownloaderMiddleware.instances.append(self)

        class MySpider(Spider):
            name = "myspider"

            @classmethod
            def from_crawler(cls, crawler):
                return cls(crawler=crawler)

            def __init__(self, crawler, **kwargs: Any):
                super().__init__(**kwargs)
                self.crawler = crawler

            async def start(self):
                MySpider.result = crawler.get_downloader_middleware(MySpider.cls)
                return
                yield

        settings = {
            **BASE_SETTINGS,
            "DOWNLOADER_MIDDLEWARES": {
                TrackingDownloaderMiddleware: 0,
            },
        }

        crawler = get_raw_crawler(MySpider, settings)
        MySpider.cls = TrackingDownloaderMiddleware
        yield crawler.crawl()
        assert len(TrackingDownloaderMiddleware.instances) == 1
        assert MySpider.result == TrackingDownloaderMiddleware.instances[-1]

        crawler = get_raw_crawler(MySpider, settings)
        MySpider.cls = DefaultSpider
        yield crawler.crawl()
        assert MySpider.result is None

        crawler = get_raw_crawler(MySpider, settings)
        MySpider.cls = ParentDownloaderMiddleware
        yield crawler.crawl()
        assert MySpider.result == TrackingDownloaderMiddleware.instances[-1]

        class ChildDownloaderMiddleware(TrackingDownloaderMiddleware):
            pass

        crawler = get_raw_crawler(MySpider, settings)
        MySpider.cls = ChildDownloaderMiddleware
        yield crawler.crawl()
        assert MySpider.result is None

    def test_get_downloader_middleware_not_crawling(self):
        crawler = get_raw_crawler(settings_dict=BASE_SETTINGS)
        with pytest.raises(RuntimeError):
            crawler.get_downloader_middleware(DefaultSpider)

    @inlineCallbacks
    def test_get_downloader_middleware_no_engine(self):
        class MySpider(Spider):
            name = "myspider"

            @classmethod
            def from_crawler(cls, crawler):
                try:
                    crawler.get_downloader_middleware(DefaultSpider)
                except Exception as e:
                    MySpider.result = e
                    raise

        crawler = get_raw_crawler(MySpider, BASE_SETTINGS)
        with pytest.raises(RuntimeError):
            yield crawler.crawl()

    @inlineCallbacks
    def test_get_extension(self):
        class ParentExtension:
            pass

        class TrackingExtension(ParentExtension):
            instances = []

            def __init__(self):
                TrackingExtension.instances.append(self)

        class MySpider(Spider):
            name = "myspider"

            @classmethod
            def from_crawler(cls, crawler):
                return cls(crawler=crawler)

            def __init__(self, crawler, **kwargs: Any):
                super().__init__(**kwargs)
                self.crawler = crawler

            async def start(self):
                MySpider.result = crawler.get_extension(MySpider.cls)
                return
                yield

        settings = {
            **BASE_SETTINGS,
            "EXTENSIONS": {
                TrackingExtension: 0,
            },
        }

        crawler = get_raw_crawler(MySpider, settings)
        MySpider.cls = TrackingExtension
        yield crawler.crawl()
        assert len(TrackingExtension.instances) == 1
        assert MySpider.result == TrackingExtension.instances[-1]

        crawler = get_raw_crawler(MySpider, settings)
        MySpider.cls = DefaultSpider
        yield crawler.crawl()
        assert MySpider.result is None

        crawler = get_raw_crawler(MySpider, settings)
        MySpider.cls = ParentExtension
        yield crawler.crawl()
        assert MySpider.result == TrackingExtension.instances[-1]

        class ChildExtension(TrackingExtension):
            pass

        crawler = get_raw_crawler(MySpider, settings)
        MySpider.cls = ChildExtension
        yield crawler.crawl()
        assert MySpider.result is None

    def test_get_extension_not_crawling(self):
        crawler = get_raw_crawler(settings_dict=BASE_SETTINGS)
        with pytest.raises(RuntimeError):
            crawler.get_extension(DefaultSpider)

    @inlineCallbacks
    def test_get_extension_no_engine(self):
        class MySpider(Spider):
            name = "myspider"

            @classmethod
            def from_crawler(cls, crawler):
                try:
                    crawler.get_extension(DefaultSpider)
                except Exception as e:
                    MySpider.result = e
                    raise

        crawler = get_raw_crawler(MySpider, BASE_SETTINGS)
        with pytest.raises(RuntimeError):
            yield crawler.crawl()

    @inlineCallbacks
    def test_get_item_pipeline(self):
        class ParentItemPipeline:
            pass

        class TrackingItemPipeline(ParentItemPipeline):
            instances = []

            def __init__(self):
                TrackingItemPipeline.instances.append(self)

        class MySpider(Spider):
            name = "myspider"

            @classmethod
            def from_crawler(cls, crawler):
                return cls(crawler=crawler)

            def __init__(self, crawler, **kwargs: Any):
                super().__init__(**kwargs)
                self.crawler = crawler

            async def start(self):
                MySpider.result = crawler.get_item_pipeline(MySpider.cls)
                return
                yield

        settings = {
            **BASE_SETTINGS,
            "ITEM_PIPELINES": {
                TrackingItemPipeline: 0,
            },
        }

        crawler = get_raw_crawler(MySpider, settings)
        MySpider.cls = TrackingItemPipeline
        yield crawler.crawl()
        assert len(TrackingItemPipeline.instances) == 1
        assert MySpider.result == TrackingItemPipeline.instances[-1]

        crawler = get_raw_crawler(MySpider, settings)
        MySpider.cls = DefaultSpider
        yield crawler.crawl()
        assert MySpider.result is None

        crawler = get_raw_crawler(MySpider, settings)
        MySpider.cls = ParentItemPipeline
        yield crawler.crawl()
        assert MySpider.result == TrackingItemPipeline.instances[-1]

        class ChildItemPipeline(TrackingItemPipeline):
            pass

        crawler = get_raw_crawler(MySpider, settings)
        MySpider.cls = ChildItemPipeline
        yield crawler.crawl()
        assert MySpider.result is None

    def test_get_item_pipeline_not_crawling(self):
        crawler = get_raw_crawler(settings_dict=BASE_SETTINGS)
        with pytest.raises(RuntimeError):
            crawler.get_item_pipeline(DefaultSpider)

    @inlineCallbacks
    def test_get_item_pipeline_no_engine(self):
        class MySpider(Spider):
            name = "myspider"

            @classmethod
            def from_crawler(cls, crawler):
                try:
                    crawler.get_item_pipeline(DefaultSpider)
                except Exception as e:
                    MySpider.result = e
                    raise

        crawler = get_raw_crawler(MySpider, BASE_SETTINGS)
        with pytest.raises(RuntimeError):
            yield crawler.crawl()

    @inlineCallbacks
    def test_get_spider_middleware(self):
        class ParentSpiderMiddleware:
            pass

        class TrackingSpiderMiddleware(ParentSpiderMiddleware):
            instances = []

            def __init__(self):
                TrackingSpiderMiddleware.instances.append(self)

        class MySpider(Spider):
            name = "myspider"

            @classmethod
            def from_crawler(cls, crawler):
                return cls(crawler=crawler)

            def __init__(self, crawler, **kwargs: Any):
                super().__init__(**kwargs)
                self.crawler = crawler

            async def start(self):
                MySpider.result = crawler.get_spider_middleware(MySpider.cls)
                return
                yield

        settings = {
            **BASE_SETTINGS,
            "SPIDER_MIDDLEWARES": {
                TrackingSpiderMiddleware: 0,
            },
        }

        crawler = get_raw_crawler(MySpider, settings)
        MySpider.cls = TrackingSpiderMiddleware
        yield crawler.crawl()
        assert len(TrackingSpiderMiddleware.instances) == 1
        assert MySpider.result == TrackingSpiderMiddleware.instances[-1]

        crawler = get_raw_crawler(MySpider, settings)
        MySpider.cls = DefaultSpider
        yield crawler.crawl()
        assert MySpider.result is None

        crawler = get_raw_crawler(MySpider, settings)
        MySpider.cls = ParentSpiderMiddleware
        yield crawler.crawl()
        assert MySpider.result == TrackingSpiderMiddleware.instances[-1]

        class ChildSpiderMiddleware(TrackingSpiderMiddleware):
            pass

        crawler = get_raw_crawler(MySpider, settings)
        MySpider.cls = ChildSpiderMiddleware
        yield crawler.crawl()
        assert MySpider.result is None

    def test_get_spider_middleware_not_crawling(self):
        crawler = get_raw_crawler(settings_dict=BASE_SETTINGS)
        with pytest.raises(RuntimeError):
            crawler.get_spider_middleware(DefaultSpider)

    @inlineCallbacks
    def test_get_spider_middleware_no_engine(self):
        class MySpider(Spider):
            name = "myspider"

            @classmethod
            def from_crawler(cls, crawler):
                try:
                    crawler.get_spider_middleware(DefaultSpider)
                except Exception as e:
                    MySpider.result = e
                    raise

        crawler = get_raw_crawler(MySpider, BASE_SETTINGS)
        with pytest.raises(RuntimeError):
            yield crawler.crawl()


class TestSpiderSettings:
    def test_spider_custom_settings(self):
        class MySpider(scrapy.Spider):
            name = "spider"
            custom_settings = {"AUTOTHROTTLE_ENABLED": True}

        crawler = get_crawler(MySpider)
        enabled_exts = [e.__class__ for e in crawler.extensions.middlewares]
        assert AutoThrottle in enabled_exts


class TestCrawlerLogging:
    def test_no_root_handler_installed(self):
        handler = get_scrapy_root_handler()
        if handler is not None:
            logging.root.removeHandler(handler)

        class MySpider(scrapy.Spider):
            name = "spider"

        get_crawler(MySpider)
        assert get_scrapy_root_handler() is None

    def test_spider_custom_settings_log_level(self, tmp_path):
        log_file = Path(tmp_path, "log.txt")
        log_file.write_text("previous message\n", encoding="utf-8")

        class MySpider(scrapy.Spider):
            name = "spider"
            custom_settings = {
                "LOG_LEVEL": "INFO",
                "LOG_FILE": str(log_file),
            }

        configure_logging()
        assert get_scrapy_root_handler().level == logging.DEBUG
        crawler = get_crawler(MySpider)
        assert get_scrapy_root_handler().level == logging.INFO
        info_count = crawler.stats.get_value("log_count/INFO")
        logging.debug("debug message")
        logging.info("info message")
        logging.warning("warning message")
        logging.error("error message")

        logged = log_file.read_text(encoding="utf-8")

        assert "previous message" in logged
        assert "debug message" not in logged
        assert "info message" in logged
        assert "warning message" in logged
        assert "error message" in logged
        assert crawler.stats.get_value("log_count/ERROR") == 1
        assert crawler.stats.get_value("log_count/WARNING") == 1
        assert crawler.stats.get_value("log_count/INFO") - info_count == 1
        assert crawler.stats.get_value("log_count/DEBUG", 0) == 0

    def test_spider_custom_settings_log_append(self, tmp_path):
        log_file = Path(tmp_path, "log.txt")
        log_file.write_text("previous message\n", encoding="utf-8")

        class MySpider(scrapy.Spider):
            name = "spider"
            custom_settings = {
                "LOG_FILE": str(log_file),
                "LOG_FILE_APPEND": False,
            }

        configure_logging()
        get_crawler(MySpider)
        logging.debug("debug message")

        logged = log_file.read_text(encoding="utf-8")

        assert "previous message" not in logged
        assert "debug message" in logged


class SpiderLoaderWithWrongInterface:
    def unneeded_method(self):
        pass


class CustomSpiderLoader(SpiderLoader):
    pass


class TestCrawlerRunner(TestBaseCrawler):
    def test_spider_manager_verify_interface(self):
        settings = Settings(
            {
                "SPIDER_LOADER_CLASS": SpiderLoaderWithWrongInterface,
            }
        )
        with pytest.raises(MultipleInvalid):
            CrawlerRunner(settings)

    def test_crawler_runner_accepts_dict(self):
        runner = CrawlerRunner({"foo": "bar"})
        assert runner.settings["foo"] == "bar"
        self.assertOptionIsDefault(runner.settings, "RETRY_ENABLED")

    def test_crawler_runner_accepts_None(self):
        runner = CrawlerRunner()
        self.assertOptionIsDefault(runner.settings, "RETRY_ENABLED")


class TestCrawlerProcess(TestBaseCrawler):
    def test_crawler_process_accepts_dict(self):
        runner = CrawlerProcess({"foo": "bar"})
        assert runner.settings["foo"] == "bar"
        self.assertOptionIsDefault(runner.settings, "RETRY_ENABLED")

    def test_crawler_process_accepts_None(self):
        runner = CrawlerProcess()
        self.assertOptionIsDefault(runner.settings, "RETRY_ENABLED")


class ExceptionSpider(scrapy.Spider):
    name = "exception"

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        raise ValueError("Exception in from_crawler method")


class NoRequestsSpider(scrapy.Spider):
    name = "no_request"

    async def start(self):
        return
        yield


@pytest.mark.usefixtures("reactor_pytest")
class TestCrawlerRunnerHasSpider(unittest.TestCase):
    def _runner(self):
        return CrawlerRunner(get_reactor_settings())

    @inlineCallbacks
    def test_crawler_runner_bootstrap_successful(self):
        runner = self._runner()
        yield runner.crawl(NoRequestsSpider)
        assert not runner.bootstrap_failed

    @inlineCallbacks
    def test_crawler_runner_bootstrap_successful_for_several(self):
        runner = self._runner()
        yield runner.crawl(NoRequestsSpider)
        yield runner.crawl(NoRequestsSpider)
        assert not runner.bootstrap_failed

    @inlineCallbacks
    def test_crawler_runner_bootstrap_failed(self):
        runner = self._runner()

        try:
            yield runner.crawl(ExceptionSpider)
        except ValueError:
            pass
        else:
            pytest.fail("Exception should be raised from spider")

        assert runner.bootstrap_failed

    @inlineCallbacks
    def test_crawler_runner_bootstrap_failed_for_several(self):
        runner = self._runner()

        try:
            yield runner.crawl(ExceptionSpider)
        except ValueError:
            pass
        else:
            pytest.fail("Exception should be raised from spider")

        yield runner.crawl(NoRequestsSpider)

        assert runner.bootstrap_failed

    @inlineCallbacks
    def test_crawler_runner_asyncio_enabled_true(self):
        if self.reactor_pytest == "default":
            runner = CrawlerRunner(
                settings={
                    "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
                }
            )
            with pytest.raises(
                Exception,
                match=r"The installed reactor \(.*?\) does not match the requested one \(.*?\)",
            ):
                yield runner.crawl(NoRequestsSpider)
        else:
            CrawlerRunner(
                settings={
                    "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
                }
            )


class ScriptRunnerMixin:
    script_dir: Path

    def get_script_args(self, script_name: str, *script_args: str) -> list[str]:
        script_path = self.script_dir / script_name
        return [sys.executable, str(script_path), *script_args]

    def run_script(self, script_name: str, *script_args: str) -> str:
        args = self.get_script_args(script_name, *script_args)
        p = subprocess.Popen(
            args,
            env=get_mockserver_env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = p.communicate()
        return stderr.decode("utf-8")


class TestCrawlerProcessSubprocess(ScriptRunnerMixin, unittest.TestCase):
    script_dir = Path(__file__).parent.resolve() / "CrawlerProcess"

    def test_simple(self):
        log = self.run_script("simple.py")
        assert "Spider closed (finished)" in log
        assert (
            "Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor"
            in log
        )

    def test_multi(self):
        log = self.run_script("multi.py")
        assert "Spider closed (finished)" in log
        assert (
            "Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor"
            in log
        )
        assert "ReactorAlreadyInstalledError" not in log

    def test_reactor_default(self):
        log = self.run_script("reactor_default.py")
        assert "Spider closed (finished)" not in log
        assert (
            "does not match the requested one "
            "(twisted.internet.asyncioreactor.AsyncioSelectorReactor)"
        ) in log

    def test_reactor_default_twisted_reactor_select(self):
        log = self.run_script("reactor_default_twisted_reactor_select.py")
        if platform.system() in ["Windows", "Darwin"]:
            # The goal of this test function is to test that, when a reactor is
            # installed (the default one here) and a different reactor is
            # configured (select here), an error raises.
            #
            # In Windows the default reactor is the select reactor, so that
            # error does not raise.
            #
            # If that ever becomes the case on more platforms (i.e. if Linux
            # also starts using the select reactor by default in a future
            # version of Twisted), then we will need to rethink this test.
            assert "Spider closed (finished)" in log
        else:
            assert "Spider closed (finished)" not in log
            assert (
                "does not match the requested one "
                "(twisted.internet.selectreactor.SelectReactor)"
            ) in log

    def test_reactor_select(self):
        log = self.run_script("reactor_select.py")
        assert "Spider closed (finished)" not in log
        assert (
            "does not match the requested one "
            "(twisted.internet.asyncioreactor.AsyncioSelectorReactor)"
        ) in log

    def test_reactor_select_twisted_reactor_select(self):
        log = self.run_script("reactor_select_twisted_reactor_select.py")
        assert "Spider closed (finished)" in log
        assert "ReactorAlreadyInstalledError" not in log

    def test_reactor_select_subclass_twisted_reactor_select(self):
        log = self.run_script("reactor_select_subclass_twisted_reactor_select.py")
        assert "Spider closed (finished)" not in log
        assert (
            "does not match the requested one "
            "(twisted.internet.selectreactor.SelectReactor)"
        ) in log

    def test_asyncio_enabled_no_reactor(self):
        log = self.run_script("asyncio_enabled_no_reactor.py")
        assert "Spider closed (finished)" in log
        assert (
            "Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor"
            in log
        )
        assert "RuntimeError" not in log

    def test_asyncio_enabled_reactor(self):
        log = self.run_script("asyncio_enabled_reactor.py")
        assert "Spider closed (finished)" in log
        assert (
            "Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor"
            in log
        )
        assert "RuntimeError" not in log

    @pytest.mark.skipif(
        parse_version(w3lib_version) >= parse_version("2.0.0"),
        reason="w3lib 2.0.0 and later do not allow invalid domains.",
    )
    def test_ipv6_default_name_resolver(self):
        log = self.run_script("default_name_resolver.py")
        assert "Spider closed (finished)" in log
        assert (
            "'downloader/exception_type_count/twisted.internet.error.DNSLookupError': 1,"
            in log
        )
        assert (
            "twisted.internet.error.DNSLookupError: DNS lookup failed: no results for hostname lookup: ::1."
            in log
        )

    def test_caching_hostname_resolver_ipv6(self):
        log = self.run_script("caching_hostname_resolver_ipv6.py")
        assert "Spider closed (finished)" in log
        assert "twisted.internet.error.DNSLookupError" not in log

    def test_caching_hostname_resolver_finite_execution(self):
        with MockServer() as mock_server:
            http_address = mock_server.http_address.replace("0.0.0.0", "127.0.0.1")
            log = self.run_script("caching_hostname_resolver.py", http_address)
            assert "Spider closed (finished)" in log
            assert "ERROR: Error downloading" not in log
            assert "TimeoutError" not in log
            assert "twisted.internet.error.DNSLookupError" not in log

    def test_twisted_reactor_select(self):
        log = self.run_script("twisted_reactor_select.py")
        assert "Spider closed (finished)" in log
        assert "Using reactor: twisted.internet.selectreactor.SelectReactor" in log

    @pytest.mark.skipif(
        platform.system() == "Windows", reason="PollReactor is not supported on Windows"
    )
    def test_twisted_reactor_poll(self):
        log = self.run_script("twisted_reactor_poll.py")
        assert "Spider closed (finished)" in log
        assert "Using reactor: twisted.internet.pollreactor.PollReactor" in log

    def test_twisted_reactor_asyncio(self):
        log = self.run_script("twisted_reactor_asyncio.py")
        assert "Spider closed (finished)" in log
        assert (
            "Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor"
            in log
        )

    def test_twisted_reactor_asyncio_custom_settings(self):
        log = self.run_script("twisted_reactor_custom_settings.py")
        assert "Spider closed (finished)" in log
        assert (
            "Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor"
            in log
        )

    def test_twisted_reactor_asyncio_custom_settings_same(self):
        log = self.run_script("twisted_reactor_custom_settings_same.py")
        assert "Spider closed (finished)" in log
        assert (
            "Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor"
            in log
        )

    def test_twisted_reactor_asyncio_custom_settings_conflict(self):
        log = self.run_script("twisted_reactor_custom_settings_conflict.py")
        assert "Using reactor: twisted.internet.selectreactor.SelectReactor" in log
        assert (
            "(twisted.internet.selectreactor.SelectReactor) does not match the requested one"
            in log
        )

    @pytest.mark.requires_uvloop
    def test_custom_loop_asyncio(self):
        log = self.run_script("asyncio_custom_loop.py")
        assert "Spider closed (finished)" in log
        assert (
            "Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor"
            in log
        )
        assert "Using asyncio event loop: uvloop.Loop" in log

    @pytest.mark.requires_uvloop
    def test_custom_loop_asyncio_deferred_signal(self):
        log = self.run_script("asyncio_deferred_signal.py", "uvloop.Loop")
        assert "Spider closed (finished)" in log
        assert (
            "Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor"
            in log
        )
        assert "Using asyncio event loop: uvloop.Loop" in log
        assert "async pipeline opened!" in log

    @pytest.mark.requires_uvloop
    def test_asyncio_enabled_reactor_same_loop(self):
        log = self.run_script("asyncio_enabled_reactor_same_loop.py")
        assert "Spider closed (finished)" in log
        assert (
            "Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor"
            in log
        )
        assert "Using asyncio event loop: uvloop.Loop" in log

    @pytest.mark.requires_uvloop
    def test_asyncio_enabled_reactor_different_loop(self):
        log = self.run_script("asyncio_enabled_reactor_different_loop.py")
        assert "Spider closed (finished)" not in log
        assert (
            "does not match the one specified in the ASYNCIO_EVENT_LOOP "
            "setting (uvloop.Loop)"
        ) in log

    def test_default_loop_asyncio_deferred_signal(self):
        log = self.run_script("asyncio_deferred_signal.py")
        assert "Spider closed (finished)" in log
        assert (
            "Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor"
            in log
        )
        assert "Using asyncio event loop: uvloop.Loop" not in log
        assert "async pipeline opened!" in log

    def test_args_change_settings(self):
        log = self.run_script("args_settings.py")
        assert "Spider closed (finished)" in log
        assert "The value of FOO is 42" in log

    def test_shutdown_graceful(self):
        sig = signal.SIGINT if sys.platform != "win32" else signal.SIGBREAK
        args = self.get_script_args("sleeping.py", "3")
        p = PopenSpawn(args, timeout=5)
        p.expect_exact("Spider opened")
        p.expect_exact("Crawled (200)")
        p.kill(sig)
        p.expect_exact("shutting down gracefully")
        p.expect_exact("Spider closed (shutdown)")
        p.wait()

    @inlineCallbacks
    def test_shutdown_forced(self):
        from twisted.internet import reactor

        sig = signal.SIGINT if sys.platform != "win32" else signal.SIGBREAK
        args = self.get_script_args("sleeping.py", "10")
        p = PopenSpawn(args, timeout=5)
        p.expect_exact("Spider opened")
        p.expect_exact("Crawled (200)")
        p.kill(sig)
        p.expect_exact("shutting down gracefully")
        # sending the second signal too fast often causes problems
        d = Deferred()
        reactor.callLater(0.01, d.callback, None)
        yield d
        p.kill(sig)
        p.expect_exact("forcing unclean shutdown")
        p.wait()


class TestCrawlerRunnerSubprocess(ScriptRunnerMixin):
    script_dir = Path(__file__).parent.resolve() / "CrawlerRunner"

    def test_response_ip_address(self):
        log = self.run_script("ip_address.py")
        assert "INFO: Spider closed (finished)" in log
        assert "INFO: Host: not.a.real.domain" in log
        assert "INFO: Type: <class 'ipaddress.IPv4Address'>" in log
        assert "INFO: IP address: 127.0.0.1" in log

    def test_change_default_reactor(self):
        log = self.run_script("change_reactor.py")
        assert (
            "DEBUG: Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor"
            in log
        )
        assert "DEBUG: Using asyncio event loop" in log


@pytest.mark.parametrize(
    ("settings", "items"),
    [
        ({}, default_settings.LOG_VERSIONS),
        ({"LOG_VERSIONS": ["itemadapter"]}, ["itemadapter"]),
        ({"LOG_VERSIONS": []}, None),
    ],
)
def test_log_scrapy_info(settings, items, caplog):
    with caplog.at_level("INFO"):
        CrawlerProcess(settings)
    assert (
        caplog.records[0].getMessage()
        == f"Scrapy {scrapy.__version__} started (bot: scrapybot)"
    ), repr(caplog.records[0].msg)
    if not items:
        assert len(caplog.records) == 1
        return
    version_string = caplog.records[1].getMessage()
    expected_items_pattern = "',\n '".join(
        f"{item}': '[^']+('\n +'[^']+)*" for item in items
    )
    assert re.search(r"^Versions:\n{'" + expected_items_pattern + "'}$", version_string)
