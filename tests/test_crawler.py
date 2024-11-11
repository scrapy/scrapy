import logging
import os
import platform
import signal
import subprocess
import sys
import warnings
from pathlib import Path
from typing import Any

from packaging.version import parse as parse_version
from pexpect.popen_spawn import PopenSpawn
from pytest import mark, raises
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
from scrapy.utils.test import get_crawler
from tests.mockserver import MockServer, get_mockserver_env

BASE_SETTINGS: dict[str, Any] = {}


def get_raw_crawler(spidercls=None, settings_dict=None):
    """get_crawler alternative that only calls the __init__ method of the
    crawler."""
    settings = Settings()
    settings.setdict(settings_dict or {})
    return Crawler(spidercls or DefaultSpider, settings)


class BaseCrawlerTest(unittest.TestCase):
    def assertOptionIsDefault(self, settings, key):
        self.assertIsInstance(settings, Settings)
        self.assertEqual(settings[key], getattr(default_settings, key))


class CrawlerTestCase(BaseCrawlerTest):
    def test_populate_spidercls_settings(self):
        spider_settings = {"TEST1": "spider", "TEST2": "spider"}
        project_settings = {**BASE_SETTINGS, "TEST1": "project", "TEST3": "project"}

        class CustomSettingsSpider(DefaultSpider):
            custom_settings = spider_settings

        settings = Settings()
        settings.setdict(project_settings, priority="project")
        crawler = Crawler(CustomSettingsSpider, settings)
        crawler._apply_settings()

        self.assertEqual(crawler.settings.get("TEST1"), "spider")
        self.assertEqual(crawler.settings.get("TEST2"), "spider")
        self.assertEqual(crawler.settings.get("TEST3"), "project")

        self.assertFalse(settings.frozen)
        self.assertTrue(crawler.settings.frozen)

    def test_crawler_accepts_dict(self):
        crawler = get_crawler(DefaultSpider, {"foo": "bar"})
        self.assertEqual(crawler.settings["foo"], "bar")
        self.assertOptionIsDefault(crawler.settings, "RETRY_ENABLED")

    def test_crawler_accepts_None(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ScrapyDeprecationWarning)
            crawler = Crawler(DefaultSpider)
        self.assertOptionIsDefault(crawler.settings, "RETRY_ENABLED")

    def test_crawler_rejects_spider_objects(self):
        with raises(ValueError):
            Crawler(DefaultSpider())

    @inlineCallbacks
    def test_crawler_crawl_twice_unsupported(self):
        crawler = get_raw_crawler(NoRequestsSpider, BASE_SETTINGS)
        yield crawler.crawl()
        with raises(RuntimeError, match="more than once on the same instance"):
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
        self.assertEqual(len(TrackingAddon.instances), 1)
        expected = TrackingAddon.instances[-1]

        addon = crawler.get_addon(TrackingAddon)
        self.assertEqual(addon, expected)

        addon = crawler.get_addon(DefaultSpider)
        self.assertIsNone(addon)

        addon = crawler.get_addon(ParentAddon)
        self.assertEqual(addon, expected)

        class ChildAddon(TrackingAddon):
            pass

        addon = crawler.get_addon(ChildAddon)
        self.assertIsNone(addon)

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

            def start_requests(self):
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
        self.assertEqual(len(TrackingDownloaderMiddleware.instances), 1)
        self.assertEqual(MySpider.result, TrackingDownloaderMiddleware.instances[-1])

        crawler = get_raw_crawler(MySpider, settings)
        MySpider.cls = DefaultSpider
        yield crawler.crawl()
        self.assertIsNone(MySpider.result)

        crawler = get_raw_crawler(MySpider, settings)
        MySpider.cls = ParentDownloaderMiddleware
        yield crawler.crawl()
        self.assertEqual(MySpider.result, TrackingDownloaderMiddleware.instances[-1])

        class ChildDownloaderMiddleware(TrackingDownloaderMiddleware):
            pass

        crawler = get_raw_crawler(MySpider, settings)
        MySpider.cls = ChildDownloaderMiddleware
        yield crawler.crawl()
        self.assertIsNone(MySpider.result)

    def test_get_downloader_middleware_not_crawling(self):
        crawler = get_raw_crawler(settings_dict=BASE_SETTINGS)
        self.assertRaises(
            RuntimeError, crawler.get_downloader_middleware, DefaultSpider
        )

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
        with raises(RuntimeError):
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

            def start_requests(self):
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
        self.assertEqual(len(TrackingExtension.instances), 1)
        self.assertEqual(MySpider.result, TrackingExtension.instances[-1])

        crawler = get_raw_crawler(MySpider, settings)
        MySpider.cls = DefaultSpider
        yield crawler.crawl()
        self.assertIsNone(MySpider.result)

        crawler = get_raw_crawler(MySpider, settings)
        MySpider.cls = ParentExtension
        yield crawler.crawl()
        self.assertEqual(MySpider.result, TrackingExtension.instances[-1])

        class ChildExtension(TrackingExtension):
            pass

        crawler = get_raw_crawler(MySpider, settings)
        MySpider.cls = ChildExtension
        yield crawler.crawl()
        self.assertIsNone(MySpider.result)

    def test_get_extension_not_crawling(self):
        crawler = get_raw_crawler(settings_dict=BASE_SETTINGS)
        self.assertRaises(RuntimeError, crawler.get_extension, DefaultSpider)

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
        with raises(RuntimeError):
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

            def start_requests(self):
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
        self.assertEqual(len(TrackingItemPipeline.instances), 1)
        self.assertEqual(MySpider.result, TrackingItemPipeline.instances[-1])

        crawler = get_raw_crawler(MySpider, settings)
        MySpider.cls = DefaultSpider
        yield crawler.crawl()
        self.assertIsNone(MySpider.result)

        crawler = get_raw_crawler(MySpider, settings)
        MySpider.cls = ParentItemPipeline
        yield crawler.crawl()
        self.assertEqual(MySpider.result, TrackingItemPipeline.instances[-1])

        class ChildItemPipeline(TrackingItemPipeline):
            pass

        crawler = get_raw_crawler(MySpider, settings)
        MySpider.cls = ChildItemPipeline
        yield crawler.crawl()
        self.assertIsNone(MySpider.result)

    def test_get_item_pipeline_not_crawling(self):
        crawler = get_raw_crawler(settings_dict=BASE_SETTINGS)
        self.assertRaises(RuntimeError, crawler.get_item_pipeline, DefaultSpider)

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
        with raises(RuntimeError):
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

            def start_requests(self):
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
        self.assertEqual(len(TrackingSpiderMiddleware.instances), 1)
        self.assertEqual(MySpider.result, TrackingSpiderMiddleware.instances[-1])

        crawler = get_raw_crawler(MySpider, settings)
        MySpider.cls = DefaultSpider
        yield crawler.crawl()
        self.assertIsNone(MySpider.result)

        crawler = get_raw_crawler(MySpider, settings)
        MySpider.cls = ParentSpiderMiddleware
        yield crawler.crawl()
        self.assertEqual(MySpider.result, TrackingSpiderMiddleware.instances[-1])

        class ChildSpiderMiddleware(TrackingSpiderMiddleware):
            pass

        crawler = get_raw_crawler(MySpider, settings)
        MySpider.cls = ChildSpiderMiddleware
        yield crawler.crawl()
        self.assertIsNone(MySpider.result)

    def test_get_spider_middleware_not_crawling(self):
        crawler = get_raw_crawler(settings_dict=BASE_SETTINGS)
        self.assertRaises(RuntimeError, crawler.get_spider_middleware, DefaultSpider)

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
        with raises(RuntimeError):
            yield crawler.crawl()


class SpiderSettingsTestCase(unittest.TestCase):
    def test_spider_custom_settings(self):
        class MySpider(scrapy.Spider):
            name = "spider"
            custom_settings = {"AUTOTHROTTLE_ENABLED": True}

        crawler = get_crawler(MySpider)
        enabled_exts = [e.__class__ for e in crawler.extensions.middlewares]
        self.assertIn(AutoThrottle, enabled_exts)


class CrawlerLoggingTestCase(unittest.TestCase):
    def test_no_root_handler_installed(self):
        handler = get_scrapy_root_handler()
        if handler is not None:
            logging.root.removeHandler(handler)

        class MySpider(scrapy.Spider):
            name = "spider"

        get_crawler(MySpider)
        assert get_scrapy_root_handler() is None

    def test_spider_custom_settings_log_level(self):
        log_file = Path(self.mktemp())
        log_file.write_text("previous message\n", encoding="utf-8")

        class MySpider(scrapy.Spider):
            name = "spider"
            custom_settings = {
                "LOG_LEVEL": "INFO",
                "LOG_FILE": str(log_file),
            }

        configure_logging()
        self.assertEqual(get_scrapy_root_handler().level, logging.DEBUG)
        crawler = get_crawler(MySpider)
        self.assertEqual(get_scrapy_root_handler().level, logging.INFO)
        info_count = crawler.stats.get_value("log_count/INFO")
        logging.debug("debug message")
        logging.info("info message")
        logging.warning("warning message")
        logging.error("error message")

        logged = log_file.read_text(encoding="utf-8")

        self.assertIn("previous message", logged)
        self.assertNotIn("debug message", logged)
        self.assertIn("info message", logged)
        self.assertIn("warning message", logged)
        self.assertIn("error message", logged)
        self.assertEqual(crawler.stats.get_value("log_count/ERROR"), 1)
        self.assertEqual(crawler.stats.get_value("log_count/WARNING"), 1)
        self.assertEqual(crawler.stats.get_value("log_count/INFO") - info_count, 1)
        self.assertEqual(crawler.stats.get_value("log_count/DEBUG", 0), 0)

    def test_spider_custom_settings_log_append(self):
        log_file = Path(self.mktemp())
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

        self.assertNotIn("previous message", logged)
        self.assertIn("debug message", logged)


class SpiderLoaderWithWrongInterface:
    def unneeded_method(self):
        pass


class CustomSpiderLoader(SpiderLoader):
    pass


class CrawlerRunnerTestCase(BaseCrawlerTest):
    def test_spider_manager_verify_interface(self):
        settings = Settings(
            {
                "SPIDER_LOADER_CLASS": SpiderLoaderWithWrongInterface,
            }
        )
        self.assertRaises(MultipleInvalid, CrawlerRunner, settings)

    def test_crawler_runner_accepts_dict(self):
        runner = CrawlerRunner({"foo": "bar"})
        self.assertEqual(runner.settings["foo"], "bar")
        self.assertOptionIsDefault(runner.settings, "RETRY_ENABLED")

    def test_crawler_runner_accepts_None(self):
        runner = CrawlerRunner()
        self.assertOptionIsDefault(runner.settings, "RETRY_ENABLED")


class CrawlerProcessTest(BaseCrawlerTest):
    def test_crawler_process_accepts_dict(self):
        runner = CrawlerProcess({"foo": "bar"})
        self.assertEqual(runner.settings["foo"], "bar")
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

    def start_requests(self):
        return []


@mark.usefixtures("reactor_pytest")
class CrawlerRunnerHasSpider(unittest.TestCase):
    def _runner(self):
        return CrawlerRunner()

    @inlineCallbacks
    def test_crawler_runner_bootstrap_successful(self):
        runner = self._runner()
        yield runner.crawl(NoRequestsSpider)
        self.assertFalse(runner.bootstrap_failed)

    @inlineCallbacks
    def test_crawler_runner_bootstrap_successful_for_several(self):
        runner = self._runner()
        yield runner.crawl(NoRequestsSpider)
        yield runner.crawl(NoRequestsSpider)
        self.assertFalse(runner.bootstrap_failed)

    @inlineCallbacks
    def test_crawler_runner_bootstrap_failed(self):
        runner = self._runner()

        try:
            yield runner.crawl(ExceptionSpider)
        except ValueError:
            pass
        else:
            self.fail("Exception should be raised from spider")

        self.assertTrue(runner.bootstrap_failed)

    @inlineCallbacks
    def test_crawler_runner_bootstrap_failed_for_several(self):
        runner = self._runner()

        try:
            yield runner.crawl(ExceptionSpider)
        except ValueError:
            pass
        else:
            self.fail("Exception should be raised from spider")

        yield runner.crawl(NoRequestsSpider)

        self.assertTrue(runner.bootstrap_failed)

    @inlineCallbacks
    def test_crawler_runner_asyncio_enabled_true(self):
        if self.reactor_pytest == "asyncio":
            CrawlerRunner(
                settings={
                    "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
                }
            )
        else:
            msg = r"The installed reactor \(.*?\) does not match the requested one \(.*?\)"
            with self.assertRaisesRegex(Exception, msg):
                runner = CrawlerRunner(
                    settings={
                        "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
                    }
                )
                yield runner.crawl(NoRequestsSpider)


class ScriptRunnerMixin:
    script_dir: Path
    cwd = os.getcwd()

    def get_script_args(self, script_name: str, *script_args: str) -> list[str]:
        script_path = self.script_dir / script_name
        return [sys.executable, str(script_path)] + list(script_args)

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


class CrawlerProcessSubprocess(ScriptRunnerMixin, unittest.TestCase):
    script_dir = Path(__file__).parent.resolve() / "CrawlerProcess"

    def test_simple(self):
        log = self.run_script("simple.py")
        self.assertIn("Spider closed (finished)", log)
        self.assertNotIn(
            "Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor", log
        )

    def test_multi(self):
        log = self.run_script("multi.py")
        self.assertIn("Spider closed (finished)", log)
        self.assertNotIn(
            "Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor", log
        )
        self.assertNotIn("ReactorAlreadyInstalledError", log)

    def test_reactor_default(self):
        log = self.run_script("reactor_default.py")
        self.assertIn("Spider closed (finished)", log)
        self.assertNotIn(
            "Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor", log
        )
        self.assertNotIn("ReactorAlreadyInstalledError", log)

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
            self.assertIn("Spider closed (finished)", log)
        else:
            self.assertNotIn("Spider closed (finished)", log)
            self.assertIn(
                (
                    "does not match the requested one "
                    "(twisted.internet.selectreactor.SelectReactor)"
                ),
                log,
            )

    def test_reactor_select(self):
        log = self.run_script("reactor_select.py")
        self.assertIn("Spider closed (finished)", log)
        self.assertNotIn("ReactorAlreadyInstalledError", log)

    def test_reactor_select_twisted_reactor_select(self):
        log = self.run_script("reactor_select_twisted_reactor_select.py")
        self.assertIn("Spider closed (finished)", log)
        self.assertNotIn("ReactorAlreadyInstalledError", log)

    def test_reactor_select_subclass_twisted_reactor_select(self):
        log = self.run_script("reactor_select_subclass_twisted_reactor_select.py")
        self.assertNotIn("Spider closed (finished)", log)
        self.assertIn(
            (
                "does not match the requested one "
                "(twisted.internet.selectreactor.SelectReactor)"
            ),
            log,
        )

    def test_asyncio_enabled_no_reactor(self):
        log = self.run_script("asyncio_enabled_no_reactor.py")
        self.assertIn("Spider closed (finished)", log)
        self.assertIn(
            "Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor", log
        )

    def test_asyncio_enabled_reactor(self):
        log = self.run_script("asyncio_enabled_reactor.py")
        self.assertIn("Spider closed (finished)", log)
        self.assertIn(
            "Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor", log
        )

    @mark.skipif(
        parse_version(w3lib_version) >= parse_version("2.0.0"),
        reason="w3lib 2.0.0 and later do not allow invalid domains.",
    )
    def test_ipv6_default_name_resolver(self):
        log = self.run_script("default_name_resolver.py")
        self.assertIn("Spider closed (finished)", log)
        self.assertIn(
            "'downloader/exception_type_count/twisted.internet.error.DNSLookupError': 1,",
            log,
        )
        self.assertIn(
            "twisted.internet.error.DNSLookupError: DNS lookup failed: no results for hostname lookup: ::1.",
            log,
        )

    def test_caching_hostname_resolver_ipv6(self):
        log = self.run_script("caching_hostname_resolver_ipv6.py")
        self.assertIn("Spider closed (finished)", log)
        self.assertNotIn("twisted.internet.error.DNSLookupError", log)

    def test_caching_hostname_resolver_finite_execution(self):
        with MockServer() as mock_server:
            http_address = mock_server.http_address.replace("0.0.0.0", "127.0.0.1")
            log = self.run_script("caching_hostname_resolver.py", http_address)
            self.assertIn("Spider closed (finished)", log)
            self.assertNotIn("ERROR: Error downloading", log)
            self.assertNotIn("TimeoutError", log)
            self.assertNotIn("twisted.internet.error.DNSLookupError", log)

    def test_twisted_reactor_select(self):
        log = self.run_script("twisted_reactor_select.py")
        self.assertIn("Spider closed (finished)", log)
        self.assertIn(
            "Using reactor: twisted.internet.selectreactor.SelectReactor", log
        )

    @mark.skipif(
        platform.system() == "Windows", reason="PollReactor is not supported on Windows"
    )
    def test_twisted_reactor_poll(self):
        log = self.run_script("twisted_reactor_poll.py")
        self.assertIn("Spider closed (finished)", log)
        self.assertIn("Using reactor: twisted.internet.pollreactor.PollReactor", log)

    def test_twisted_reactor_asyncio(self):
        log = self.run_script("twisted_reactor_asyncio.py")
        self.assertIn("Spider closed (finished)", log)
        self.assertIn(
            "Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor", log
        )

    def test_twisted_reactor_asyncio_custom_settings(self):
        log = self.run_script("twisted_reactor_custom_settings.py")
        self.assertIn("Spider closed (finished)", log)
        self.assertIn(
            "Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor", log
        )

    def test_twisted_reactor_asyncio_custom_settings_same(self):
        log = self.run_script("twisted_reactor_custom_settings_same.py")
        self.assertIn("Spider closed (finished)", log)
        self.assertIn(
            "Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor", log
        )

    def test_twisted_reactor_asyncio_custom_settings_conflict(self):
        log = self.run_script("twisted_reactor_custom_settings_conflict.py")
        self.assertIn(
            "Using reactor: twisted.internet.selectreactor.SelectReactor", log
        )
        self.assertIn(
            "(twisted.internet.selectreactor.SelectReactor) does not match the requested one",
            log,
        )

    @mark.requires_uvloop
    def test_custom_loop_asyncio(self):
        log = self.run_script("asyncio_custom_loop.py")
        self.assertIn("Spider closed (finished)", log)
        self.assertIn(
            "Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor", log
        )
        self.assertIn("Using asyncio event loop: uvloop.Loop", log)

    @mark.requires_uvloop
    def test_custom_loop_asyncio_deferred_signal(self):
        log = self.run_script("asyncio_deferred_signal.py", "uvloop.Loop")
        self.assertIn("Spider closed (finished)", log)
        self.assertIn(
            "Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor", log
        )
        self.assertIn("Using asyncio event loop: uvloop.Loop", log)
        self.assertIn("async pipeline opened!", log)

    @mark.requires_uvloop
    def test_asyncio_enabled_reactor_same_loop(self):
        log = self.run_script("asyncio_enabled_reactor_same_loop.py")
        self.assertIn("Spider closed (finished)", log)
        self.assertIn(
            "Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor", log
        )
        self.assertIn("Using asyncio event loop: uvloop.Loop", log)

    @mark.requires_uvloop
    def test_asyncio_enabled_reactor_different_loop(self):
        log = self.run_script("asyncio_enabled_reactor_different_loop.py")
        self.assertNotIn("Spider closed (finished)", log)
        self.assertIn(
            (
                "does not match the one specified in the ASYNCIO_EVENT_LOOP "
                "setting (uvloop.Loop)"
            ),
            log,
        )

    def test_default_loop_asyncio_deferred_signal(self):
        log = self.run_script("asyncio_deferred_signal.py")
        self.assertIn("Spider closed (finished)", log)
        self.assertIn(
            "Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor", log
        )
        self.assertNotIn("Using asyncio event loop: uvloop.Loop", log)
        self.assertIn("async pipeline opened!", log)

    def test_args_change_settings(self):
        log = self.run_script("args_settings.py")
        self.assertIn("Spider closed (finished)", log)
        self.assertIn("The value of FOO is 42", log)

    def test_shutdown_graceful(self):
        sig = signal.SIGINT if sys.platform != "win32" else signal.SIGBREAK
        args = self.get_script_args("sleeping.py", "-a", "sleep=3")
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
        args = self.get_script_args("sleeping.py", "-a", "sleep=10")
        p = PopenSpawn(args, timeout=5)
        p.expect_exact("Spider opened")
        p.expect_exact("Crawled (200)")
        p.kill(sig)
        p.expect_exact("shutting down gracefully")
        # sending the second signal too fast often causes problems
        d = Deferred()
        reactor.callLater(0.1, d.callback, None)
        yield d
        p.kill(sig)
        p.expect_exact("forcing unclean shutdown")
        p.wait()


class CrawlerRunnerSubprocess(ScriptRunnerMixin, unittest.TestCase):
    script_dir = Path(__file__).parent.resolve() / "CrawlerRunner"

    def test_response_ip_address(self):
        log = self.run_script("ip_address.py")
        self.assertIn("INFO: Spider closed (finished)", log)
        self.assertIn("INFO: Host: not.a.real.domain", log)
        self.assertIn("INFO: Type: <class 'ipaddress.IPv4Address'>", log)
        self.assertIn("INFO: IP address: 127.0.0.1", log)

    def test_change_default_reactor(self):
        log = self.run_script("change_reactor.py")
        self.assertIn(
            "DEBUG: Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor",
            log,
        )
        self.assertIn("DEBUG: Using asyncio event loop", log)
