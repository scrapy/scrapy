import json
import os
import re
from subprocess import Popen, PIPE
import sys
import time

import pytest
from six.moves.urllib.parse import urlsplit, urlunsplit
from testfixtures import LogCapture

from twisted.internet import defer
from twisted.trial.unittest import TestCase

from scrapy.utils.test import get_crawler
from scrapy.http import Request
from tests.spiders import SimpleSpider, SingleRequestSpider
from tests.mockserver import MockServer


class MitmProxy:
    auth_user = 'scrapy'
    auth_pass = 'scrapy'

    def start(self):
        from scrapy.utils.test import get_testenv
        script = """
import sys
from mitmproxy.tools.main import mitmdump
sys.argv[0] = "mitmdump"
sys.exit(mitmdump())
        """
        cert_path = os.path.join(os.path.abspath(os.path.dirname(__file__)),
            'keys', 'mitmproxy-ca.pem')
        self.proc = Popen([sys.executable,
                           '-c', script,
                           '--listen-host', '127.0.0.1',
                           '--listen-port', '0',
                           '--proxyauth', '%s:%s' % (self.auth_user, self.auth_pass),
                           '--certs', cert_path,
                           '--ssl-insecure',
                           ],
                           stdout=PIPE, env=get_testenv())
        line = self.proc.stdout.readline().decode('utf-8')
        host_port = re.search(r'listening at http://([^:]+:\d+)', line).group(1)
        address = 'http://%s:%s@%s' % (self.auth_user, self.auth_pass, host_port)
        return address

    def stop(self):
        self.proc.kill()
        self.proc.wait()
        time.sleep(0.2)


def _wrong_credentials(proxy_url):
    bad_auth_proxy = list(urlsplit(proxy_url))
    bad_auth_proxy[1] = bad_auth_proxy[1].replace('scrapy:scrapy@', 'wrong:wronger@')
    return urlunsplit(bad_auth_proxy)


class ProxyConnectTestCase(TestCase):

    def setUp(self):
        self.mockserver = MockServer()
        self.mockserver.__enter__()
        self._oldenv = os.environ.copy()

        self._proxy = MitmProxy()
        proxy_url = self._proxy.start()
        os.environ['https_proxy'] = proxy_url
        os.environ['http_proxy'] = proxy_url

    def tearDown(self):
        self.mockserver.__exit__(None, None, None)
        self._proxy.stop()
        os.environ = self._oldenv

    @defer.inlineCallbacks
    def test_https_connect_tunnel(self):
        crawler = get_crawler(SimpleSpider)
        with LogCapture() as l:
            yield crawler.crawl(self.mockserver.url("/status?n=200", is_secure=True))
        self._assert_got_response_code(200, l)

    @pytest.mark.xfail(reason='mitmproxy gives an error for noconnect requests')
    @defer.inlineCallbacks
    def test_https_noconnect(self):
        proxy = os.environ['https_proxy']
        os.environ['https_proxy'] = proxy + '?noconnect'
        crawler = get_crawler(SimpleSpider)
        with LogCapture() as l:
            yield crawler.crawl(self.mockserver.url("/status?n=200", is_secure=True))
        self._assert_got_response_code(200, l)

    @pytest.mark.xfail(reason='Python 3 fails this earlier')
    @defer.inlineCallbacks
    def test_https_connect_tunnel_error(self):
        crawler = get_crawler(SimpleSpider)
        with LogCapture() as l:
            yield crawler.crawl("https://localhost:99999/status?n=200")
        self._assert_got_tunnel_error(l)

    @defer.inlineCallbacks
    def test_https_tunnel_auth_error(self):
        os.environ['https_proxy'] = _wrong_credentials(os.environ['https_proxy'])
        crawler = get_crawler(SimpleSpider)
        with LogCapture() as l:
            yield crawler.crawl(self.mockserver.url("/status?n=200", is_secure=True))
        # The proxy returns a 407 error code but it does not reach the client;
        # he just sees a TunnelError.
        self._assert_got_tunnel_error(l)

    @defer.inlineCallbacks
    def test_https_tunnel_without_leak_proxy_authorization_header(self):
        request = Request(self.mockserver.url("/echo", is_secure=True))
        crawler = get_crawler(SingleRequestSpider)
        with LogCapture() as l:
            yield crawler.crawl(seed=request)
        self._assert_got_response_code(200, l)
        echo = json.loads(crawler.spider.meta['responses'][0].body)
        self.assertTrue('Proxy-Authorization' not in echo['headers'])

    @pytest.mark.xfail(reason='mitmproxy gives an error for noconnect requests')
    @defer.inlineCallbacks
    def test_https_noconnect_auth_error(self):
        os.environ['https_proxy'] = _wrong_credentials(os.environ['https_proxy']) + '?noconnect'
        crawler = get_crawler(SimpleSpider)
        with LogCapture() as l:
            yield crawler.crawl(self.mockserver.url("/status?n=200", is_secure=True))
        self._assert_got_response_code(407, l)

    def _assert_got_response_code(self, code, log):
        print(log)
        self.assertEqual(str(log).count('Crawled (%d)' % code), 1)

    def _assert_got_tunnel_error(self, log):
        print(log)
        self.assertIn('TunnelError', str(log))
