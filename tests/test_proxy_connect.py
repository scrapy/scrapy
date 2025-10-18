import json
import os
import re
import sys
from pathlib import Path
from subprocess import PIPE, Popen
from urllib.parse import urlsplit, urlunsplit

import pytest
from testfixtures import LogCapture
from twisted.internet.defer import inlineCallbacks

from scrapy.http import Request
from scrapy.utils.test import get_crawler
from tests.mockserver.http import MockServer
from tests.spiders import SimpleSpider, SingleRequestSpider


class MitmProxy:
    auth_user = "scrapy"
    auth_pass = "scrapy"

    def start(self, listen_host: str = "127.0.0.1"):
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
                listen_host,
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
        host_port = re.search(
            r"listening at (?:https?:\/\/)?([^\s.]+(?:\.\S+)*?:\d+)", line
        ).group(1)
        return f"http://{self.auth_user}:{self.auth_pass}@{host_port}"

    def stop(self):
        self.proc.kill()
        self.proc.communicate()


def _wrong_credentials(proxy_url):
    bad_auth_proxy = list(urlsplit(proxy_url))
    bad_auth_proxy[1] = bad_auth_proxy[1].replace("scrapy:scrapy@", "wrong:wronger@")
    return urlunsplit(bad_auth_proxy)


class BaseTestProxyConnect:
    @classmethod
    def setup_class(cls):
        cls.mockserver = MockServer()
        cls.mockserver.__enter__()

    @classmethod
    def teardown_class(cls):
        cls.mockserver.__exit__(None, None, None)

    def setup_method(self):
        try:
            import mitmproxy  # noqa: F401,PLC0415
        except ImportError:
            pytest.skip("mitmproxy is not installed")

        self._oldenv = os.environ.copy()
        self._proxy = MitmProxy()
        proxy_url = self._proxy.start(listen_host=self.proxy_host)
        os.environ["https_proxy"] = proxy_url
        os.environ["http_proxy"] = proxy_url

    def teardown_method(self):
        self._proxy.stop()
        os.environ = self._oldenv

    @inlineCallbacks
    def test_https_connect_tunnel(self):
        crawler = get_crawler(SimpleSpider)
        with LogCapture() as log:
            yield crawler.crawl(self.mockserver.url("/status?n=200", is_secure=True))
        self._assert_got_response_code(200, log)

    @inlineCallbacks
    def test_https_tunnel_auth_error(self):
        os.environ["https_proxy"] = _wrong_credentials(os.environ["https_proxy"])
        crawler = get_crawler(SimpleSpider)
        with LogCapture() as log:
            yield crawler.crawl(self.mockserver.url("/status?n=200", is_secure=True))
        self._assert_got_tunnel_error(log)

    @inlineCallbacks
    def test_https_tunnel_without_leak_proxy_authorization_header(self):
        request = Request(self.mockserver.url("/echo", is_secure=True))
        crawler = get_crawler(SingleRequestSpider)
        with LogCapture() as log:
            yield crawler.crawl(seed=request)
        self._assert_got_response_code(200, log)
        echo = json.loads(crawler.spider.meta["responses"][0].text)
        assert "Proxy-Authorization" not in echo["headers"]

    def _assert_got_response_code(self, code, log):
        assert str(log).count(f"Crawled ({code})") == 1

    def _assert_got_tunnel_error(self, log):
        assert "TunnelError" in str(log)


class TestProxyConnect(BaseTestProxyConnect):
    proxy_host = "127.0.0.1"


class TestProxyConnectIPv6(BaseTestProxyConnect):
    proxy_host = "::1"
