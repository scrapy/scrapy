import os
import sys
from io import BytesIO
from pathlib import Path

from pexpect.popen_spawn import PopenSpawn
from twisted.internet import defer
from twisted.trial import unittest

from tests import NON_EXISTING_RESOLVABLE, tests_datadir
from tests.mockserver import MockServer
from tests.utils.testproc import ProcessTest
from tests.utils.testsite import SiteTest


class TestShellCommand(ProcessTest, SiteTest, unittest.TestCase):
    command = "shell"

    @defer.inlineCallbacks
    def test_empty(self):
        _, out, _ = yield self.execute(["-c", "item"])
        assert b"{}" in out

    @defer.inlineCallbacks
    def test_response_body(self):
        _, out, _ = yield self.execute([self.url("/text"), "-c", "response.body"])
        assert b"Works" in out

    @defer.inlineCallbacks
    def test_response_type_text(self):
        _, out, _ = yield self.execute([self.url("/text"), "-c", "type(response)"])
        assert b"TextResponse" in out

    @defer.inlineCallbacks
    def test_response_type_html(self):
        _, out, _ = yield self.execute([self.url("/html"), "-c", "type(response)"])
        assert b"HtmlResponse" in out

    @defer.inlineCallbacks
    def test_response_selector_html(self):
        xpath = "response.xpath(\"//p[@class='one']/text()\").get()"
        _, out, _ = yield self.execute([self.url("/html"), "-c", xpath])
        assert out.strip() == b"Works"

    @defer.inlineCallbacks
    def test_response_encoding_gb18030(self):
        _, out, _ = yield self.execute(
            [self.url("/enc-gb18030"), "-c", "response.encoding"]
        )
        assert out.strip() == b"gb18030"

    @defer.inlineCallbacks
    def test_redirect(self):
        _, out, _ = yield self.execute([self.url("/redirect"), "-c", "response.url"])
        assert out.strip().endswith(b"/redirected")

    @defer.inlineCallbacks
    def test_redirect_follow_302(self):
        _, out, _ = yield self.execute(
            [self.url("/redirect-no-meta-refresh"), "-c", "response.status"]
        )
        assert out.strip().endswith(b"200")

    @defer.inlineCallbacks
    def test_redirect_not_follow_302(self):
        _, out, _ = yield self.execute(
            [
                "--no-redirect",
                self.url("/redirect-no-meta-refresh"),
                "-c",
                "response.status",
            ]
        )
        assert out.strip().endswith(b"302")

    @defer.inlineCallbacks
    def test_fetch_redirect_follow_302(self):
        """Test that calling ``fetch(url)`` follows HTTP redirects by default."""
        url = self.url("/redirect-no-meta-refresh")
        code = f"fetch('{url}')"
        errcode, out, errout = yield self.execute(["-c", code])
        assert errcode == 0, out
        assert b"Redirecting (302)" in errout
        assert b"Crawled (200)" in errout

    @defer.inlineCallbacks
    def test_fetch_redirect_not_follow_302(self):
        """Test that calling ``fetch(url, redirect=False)`` disables automatic redirects."""
        url = self.url("/redirect-no-meta-refresh")
        code = f"fetch('{url}', redirect=False)"
        errcode, out, errout = yield self.execute(["-c", code])
        assert errcode == 0, out
        assert b"Crawled (302)" in errout

    @defer.inlineCallbacks
    def test_request_replace(self):
        url = self.url("/text")
        code = f"fetch('{url}') or fetch(response.request.replace(method='POST'))"
        errcode, out, _ = yield self.execute(["-c", code])
        assert errcode == 0, out

    @defer.inlineCallbacks
    def test_scrapy_import(self):
        url = self.url("/text")
        code = f"fetch(scrapy.Request('{url}'))"
        errcode, out, _ = yield self.execute(["-c", code])
        assert errcode == 0, out

    @defer.inlineCallbacks
    def test_local_file(self):
        filepath = Path(tests_datadir, "test_site", "index.html")
        _, out, _ = yield self.execute([str(filepath), "-c", "item"])
        assert b"{}" in out

    @defer.inlineCallbacks
    def test_local_nofile(self):
        filepath = "file:///tests/sample_data/test_site/nothinghere.html"
        errcode, out, err = yield self.execute(
            [filepath, "-c", "item"], check_code=False
        )
        assert errcode == 1, out or err
        assert b"No such file or directory" in err

    @defer.inlineCallbacks
    def test_dns_failures(self):
        if NON_EXISTING_RESOLVABLE:
            raise unittest.SkipTest("Non-existing hosts are resolvable")
        url = "www.somedomainthatdoesntexi.st"
        errcode, out, err = yield self.execute([url, "-c", "item"], check_code=False)
        assert errcode == 1, out or err
        assert b"DNS lookup failed" in err

    @defer.inlineCallbacks
    def test_shell_fetch_async(self):
        reactor_path = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
        url = self.url("/html")
        code = f"fetch('{url}')"
        args = ["-c", code, "--set", f"TWISTED_REACTOR={reactor_path}"]
        _, _, err = yield self.execute(args, check_code=True)
        assert b"RuntimeError: There is no current event loop in thread" not in err


class TestInteractiveShell:
    def test_fetch(self):
        args = (
            sys.executable,
            "-m",
            "scrapy.cmdline",
            "shell",
        )
        env = os.environ.copy()
        env["SCRAPY_PYTHON_SHELL"] = "python"
        logfile = BytesIO()
        p = PopenSpawn(args, env=env, timeout=5)
        p.logfile_read = logfile
        p.expect_exact("Available Scrapy objects")
        with MockServer() as mockserver:
            p.sendline(f"fetch('{mockserver.url('/')}')")
            p.sendline("type(response)")
            p.expect_exact("HtmlResponse")
        p.sendeof()
        p.wait()
        logfile.seek(0)
        assert "Traceback" not in logfile.read().decode()
