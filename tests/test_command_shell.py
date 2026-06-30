from __future__ import annotations

import importlib.util
import os
import signal
import sys
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pexpect.popen_spawn import PopenSpawn

from scrapy import Spider
from scrapy.http import Request, Response
from scrapy.shell import Shell, inspect_response
from scrapy.utils.reactor import _asyncio_reactor_path
from scrapy.utils.test import get_crawler
from tests import NON_EXISTING_RESOLVABLE, tests_datadir
from tests.utils.cmdline import proc
from tests.utils.decorators import coroutine_test

if TYPE_CHECKING:
    from scrapy.crawler import Crawler
    from tests.mockserver.http import MockServer


class TestShellCommand:
    def test_empty(self) -> None:
        _, out, _ = proc("shell", "-c", "item")
        assert "{}" in out

    def test_empty_no_reactor(self) -> None:
        _, out, _ = proc(
            "shell", "-c", "item", "--set", "TWISTED_REACTOR_ENABLED=False"
        )
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
        assert "CannotResolveHostError" in err

    def test_shell_fetch_async(self, mockserver: MockServer) -> None:
        url = mockserver.url("/html")
        code = f"fetch('{url}')"
        ret, _, err = proc(
            "shell", "-c", code, "--set", f"TWISTED_REACTOR={_asyncio_reactor_path}"
        )
        assert ret == 0, err
        assert "RuntimeError: There is no current event loop in thread" not in err

    def test_shell_fetch_no_reactor(self, mockserver: MockServer) -> None:
        url = mockserver.url("/html")
        code = f"fetch('{url}')"
        ret, _, err = proc(
            "shell", "-c", code, "--set", "TWISTED_REACTOR_ENABLED=False"
        )
        assert ret == 0, err

    def test_shelp(self) -> None:
        ret, out, _ = proc("shell", "-c", "shelp()")
        assert ret == 0, out
        assert "Available Scrapy objects" in out

    def test_fetch_request_with_callbacks(self, mockserver: MockServer) -> None:
        url = mockserver.url("/text")
        code = (
            f"fetch(scrapy.Request('{url}', callback=lambda r: r, errback=lambda f: f))"
        )
        ret, out, _ = proc("shell", "-c", code)
        assert ret == 0, out


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
        p = PopenSpawn(args, env=env, timeout=5)
        p.logfile_read = logfile
        p.expect_exact("Available Scrapy objects")
        p.sendline(f"fetch('{mockserver.url('/')}')")
        p.sendline("type(response)")
        p.expect_exact("HtmlResponse")
        p.sendeof()
        p.wait()  # type: ignore[no-untyped-call]
        if p.proc.stdin:
            p.proc.stdin.close()
        if p.proc.stdout:
            p.proc.stdout.close()
        logfile.seek(0)
        assert "Traceback" not in logfile.read().decode()

    @staticmethod
    def _isolate_config(env: dict[str, str], config_home: Path) -> None:
        """Point every scrapy.cfg location (see
        :func:`scrapy.utils.conf.get_sources`) at ``config_home``.

        ``XDG_CONFIG_HOME`` is read by Scrapy on all platforms, while
        ``~/.scrapy.cfg`` goes through :func:`os.path.expanduser`, which uses
        ``HOME`` on POSIX and ``USERPROFILE`` on Windows. The working directory
        stays at the repository root (no scrapy.cfg) so subprocess coverage data
        is still collected there.
        """
        env.pop("SCRAPY_PYTHON_SHELL", None)
        env["HOME"] = str(config_home)
        env["USERPROFILE"] = str(config_home)
        env["XDG_CONFIG_HOME"] = str(config_home)

    def _run_interactive_shell(self, env: dict[str, str]) -> str:
        args = (sys.executable, "-m", "scrapy.cmdline", "shell")
        logfile = BytesIO()
        p = PopenSpawn(args, env=env, timeout=5)
        p.logfile_read = logfile
        p.expect_exact("Available Scrapy objects")
        p.sendeof()
        p.wait()  # type: ignore[no-untyped-call]
        if p.proc.stdin:
            p.proc.stdin.close()
        if p.proc.stdout:
            p.proc.stdout.close()
        logfile.seek(0)
        return logfile.read().decode()

    @pytest.mark.skipif(
        importlib.util.find_spec("IPython") is None,
        reason="Without IPython installed, shell=python and the default both "
        "select the standard Python shell, so the setting has no observable effect.",
    )
    def test_shell_from_cfg(self, tmp_path: Path) -> None:
        config_home = tmp_path / "config"
        config_home.mkdir()
        (config_home / "scrapy.cfg").write_text("[settings]\nshell = python\n")
        env = os.environ.copy()
        self._isolate_config(env, config_home)
        args = (sys.executable, "-m", "scrapy.cmdline", "shell")
        logfile = BytesIO()
        p = PopenSpawn(args, env=env, timeout=10)
        p.logfile_read = logfile
        p.expect_exact("Available Scrapy objects")
        # The standard Python shell never imports IPython, whereas the IPython
        # shell (the default when installed) does; this confirms the configured
        # shell=python was honored, regardless of platform-specific prompts.
        p.sendline("import sys; print('IPYMODULE', 'IPython' in sys.modules)")
        p.expect_exact("IPYMODULE False")
        p.sendeof()
        p.wait()  # type: ignore[no-untyped-call]
        if p.proc.stdin:
            p.proc.stdin.close()
        if p.proc.stdout:
            p.proc.stdout.close()
        logfile.seek(0)
        assert "Traceback" not in logfile.read().decode()

    def test_shell_default_shells(self, tmp_path: Path) -> None:
        config_home = tmp_path / "config"
        config_home.mkdir()
        env = os.environ.copy()
        self._isolate_config(env, config_home)
        assert "Traceback" not in self._run_interactive_shell(env)


@pytest.fixture
def restore_sigint():
    """Shell.start() installs SIG_IGN as the SIGINT handler; restore it."""
    handler = signal.getsignal(signal.SIGINT)
    try:
        yield
    finally:
        signal.signal(signal.SIGINT, handler)


def _no_reactor_crawler(monkeypatch: pytest.MonkeyPatch) -> Crawler:
    """Return a crawler that reports ``TWISTED_REACTOR_ENABLED=False``.

    A genuine no-reactor crawler cannot be built while a Twisted reactor is
    installed (as it is during the test run), so we build a normal crawler and
    make its settings report the reactor as disabled, which is all the shell
    code looks at.
    """
    crawler = get_crawler()
    real_getbool = crawler.settings.getbool

    def fake_getbool(name: str, *args: Any, **kwargs: Any) -> bool:
        if name == "TWISTED_REACTOR_ENABLED":
            return False
        return real_getbool(name, *args, **kwargs)

    monkeypatch.setattr(crawler.settings, "getbool", fake_getbool)
    return crawler


@pytest.mark.requires_reactor
class TestShell:
    """Tests for :class:`~scrapy.shell.Shell` paths with no ``scrapy shell``
    command-line route: those reached through
    :func:`scrapy.shell.inspect_response` (called from spider callbacks) or only
    through direct API use, hence not covered by the subprocess tests above.
    """

    def test_populate_vars_fetch_not_available(self) -> None:
        shell = Shell(get_crawler())
        shell._inthread = False
        shell.populate_vars()
        assert "fetch" not in shell.vars

    def test_get_help_fetch_not_available(self) -> None:
        shell = Shell(get_crawler())
        shell._inthread = False
        shell.populate_vars()
        help_text = shell.get_help()
        assert "fetch(url" not in help_text
        assert "shelp()" in help_text

    def test_start_with_request(self, restore_sigint: None) -> None:
        shell = Shell(get_crawler(), code="1")
        shell.fetch = MagicMock()  # type: ignore[method-assign]
        request = Request("data:,")
        shell.start(request=request)
        shell.fetch.assert_called_once_with(request, None)

    def test_start_with_response(
        self, restore_sigint: None, capsys: pytest.CaptureFixture[str]
    ) -> None:
        shell = Shell(get_crawler(), code="response.url")
        request = Request("data:,")
        response = Response("data:,", request=request)
        shell.start(response=response)
        assert "data:," in capsys.readouterr().out
        assert shell.vars["response"] is response
        assert shell.vars["request"] is request

    @patch("scrapy.shell.start_python_console")
    def test_inspect_response(
        self, mock_console: MagicMock, restore_sigint: None
    ) -> None:
        crawler = get_crawler()
        spider = crawler._create_spider()
        response = Response("data:,", request=Request("data:,"))
        sigint_handler = signal.getsignal(signal.SIGINT)
        inspect_response(response, spider)
        mock_console.assert_called_once()
        assert signal.getsignal(signal.SIGINT) is sigint_handler

    @coroutine_test
    async def test_open_spider_explicit_spider(self) -> None:
        crawler = get_crawler()
        crawler.engine = MagicMock()
        crawler.engine.open_spider_async = AsyncMock()
        shell = Shell(crawler)
        spider = Spider("test")
        await shell._open_spider(spider)
        assert shell.spider is spider
        assert crawler.spider is spider
        crawler.engine.open_spider_async.assert_called_once_with(close_if_idle=False)


@pytest.mark.only_asyncio
class TestShellNoReactor:
    @coroutine_test
    @patch("scrapy.shell.start_python_console")
    async def test_inspect_response_no_reactor(
        self,
        mock_console: MagicMock,
        restore_sigint: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        crawler = _no_reactor_crawler(monkeypatch)
        spider = crawler._create_spider()
        response = Response("data:,", request=Request("data:,"))
        inspect_response(response, spider)
        mock_console.assert_called_once()
