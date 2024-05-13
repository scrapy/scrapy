import json
import os
import re
import sys
from pathlib import Path
from subprocess import PIPE, Popen
from urllib.parse import urlsplit, urlunsplit

from testfixtures import LogCapture
from twisted.internet import defer
from twisted.trial.unittest import TestCase

from scrapy.http import Request
from scrapy.utils.test import get_crawler
from tests.mockserver import MockServer
from tests.spiders import SimpleSpider, SingleRequestSpider


class MitmProxy:
    auth_user = "scrapy"
    auth_pass = "scrapy"

    def start(self):
        script = """
import sys
from mitmproxy.tools.main import mitmdump
sys.argv[0] = "mitmdump"
sys.exit(mitmdump())
        """
        cert_path = Path(__file__).parent.resolve() / "keys"
        self.proc = Popen(
            [
                sys.executable,
                "-u",
                "-c",
                script,
                "--listen-host",
                "127.0.0.1",
                "--listen-port",
                "0",
                "--proxyauth",
                f"{self.auth_user}:{self.auth_pass}",
                "--set",
                f"confdir={cert_path}",
                "--ssl-insecure",
            ],
            stdout=PIPE,
        )
        line = self.proc.stdout.readline().decode("utf-8")
        host_port = re.search(r"listening at (?:http://)?([^:]+:\d+)", line).group(1)
        address = f"http://{self.auth_user}:{self.auth_pass}@{host_port}"
        return address

    def stop(self):
        self.proc.kill()
        self.proc.communicate()


def _wrong_credentials(proxy_url):
    bad_auth_proxy = list(urlsplit(proxy_url))
    bad_auth_proxy[1] = bad_auth_proxy[1].replace("scrapy:scrapy@", "wrong:wronger@")
    return urlunsplit(bad_auth_proxy)


class ProxyConnectTestCase(TestCase):
    def setUp(self):
        try:
            import mitmproxy  # noqa: F401
        except ImportError:
            self.skipTest("mitmproxy is not installed")

        self.mockserver = MockServer()
        self.mockserver.__enter__()
        self._oldenv = os.environ.copy()

        self._proxy = MitmProxy()
        proxy_url = self._proxy.start()
        os.environ["https_proxy"] = proxy_url
        os.environ["http_proxy"] = proxy_url

    def tearDown(self):
        self.mockserver.__exit__(None, None, None)
        self._proxy.stop()
        os.environ = self._oldenv

    @defer.inlineCallbacks
    def test_https_connect_tunnel(self):
        crawler = get_crawler(SimpleSpider)
        with LogCapture() as log:
            yield crawler.crawl(self.mockserver.url("/status?n=200", is_secure=True))
        self._assert_got_response_code(200, log)

    @defer.inlineCallbacks
    def test_https_tunnel_auth_error(self):
        os.environ["https_proxy"] = _wrong_credentials(os.environ["https_proxy"])
        crawler = get_crawler(SimpleSpider)
        with LogCapture() as log:
            yield crawler.crawl(self.mockserver.url("/status?n=200", is_secure=True))
        # The proxy returns a 407 error code but it does not reach the client;
        # he just sees a TunnelError.
        self._assert_got_tunnel_error(log)

    @defer.inlineCallbacks
    def test_https_tunnel_without_leak_proxy_authorization_header(self):
        request = Request(self.mockserver.url("/echo", is_secure=True))
        crawler = get_crawler(SingleRequestSpider)
        with LogCapture() as log:
            yield crawler.crawl(seed=request)
        self._assert_got_response_code(200, log)
        echo = json.loads(crawler.spider.meta["responses"][0].text)
        self.assertTrue("Proxy-Authorization" not in echo["headers"])

    def _assert_got_response_code(self, code, log):
        print(log)
        self.assertEqual(str(log).count(f"Crawled ({code})"), 1)

    def _assert_got_tunnel_error(self, log):
        print(log)
        self.assertIn("TunnelError", str(log))
