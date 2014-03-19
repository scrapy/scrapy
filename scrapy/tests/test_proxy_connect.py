import os
import subprocess
import time

from threading import Thread
from libmproxy import controller, proxy
from netlib import http_auth

from twisted.internet import defer
from twisted.trial.unittest import TestCase
from scrapy.utils.test import get_testlog, docrawl
from scrapy.tests.spiders import SimpleSpider
from scrapy.tests.mockserver import MockServer


class HTTPSProxy(controller.Master, Thread):

    def __init__(self, port):
        password_manager = http_auth.PassManSingleUser('scrapy', 'scrapy')
        authenticator = http_auth.BasicProxyAuth(password_manager, "mitmproxy")
        cert_path = os.path.join(os.path.abspath(os.path.dirname(__file__)),
                                 'keys', 'mitmproxy-ca.pem')
        server = proxy.ProxyServer(proxy.ProxyConfig(
            authenticator=authenticator,
            cacert=cert_path),
            port)
        Thread.__init__(self)
        controller.Master.__init__(self, server)


class ProxyConnectTestCase(TestCase):

    def setUp(self):
        self.mockserver = MockServer()
        self.mockserver.__enter__()
        self._oldenv = os.environ.copy()
        self._proxy = HTTPSProxy(8888)
        self._proxy.start()
        # Wait for the proxy to start.
        time.sleep(1.0)
        os.environ['http_proxy'] = 'http://scrapy:scrapy@localhost:8888'
        os.environ['https_proxy'] = 'http://scrapy:scrapy@localhost:8888'

    def tearDown(self):
        self.mockserver.__exit__(None, None, None)
        self._proxy.shutdown()
        os.environ = self._oldenv

    @defer.inlineCallbacks
    def test_https_connect_tunnel(self):
        spider = SimpleSpider("https://localhost:8999/status?n=200")
        yield docrawl(spider)
        self._assert_got_response_code(200)

    @defer.inlineCallbacks
    def test_https_noconnect(self):
        os.environ[
            'https_proxy'] = 'http://scrapy:scrapy@localhost:8888?noconnect'
        spider = SimpleSpider("https://localhost:8999/status?n=200")
        yield docrawl(spider)
        self._assert_got_response_code(200)
        os.environ['https_proxy'] = 'http://scrapy:scrapy@localhost:8888'

    @defer.inlineCallbacks
    def test_https_connect_tunnel_error(self):
        spider = SimpleSpider("https://localhost:99999/status?n=200")
        yield docrawl(spider)
        self._assert_got_tunnel_error()

    @defer.inlineCallbacks
    def test_https_tunnel_auth_error(self):
        os.environ['https_proxy'] = 'http://wrong:wronger@localhost:8888'
        spider = SimpleSpider("https://localhost:8999/status?n=200")
        yield docrawl(spider)
        # The proxy returns a 407 error code but it does not reach the client;
        # he just sees a TunnelError.
        self._assert_got_tunnel_error()
        os.environ['https_proxy'] = 'http://scrapy:scrapy@localhost:8888'

    @defer.inlineCallbacks
    def test_https_noconnect_auth_error(self):
        os.environ[
            'https_proxy'] = 'http://wrong:wronger@localhost:8888?noconnect'
        spider = SimpleSpider("https://localhost:8999/status?n=200")
        yield docrawl(spider)
        self._assert_got_response_code(407)

    def _assert_got_response_code(self, code):
        log = get_testlog()
        self.assertEqual(log.count('Crawled (%d)' % code), 1)

    def _assert_got_tunnel_error(self):
        log = get_testlog()
        self.assertEqual(log.count('TunnelError'), 1)
