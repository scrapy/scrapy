import logging
import os
import platform
import subprocess
import sys
import warnings

from pytest import raises, mark
from twisted import version as twisted_version
from twisted.internet import defer
from twisted.python.versions import Version
from twisted.trial import unittest

import scrapy
from scrapy.crawler import Crawler, CrawlerRunner, CrawlerProcess
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.settings import Settings, default_settings
from scrapy.spiderloader import SpiderLoader
from scrapy.utils.log import configure_logging, get_scrapy_root_handler
from scrapy.utils.spider import DefaultSpider
from scrapy.utils.misc import load_object
from scrapy.utils.test import get_crawler
from scrapy.extensions.throttle import AutoThrottle
from scrapy.extensions import telnet
from scrapy.utils.test import get_testenv
from pkg_resources import parse_version
from w3lib import __version__ as w3lib_version

from tests.mockserver import MockServer


class BaseCrawlerTest(unittest.TestCase):

    def assertOptionIsDefault(self, settings, key):
        self.assertIsInstance(settings, Settings)
        self.assertEqual(settings[key], getattr(default_settings, key))


class CrawlerTestCase(BaseCrawlerTest):

    def test_populate_spidercls_settings(self):
        spider_settings = {'TEST1': 'spider', 'TEST2': 'spider'}
        project_settings = {'TEST1': 'project', 'TEST3': 'project'}

        class CustomSettingsSpider(DefaultSpider):
            custom_settings = spider_settings

        settings = Settings()
        settings.setdict(project_settings, priority='project')
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ScrapyDeprecationWarning)
            crawler = Crawler(CustomSettingsSpider, settings)

        self.assertEqual(crawler.settings.get('TEST1'), 'spider')
        self.assertEqual(crawler.settings.get('TEST2'), 'spider')
        self.assertEqual(crawler.settings.get('TEST3'), 'project')

        self.assertFalse(settings.frozen)
        self.assertTrue(crawler.settings.frozen)

    def test_crawler_accepts_dict(self):
        crawler = get_crawler(DefaultSpider, {'foo': 'bar'})
        self.assertEqual(crawler.settings['foo'], 'bar')
        self.assertOptionIsDefault(crawler.settings, 'RETRY_ENABLED')

    def test_crawler_accepts_None(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ScrapyDeprecationWarning)
            crawler = Crawler(DefaultSpider)
        self.assertOptionIsDefault(crawler.settings, 'RETRY_ENABLED')

    def test_crawler_rejects_spider_objects(self):
        with raises(ValueError):
            Crawler(DefaultSpider())


class SpiderSettingsTestCase(unittest.TestCase):
    def test_spider_custom_settings(self):
        class MySpider(scrapy.Spider):
            name = 'spider'
            custom_settings = {
                'AUTOTHROTTLE_ENABLED': True
            }

        crawler = get_crawler(MySpider)
        enabled_exts = [e.__class__ for e in crawler.extensions.middlewares]
        self.assertIn(AutoThrottle, enabled_exts)


class CrawlerLoggingTestCase(unittest.TestCase):
    def test_no_root_handler_installed(self):
        handler = get_scrapy_root_handler()
        if handler is not None:
            logging.root.removeHandler(handler)

        class MySpider(scrapy.Spider):
            name = 'spider'

        get_crawler(MySpider)
        assert get_scrapy_root_handler() is None

    def test_spider_custom_settings_log_level(self):
        log_file = self.mktemp()
        with open(log_file, 'wb') as fo:
            fo.write('previous message\n'.encode('utf-8'))

        class MySpider(scrapy.Spider):
            name = 'spider'
            custom_settings = {
                'LOG_LEVEL': 'INFO',
                'LOG_FILE': log_file,
                # settings to avoid extra warnings
                'REQUEST_FINGERPRINTER_IMPLEMENTATION': '2.7',
                'TELNETCONSOLE_ENABLED': telnet.TWISTED_CONCH_AVAILABLE,
            }

        configure_logging()
        self.assertEqual(get_scrapy_root_handler().level, logging.DEBUG)
        crawler = get_crawler(MySpider)
        self.assertEqual(get_scrapy_root_handler().level, logging.INFO)
        info_count = crawler.stats.get_value('log_count/INFO')
        logging.debug('debug message')
        logging.info('info message')
        logging.warning('warning message')
        logging.error('error message')

        with open(log_file, 'rb') as fo:
            logged = fo.read().decode('utf-8')

        self.assertIn('previous message', logged)
        self.assertNotIn('debug message', logged)
        self.assertIn('info message', logged)
        self.assertIn('warning message', logged)
        self.assertIn('error message', logged)
        self.assertEqual(crawler.stats.get_value('log_count/ERROR'), 1)
        self.assertEqual(crawler.stats.get_value('log_count/WARNING'), 1)
        self.assertEqual(
            crawler.stats.get_value('log_count/INFO') - info_count, 1)
        self.assertEqual(crawler.stats.get_value('log_count/DEBUG', 0), 0)

    def test_spider_custom_settings_log_append(self):
        log_file = self.mktemp()
        with open(log_file, 'wb') as fo:
            fo.write('previous message\n'.encode('utf-8'))

        class MySpider(scrapy.Spider):
            name = 'spider'
            custom_settings = {
                'LOG_FILE': log_file,
                'LOG_FILE_APPEND': False,
                # disable telnet if not available to avoid an extra warning
                'TELNETCONSOLE_ENABLED': telnet.TWISTED_CONCH_AVAILABLE,
            }

        configure_logging()
        get_crawler(MySpider)
        logging.debug('debug message')

        with open(log_file, 'rb') as fo:
            logged = fo.read().decode('utf-8')

        self.assertNotIn('previous message', logged)
        self.assertIn('debug message', logged)


class SpiderLoaderWithWrongInterface:

    def unneeded_method(self):
        pass


class CustomSpiderLoader(SpiderLoader):
    pass


class CrawlerRunnerTestCase(BaseCrawlerTest):

    def test_spider_manager_verify_interface(self):
        settings = Settings({
            'SPIDER_LOADER_CLASS': SpiderLoaderWithWrongInterface,
        })
        with warnings.catch_warnings(record=True) as w:
            self.assertRaises(AttributeError, CrawlerRunner, settings)
            self.assertEqual(len(w), 1)
            self.assertIn("SPIDER_LOADER_CLASS", str(w[0].message))
            self.assertIn("scrapy.interfaces.ISpiderLoader", str(w[0].message))

    def test_crawler_runner_accepts_dict(self):
        runner = CrawlerRunner({'foo': 'bar'})
        self.assertEqual(runner.settings['foo'], 'bar')
        self.assertOptionIsDefault(runner.settings, 'RETRY_ENABLED')

    def test_crawler_runner_accepts_None(self):
        runner = CrawlerRunner()
        self.assertOptionIsDefault(runner.settings, 'RETRY_ENABLED')

    def test_deprecated_attribute_spiders(self):
        with warnings.catch_warnings(record=True) as w:
            runner = CrawlerRunner(Settings())
            spiders = runner.spiders
            self.assertEqual(len(w), 1)
            self.assertIn("CrawlerRunner.spiders", str(w[0].message))
            self.assertIn("CrawlerRunner.spider_loader", str(w[0].message))
            sl_cls = load_object(runner.settings['SPIDER_LOADER_CLASS'])
            self.assertIsInstance(spiders, sl_cls)


class CrawlerProcessTest(BaseCrawlerTest):
    def test_crawler_process_accepts_dict(self):
        runner = CrawlerProcess({'foo': 'bar'})
        self.assertEqual(runner.settings['foo'], 'bar')
        self.assertOptionIsDefault(runner.settings, 'RETRY_ENABLED')

    def test_crawler_process_accepts_None(self):
        runner = CrawlerProcess()
        self.assertOptionIsDefault(runner.settings, 'RETRY_ENABLED')


class ExceptionSpider(scrapy.Spider):
    name = 'exception'

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        raise ValueError('Exception in from_crawler method')


class NoRequestsSpider(scrapy.Spider):
    name = 'no_request'

    def start_requests(self):
        return []


@mark.usefixtures('reactor_pytest')
class CrawlerRunnerHasSpider(unittest.TestCase):

    def _runner(self):
        return CrawlerRunner({'REQUEST_FINGERPRINTER_IMPLEMENTATION': '2.7'})

    @defer.inlineCallbacks
    def test_crawler_runner_bootstrap_successful(self):
        runner = self._runner()
        yield runner.crawl(NoRequestsSpider)
        self.assertEqual(runner.bootstrap_failed, False)

    @defer.inlineCallbacks
    def test_crawler_runner_bootstrap_successful_for_several(self):
        runner = self._runner()
        yield runner.crawl(NoRequestsSpider)
        yield runner.crawl(NoRequestsSpider)
        self.assertEqual(runner.bootstrap_failed, False)

    @defer.inlineCallbacks
    def test_crawler_runner_bootstrap_failed(self):
        runner = self._runner()

        try:
            yield runner.crawl(ExceptionSpider)
        except ValueError:
            pass
        else:
            self.fail('Exception should be raised from spider')

        self.assertEqual(runner.bootstrap_failed, True)

    @defer.inlineCallbacks
    def test_crawler_runner_bootstrap_failed_for_several(self):
        runner = self._runner()

        try:
            yield runner.crawl(ExceptionSpider)
        except ValueError:
            pass
        else:
            self.fail('Exception should be raised from spider')

        yield runner.crawl(NoRequestsSpider)

        self.assertEqual(runner.bootstrap_failed, True)

    @defer.inlineCallbacks
    def test_crawler_runner_asyncio_enabled_true(self):
        if self.reactor_pytest == 'asyncio':
            CrawlerRunner(settings={
                "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
                "REQUEST_FINGERPRINTER_IMPLEMENTATION": "2.7",
            })
        else:
            msg = r"The installed reactor \(.*?\) does not match the requested one \(.*?\)"
            with self.assertRaisesRegex(Exception, msg):
                runner = CrawlerRunner(settings={
                    "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
                    "REQUEST_FINGERPRINTER_IMPLEMENTATION": "2.7",
                })
                yield runner.crawl(NoRequestsSpider)


class ScriptRunnerMixin:
    def run_script(self, script_name, *script_args):
        script_path = os.path.join(self.script_dir, script_name)
        args = [sys.executable, script_path] + list(script_args)
        p = subprocess.Popen(args, env=get_testenv(),
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = p.communicate()
        return stderr.decode('utf-8')


class CrawlerProcessSubprocess(ScriptRunnerMixin, unittest.TestCase):
    script_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'CrawlerProcess')

    def test_simple(self):
        log = self.run_script('simple.py')
        self.assertIn('Spider closed (finished)', log)
        self.assertNotIn("Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor", log)

    def test_multi(self):
        log = self.run_script('multi.py')
        self.assertIn('Spider closed (finished)', log)
        self.assertNotIn("Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor", log)
        self.assertNotIn("ReactorAlreadyInstalledError", log)

    def test_reactor_default(self):
        log = self.run_script('reactor_default.py')
        self.assertIn('Spider closed (finished)', log)
        self.assertNotIn("Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor", log)
        self.assertNotIn("ReactorAlreadyInstalledError", log)

    def test_reactor_default_twisted_reactor_select(self):
        log = self.run_script('reactor_default_twisted_reactor_select.py')
        if platform.system() in ['Windows', 'Darwin']:
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
            self.assertIn('Spider closed (finished)', log)
        else:
            self.assertNotIn('Spider closed (finished)', log)
            self.assertIn(
                (
                    "does not match the requested one "
                    "(twisted.internet.selectreactor.SelectReactor)"
                ),
                log,
            )

    def test_reactor_select(self):
        log = self.run_script('reactor_select.py')
        self.assertIn('Spider closed (finished)', log)
        self.assertNotIn("ReactorAlreadyInstalledError", log)

    def test_reactor_select_twisted_reactor_select(self):
        log = self.run_script('reactor_select_twisted_reactor_select.py')
        self.assertIn('Spider closed (finished)', log)
        self.assertNotIn("ReactorAlreadyInstalledError", log)

    def test_reactor_select_subclass_twisted_reactor_select(self):
        log = self.run_script('reactor_select_subclass_twisted_reactor_select.py')
        self.assertNotIn('Spider closed (finished)', log)
        self.assertIn(
            (
                "does not match the requested one "
                "(twisted.internet.selectreactor.SelectReactor)"
            ),
            log,
        )

    def test_asyncio_enabled_no_reactor(self):
        log = self.run_script('asyncio_enabled_no_reactor.py')
        self.assertIn('Spider closed (finished)', log)
        self.assertIn("Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor", log)

    def test_asyncio_enabled_reactor(self):
        log = self.run_script('asyncio_enabled_reactor.py')
        self.assertIn('Spider closed (finished)', log)
        self.assertIn("Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor", log)

    @mark.skipif(parse_version(w3lib_version) >= parse_version("2.0.0"),
                 reason='w3lib 2.0.0 and later do not allow invalid domains.')
    def test_ipv6_default_name_resolver(self):
        log = self.run_script('default_name_resolver.py')
        self.assertIn('Spider closed (finished)', log)
        self.assertIn("'downloader/exception_type_count/twisted.internet.error.DNSLookupError': 1,", log)
        self.assertIn(
            "twisted.internet.error.DNSLookupError: DNS lookup failed: no results for hostname lookup: ::1.",
            log)

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
        self.assertIn("Using reactor: twisted.internet.selectreactor.SelectReactor", log)

    @mark.skipif(platform.system() == 'Windows', reason="PollReactor is not supported on Windows")
    def test_twisted_reactor_poll(self):
        log = self.run_script("twisted_reactor_poll.py")
        self.assertIn("Spider closed (finished)", log)
        self.assertIn("Using reactor: twisted.internet.pollreactor.PollReactor", log)

    def test_twisted_reactor_asyncio(self):
        log = self.run_script("twisted_reactor_asyncio.py")
        self.assertIn("Spider closed (finished)", log)
        self.assertIn("Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor", log)

    def test_twisted_reactor_asyncio_custom_settings(self):
        log = self.run_script("twisted_reactor_custom_settings.py")
        self.assertIn("Spider closed (finished)", log)
        self.assertIn("Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor", log)

    def test_twisted_reactor_asyncio_custom_settings_same(self):
        log = self.run_script("twisted_reactor_custom_settings_same.py")
        self.assertIn("Spider closed (finished)", log)
        self.assertIn("Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor", log)

    def test_twisted_reactor_asyncio_custom_settings_conflict(self):
        log = self.run_script("twisted_reactor_custom_settings_conflict.py")
        self.assertIn("Using reactor: twisted.internet.selectreactor.SelectReactor", log)
        self.assertIn("(twisted.internet.selectreactor.SelectReactor) does not match the requested one", log)

    @mark.skipif(sys.implementation.name == 'pypy', reason='uvloop does not support pypy properly')
    @mark.skipif(platform.system() == 'Windows', reason='uvloop does not support Windows')
    @mark.skipif(twisted_version == Version('twisted', 21, 2, 0), reason='https://twistedmatrix.com/trac/ticket/10106')
    def test_custom_loop_asyncio(self):
        log = self.run_script("asyncio_custom_loop.py")
        self.assertIn("Spider closed (finished)", log)
        self.assertIn("Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor", log)
        self.assertIn("Using asyncio event loop: uvloop.Loop", log)

    @mark.skipif(sys.implementation.name == "pypy", reason="uvloop does not support pypy properly")
    @mark.skipif(platform.system() == "Windows", reason="uvloop does not support Windows")
    @mark.skipif(twisted_version == Version('twisted', 21, 2, 0), reason='https://twistedmatrix.com/trac/ticket/10106')
    def test_custom_loop_asyncio_deferred_signal(self):
        log = self.run_script("asyncio_deferred_signal.py", "uvloop.Loop")
        self.assertIn("Spider closed (finished)", log)
        self.assertIn("Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor", log)
        self.assertIn("Using asyncio event loop: uvloop.Loop", log)
        self.assertIn("async pipeline opened!", log)

    @mark.skipif(sys.implementation.name == 'pypy', reason='uvloop does not support pypy properly')
    @mark.skipif(platform.system() == 'Windows', reason='uvloop does not support Windows')
    @mark.skipif(twisted_version == Version('twisted', 21, 2, 0), reason='https://twistedmatrix.com/trac/ticket/10106')
    def test_asyncio_enabled_reactor_same_loop(self):
        log = self.run_script("asyncio_enabled_reactor_same_loop.py")
        self.assertIn("Spider closed (finished)", log)
        self.assertIn("Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor", log)
        self.assertIn("Using asyncio event loop: uvloop.Loop", log)

    @mark.skipif(sys.implementation.name == 'pypy', reason='uvloop does not support pypy properly')
    @mark.skipif(platform.system() == 'Windows', reason='uvloop does not support Windows')
    @mark.skipif(twisted_version == Version('twisted', 21, 2, 0), reason='https://twistedmatrix.com/trac/ticket/10106')
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
        self.assertIn("Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor", log)
        self.assertNotIn("Using asyncio event loop: uvloop.Loop", log)
        self.assertIn("async pipeline opened!", log)


class CrawlerRunnerSubprocess(ScriptRunnerMixin, unittest.TestCase):
    script_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'CrawlerRunner')

    def test_response_ip_address(self):
        log = self.run_script("ip_address.py")
        self.assertIn("INFO: Spider closed (finished)", log)
        self.assertIn("INFO: Host: not.a.real.domain", log)
        self.assertIn("INFO: Type: <class 'ipaddress.IPv4Address'>", log)
        self.assertIn("INFO: IP address: 127.0.0.1", log)
