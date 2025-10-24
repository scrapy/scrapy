from __future__ import annotations

import os
import sys
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest
from pexpect.popen_spawn import PopenSpawn

from scrapy.utils.reactor import _asyncio_reactor_path
from tests import NON_EXISTING_RESOLVABLE, tests_datadir
from tests.utils.cmdline import proc

if TYPE_CHECKING:
    from tests.mockserver.http import MockServer


class TestShellCommand:
    def test_empty(self) -> None:
        _, out, _ = proc("shell", "-c", "item")
        assert "{}" in out

    def test_response_body(self, mockserver: MockServer) -> None:
        _, out, _ = proc("shell", mockserver.url("/text"), "-c", "response.body")
        assert "Works" in out

    def test_response_type_text(self, mockserver: MockServer) -> None:
        _, out, _ = proc("shell", mockserver.url("/text"), "-c", "type(response)")
        assert "TextResponse" in out

    def test_response_type_html(self, mockserver: MockServer) -> None:
        _, out, _ = proc("shell", mockserver.url("/html"), "-c", "type(response)")
        assert "HtmlResponse" in out

    def test_response_selector_html(self, mockserver: MockServer) -> None:
        xpath = "response.xpath(\"//p[@class='one']/text()\").get()"
        _, out, _ = proc("shell", mockserver.url("/html"), "-c", xpath)
        assert out.strip() == "Works"

    def test_response_encoding_gb18030(self, mockserver: MockServer) -> None:
        _, out, _ = proc(
            "shell", mockserver.url("/enc-gb18030"), "-c", "response.encoding"
        )
        assert out.strip() == "gb18030"

    def test_redirect(self, mockserver: MockServer) -> None:
        _, out, _ = proc("shell", mockserver.url("/redirect"), "-c", "response.url")
        assert out.strip().endswith("/redirected")

    def test_redirect_follow_302(self, mockserver: MockServer) -> None:
        _, out, _ = proc(
            "shell",
            mockserver.url("/redirect-no-meta-refresh"),
            "-c",
            "response.status",
        )
        assert out.strip().endswith("200")

    def test_redirect_not_follow_302(self, mockserver: MockServer) -> None:
        _, out, _ = proc(
            "shell",
            "--no-redirect",
            mockserver.url("/redirect-no-meta-refresh"),
            "-c",
            "response.status",
        )
        assert out.strip().endswith("302")

    def test_fetch_redirect_follow_302(self, mockserver: MockServer) -> None:
        """Test that calling ``fetch(url)`` follows HTTP redirects by default."""
        url = mockserver.url("/redirect-no-meta-refresh")
        code = f"fetch('{url}')"
        ret, out, err = proc("shell", "-c", code)
        assert ret == 0, out
        assert "Redirecting (302)" in err
        assert "Crawled (200)" in err

    def test_fetch_redirect_not_follow_302(self, mockserver: MockServer) -> None:
        """Test that calling ``fetch(url, redirect=False)`` disables automatic redirects."""
        url = mockserver.url("/redirect-no-meta-refresh")
        code = f"fetch('{url}', redirect=False)"
        ret, out, err = proc("shell", "-c", code)
        assert ret == 0, out
        assert "Crawled (302)" in err

    def test_request_replace(self, mockserver: MockServer) -> None:
        url = mockserver.url("/text")
        code = f"fetch('{url}') or fetch(response.request.replace(method='POST'))"
        ret, out, _ = proc("shell", "-c", code)
        assert ret == 0, out

    def test_scrapy_import(self, mockserver: MockServer) -> None:
        url = mockserver.url("/text")
        code = f"fetch(scrapy.Request('{url}'))"
        ret, out, _ = proc("shell", "-c", code)
        assert ret == 0, out

    def test_local_file(self) -> None:
        filepath = Path(tests_datadir, "test_site", "index.html")
        _, out, _ = proc("shell", str(filepath), "-c", "item")
        assert "{}" in out

    def test_local_nofile(self) -> None:
        filepath = "file:///tests/sample_data/test_site/nothinghere.html"
        ret, out, err = proc("shell", filepath, "-c", "item")
        assert ret == 1, out or err
        assert "No such file or directory" in err

    def test_dns_failures(self, mockserver: MockServer) -> None:
        if NON_EXISTING_RESOLVABLE:
            pytest.skip("Non-existing hosts are resolvable")
        url = "www.somedomainthatdoesntexi.st"
        ret, out, err = proc("shell", url, "-c", "item")
        assert ret == 1, out or err
        assert "DNS lookup failed" in err

    def test_shell_fetch_async(self, mockserver: MockServer) -> None:
        url = mockserver.url("/html")
        code = f"fetch('{url}')"
        ret, _, err = proc(
            "shell", "-c", code, "--set", f"TWISTED_REACTOR={_asyncio_reactor_path}"
        )
        assert ret == 0, err
        assert "RuntimeError: There is no current event loop in thread" not in err


class TestInteractiveShell:
    def test_fetch(self, mockserver: MockServer) -> None:
        args = (
            sys.executable,
            "-m",
            "scrapy.cmdline",
            "shell",
        )
        env = os.environ.copy()
        env["SCRAPY_PYTHON_SHELL"] = "python"
        logfile = BytesIO()
        # https://github.com/python/typeshed/issues/14915
        p = PopenSpawn(args, env=cast("os._Environ", env), timeout=5)
        p.logfile_read = logfile
        p.expect_exact("Available Scrapy objects")
        p.sendline(f"fetch('{mockserver.url('/')}')")
        p.sendline("type(response)")
        p.expect_exact("HtmlResponse")
        p.sendeof()
        p.wait()
        logfile.seek(0)
        assert "Traceback" not in logfile.read().decode()
