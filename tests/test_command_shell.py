import os
import sys
from io import BytesIO
from pathlib import Path

import pytest
from pexpect.popen_spawn import PopenSpawn

from scrapy.utils.reactor import _asyncio_reactor_path
from tests import NON_EXISTING_RESOLVABLE, tests_datadir
from tests.mockserver import MockServer
from tests.test_commands import TestProjectBase


class TestShellCommand(TestProjectBase):
    @classmethod
    def setup_class(cls):
        cls.mockserver = MockServer()
        cls.mockserver.__enter__()

    @classmethod
    def teardown_class(cls):
        cls.mockserver.__exit__(None, None, None)

    def test_empty(self):
        _, out, _ = self.proc("shell", "-c", "item")
        assert "{}" in out

    def test_response_body(self):
        _, out, _ = self.proc(
            "shell", self.mockserver.url("/text"), "-c", "response.body"
        )
        assert "Works" in out

    def test_response_type_text(self):
        _, out, _ = self.proc(
            "shell", self.mockserver.url("/text"), "-c", "type(response)"
        )
        assert "TextResponse" in out

    def test_response_type_html(self):
        _, out, _ = self.proc(
            "shell", self.mockserver.url("/html"), "-c", "type(response)"
        )
        assert "HtmlResponse" in out

    def test_response_selector_html(self):
        xpath = "response.xpath(\"//p[@class='one']/text()\").get()"
        _, out, _ = self.proc("shell", self.mockserver.url("/html"), "-c", xpath)
        assert out.strip() == "Works"

    def test_response_encoding_gb18030(self):
        _, out, _ = self.proc(
            "shell", self.mockserver.url("/enc-gb18030"), "-c", "response.encoding"
        )
        assert out.strip() == "gb18030"

    def test_redirect(self):
        _, out, _ = self.proc(
            "shell", self.mockserver.url("/redirect"), "-c", "response.url"
        )
        assert out.strip().endswith("/redirected")

    def test_redirect_follow_302(self):
        _, out, _ = self.proc(
            "shell",
            self.mockserver.url("/redirect-no-meta-refresh"),
            "-c",
            "response.status",
        )
        assert out.strip().endswith("200")

    def test_redirect_not_follow_302(self):
        _, out, _ = self.proc(
            "shell",
            "--no-redirect",
            self.mockserver.url("/redirect-no-meta-refresh"),
            "-c",
            "response.status",
        )
        assert out.strip().endswith("302")

    def test_fetch_redirect_follow_302(self):
        """Test that calling ``fetch(url)`` follows HTTP redirects by default."""
        url = self.mockserver.url("/redirect-no-meta-refresh")
        code = f"fetch('{url}')"
        p, out, errout = self.proc("shell", "-c", code)
        assert p.returncode == 0, out
        assert "Redirecting (302)" in errout
        assert "Crawled (200)" in errout

    def test_fetch_redirect_not_follow_302(self):
        """Test that calling ``fetch(url, redirect=False)`` disables automatic redirects."""
        url = self.mockserver.url("/redirect-no-meta-refresh")
        code = f"fetch('{url}', redirect=False)"
        p, out, errout = self.proc("shell", "-c", code)
        assert p.returncode == 0, out
        assert "Crawled (302)" in errout

    def test_request_replace(self):
        url = self.mockserver.url("/text")
        code = f"fetch('{url}') or fetch(response.request.replace(method='POST'))"
        p, out, _ = self.proc("shell", "-c", code)
        assert p.returncode == 0, out

    def test_scrapy_import(self):
        url = self.mockserver.url("/text")
        code = f"fetch(scrapy.Request('{url}'))"
        p, out, _ = self.proc("shell", "-c", code)
        assert p.returncode == 0, out

    def test_local_file(self):
        filepath = Path(tests_datadir, "test_site", "index.html")
        _, out, _ = self.proc("shell", str(filepath), "-c", "item")
        assert "{}" in out

    def test_local_nofile(self):
        filepath = "file:///tests/sample_data/test_site/nothinghere.html"
        p, out, err = self.proc("shell", filepath, "-c", "item")
        assert p.returncode == 1, out or err
        assert "No such file or directory" in err

    def test_dns_failures(self):
        if NON_EXISTING_RESOLVABLE:
            pytest.skip("Non-existing hosts are resolvable")
        url = "www.somedomainthatdoesntexi.st"
        p, out, err = self.proc("shell", url, "-c", "item")
        assert p.returncode == 1, out or err
        assert "DNS lookup failed" in err

    def test_shell_fetch_async(self):
        url = self.mockserver.url("/html")
        code = f"fetch('{url}')"
        p, _, err = self.proc(
            "shell", "-c", code, "--set", f"TWISTED_REACTOR={_asyncio_reactor_path}"
        )
        assert p.returncode == 0, err
        assert "RuntimeError: There is no current event loop in thread" not in err


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
