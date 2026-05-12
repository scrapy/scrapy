from __future__ import annotations

import platform
import re
import signal
import subprocess
import sys
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from packaging.version import parse as parse_version
from pexpect.popen_spawn import PopenSpawn
from w3lib import __version__ as w3lib_version

from tests.utils import async_sleep, get_script_run_env
from tests.utils.decorators import coroutine_test

if TYPE_CHECKING:
    from tests.mockserver.http import MockServer


class ScriptRunnerMixin(ABC):
    @property
    @abstractmethod
    def script_dir(self) -> Path:
        raise NotImplementedError

    @staticmethod
    def get_script_dir(name: str) -> Path:
        return Path(__file__).parent.resolve() / name

    def get_script_args(self, script_name: str, *script_args: str) -> list[str]:
        script_path = self.script_dir / script_name
        return [sys.executable, str(script_path), *script_args]

    def run_script(self, script_name: str, *script_args: str) -> str:
        args = self.get_script_args(script_name, *script_args)
        p = subprocess.Popen(
            args,
            env=get_script_run_env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        _, stderr = p.communicate()
        return stderr.decode("utf-8")


class TestCrawlerProcessSubprocessBase(ScriptRunnerMixin):
    """Common tests between CrawlerProcess and AsyncCrawlerProcess,
    with the same file names and expectations.
    """

    def test_simple(self):
        log = self.run_script("simple.py")
        assert "Spider closed (finished)" in log
        assert (
            "Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor"
            in log
        )
        assert "is_reactorless(): False" in log

    def test_multi(self):
        log = self.run_script("multi.py")
        assert "Spider closed (finished)" in log
        assert (
            "Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor"
            in log
        )
        assert "ReactorAlreadyInstalledError" not in log

    def test_reactor_default(self):
        log = self.run_script("reactor_default.py")
        assert "Spider closed (finished)" not in log
        assert (
            "does not match the requested one "
            "(twisted.internet.asyncioreactor.AsyncioSelectorReactor)"
        ) in log

    def test_asyncio_enabled_no_reactor(self):
        log = self.run_script("asyncio_enabled_no_reactor.py")
        assert "Spider closed (finished)" in log
        assert (
            "Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor"
            in log
        )
        assert "RuntimeError" not in log

    def test_asyncio_enabled_reactor(self):
        log = self.run_script("asyncio_enabled_reactor.py")
        assert "Spider closed (finished)" in log
        assert (
            "Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor"
            in log
        )
        assert "RuntimeError" not in log

    @pytest.mark.skipif(
        parse_version(w3lib_version) >= parse_version("2.0.0"),
        reason="w3lib 2.0.0 and later do not allow invalid domains.",
    )
    def test_ipv6_default_name_resolver(self):
        log = self.run_script("default_name_resolver.py")
        assert "Spider closed (finished)" in log
        assert (
            "'downloader/exception_type_count/scrapy.exceptions.CannotResolveHostError': 1,"
            in log
        )
        assert (
            "scrapy.exceptions.CannotResolveHostError: DNS lookup failed: no results for hostname lookup: ::1."
            in log
        )

    def test_caching_hostname_resolver_ipv6(self):
        log = self.run_script("caching_hostname_resolver_ipv6.py")
        assert "Spider closed (finished)" in log
        assert "scrapy.exceptions.CannotResolveHostError" not in log

    def test_caching_hostname_resolver_finite_execution(
        self, mockserver: MockServer
    ) -> None:
        log = self.run_script("caching_hostname_resolver.py", mockserver.url("/"))
        assert "Spider closed (finished)" in log
        assert "ERROR: Error downloading" not in log
        assert "TimeoutError" not in log
        assert "scrapy.exceptions.CannotResolveHostError" not in log

    def test_twisted_reactor_asyncio(self):
        log = self.run_script("twisted_reactor_asyncio.py")
        assert "Spider closed (finished)" in log
        assert (
            "Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor"
            in log
        )

    def test_twisted_reactor_asyncio_custom_settings(self):
        log = self.run_script("twisted_reactor_custom_settings.py")
        assert "Spider closed (finished)" in log
        assert (
            "Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor"
            in log
        )

    def test_twisted_reactor_asyncio_custom_settings_same(self):
        log = self.run_script("twisted_reactor_custom_settings_same.py")
        assert "Spider closed (finished)" in log
        assert (
            "Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor"
            in log
        )

    @pytest.mark.requires_uvloop
    def test_custom_loop_asyncio(self):
        log = self.run_script("asyncio_custom_loop.py")
        assert "Spider closed (finished)" in log
        assert (
            "Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor"
            in log
        )
        assert "Using asyncio event loop: uvloop.Loop" in log

    @pytest.mark.requires_uvloop
    def test_custom_loop_asyncio_deferred_signal(self):
        log = self.run_script("asyncio_deferred_signal.py", "uvloop.Loop")
        assert "Spider closed (finished)" in log
        assert (
            "Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor"
            in log
        )
        assert "Using asyncio event loop: uvloop.Loop" in log
        assert "async pipeline opened!" in log

    @pytest.mark.requires_uvloop
    def test_asyncio_enabled_reactor_same_loop(self):
        log = self.run_script("asyncio_enabled_reactor_same_loop.py")
        assert "Spider closed (finished)" in log
        assert (
            "Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor"
            in log
        )
        assert "Using asyncio event loop: uvloop.Loop" in log

    @pytest.mark.requires_uvloop
    def test_asyncio_enabled_reactor_different_loop(self):
        log = self.run_script("asyncio_enabled_reactor_different_loop.py")
        assert "Spider closed (finished)" not in log
        assert (
            "does not match the one specified in the ASYNCIO_EVENT_LOOP "
            "setting (uvloop.Loop)"
        ) in log

    def test_default_loop_asyncio_deferred_signal(self):
        log = self.run_script("asyncio_deferred_signal.py")
        assert "Spider closed (finished)" in log
        assert (
            "Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor"
            in log
        )
        assert "Using asyncio event loop: uvloop.Loop" not in log
        assert "async pipeline opened!" in log

    def test_args_change_settings(self):
        log = self.run_script("args_settings.py")
        assert "Spider closed (finished)" in log
        assert "The value of FOO is 42" in log

    def _test_shutdown_graceful(self, script: str = "sleeping.py") -> None:
        sig = signal.SIGINT if sys.platform != "win32" else signal.SIGBREAK  # type: ignore[attr-defined]
        args = self.get_script_args(script, "3")
        p = PopenSpawn(args, timeout=5, env=get_script_run_env())
        p.expect_exact("Spider opened")
        p.expect_exact("Crawled (200)")
        p.kill(sig)
        p.expect_exact("shutting down gracefully")
        p.expect_exact("Spider closed (shutdown)")
        p.wait()  # type: ignore[no-untyped-call]

    def test_shutdown_graceful(self) -> None:
        self._test_shutdown_graceful()

    async def _test_shutdown_forced(self, script: str = "sleeping.py") -> None:
        sig = signal.SIGINT if sys.platform != "win32" else signal.SIGBREAK  # type: ignore[attr-defined]
        args = self.get_script_args(script, "10")
        p = PopenSpawn(args, timeout=5, env=get_script_run_env())
        p.expect_exact("Spider opened")
        p.expect_exact("Crawled (200)")
        p.kill(sig)
        p.expect_exact("shutting down gracefully")
        # sending the second signal too fast often causes problems
        await async_sleep(0.01)
        p.kill(sig)
        p.expect_exact("forcing unclean shutdown")
        p.wait()  # type: ignore[no-untyped-call]

    @coroutine_test
    async def test_shutdown_forced(self) -> None:
        await self._test_shutdown_forced()


class TestCrawlerProcessSubprocess(TestCrawlerProcessSubprocessBase):
    @property
    def script_dir(self) -> Path:
        return self.get_script_dir("CrawlerProcess")

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
            assert "Spider closed (finished)" in log
        else:
            assert "Spider closed (finished)" not in log
            assert (
                "does not match the requested one "
                "(twisted.internet.selectreactor.SelectReactor)"
            ) in log

    def test_reactor_select(self):
        log = self.run_script("reactor_select.py")
        assert "Spider closed (finished)" not in log
        assert (
            "does not match the requested one "
            "(twisted.internet.asyncioreactor.AsyncioSelectorReactor)"
        ) in log

    def test_reactor_select_twisted_reactor_select(self):
        log = self.run_script("reactor_select_twisted_reactor_select.py")
        assert "Spider closed (finished)" in log
        assert "ReactorAlreadyInstalledError" not in log

    def test_reactor_select_subclass_twisted_reactor_select(self):
        log = self.run_script("reactor_select_subclass_twisted_reactor_select.py")
        assert "Spider closed (finished)" not in log
        assert (
            "does not match the requested one "
            "(twisted.internet.selectreactor.SelectReactor)"
        ) in log

    def test_twisted_reactor_select(self):
        log = self.run_script("twisted_reactor_select.py")
        assert "Spider closed (finished)" in log
        assert "Using reactor: twisted.internet.selectreactor.SelectReactor" in log

    @pytest.mark.skipif(
        platform.system() == "Windows", reason="PollReactor is not supported on Windows"
    )
    def test_twisted_reactor_poll(self):
        log = self.run_script("twisted_reactor_poll.py")
        assert "Spider closed (finished)" in log
        assert "Using reactor: twisted.internet.pollreactor.PollReactor" in log

    def test_twisted_reactor_asyncio_custom_settings_conflict(self):
        log = self.run_script("twisted_reactor_custom_settings_conflict.py")
        assert "Using reactor: twisted.internet.selectreactor.SelectReactor" in log
        assert (
            "(twisted.internet.selectreactor.SelectReactor) does not match the requested one"
            in log
        )

    def test_reactorless(self):
        log = self.run_script("reactorless.py")
        assert (
            "RuntimeError: CrawlerProcess doesn't support TWISTED_REACTOR_ENABLED=False"
            in log
        )


class TestAsyncCrawlerProcessSubprocess(TestCrawlerProcessSubprocessBase):
    @property
    def script_dir(self) -> Path:
        return self.get_script_dir("AsyncCrawlerProcess")

    def test_twisted_reactor_custom_settings_select(self):
        log = self.run_script("twisted_reactor_custom_settings_select.py")
        assert "Spider closed (finished)" not in log
        assert (
            "(twisted.internet.asyncioreactor.AsyncioSelectorReactor) "
            "does not match the requested one "
            "(twisted.internet.selectreactor.SelectReactor)"
        ) in log

    @pytest.mark.requires_uvloop
    def test_asyncio_enabled_reactor_same_loop(self):
        log = self.run_script("asyncio_custom_loop_custom_settings_same.py")
        assert "Spider closed (finished)" in log
        assert (
            "Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor"
            in log
        )
        assert "Using asyncio event loop: uvloop.Loop" in log

    @pytest.mark.requires_uvloop
    def test_asyncio_enabled_reactor_different_loop(self):
        log = self.run_script("asyncio_custom_loop_custom_settings_different.py")
        assert "Spider closed (finished)" not in log
        assert (
            "does not match the one specified in the ASYNCIO_EVENT_LOOP "
            "setting (uvloop.Loop)"
        ) in log

    def test_reactorless_simple(self):
        log = self.run_script("reactorless_simple.py")
        assert "Not using a Twisted reactor" in log
        assert "Spider closed (finished)" in log
        assert "is_reactorless(): True" in log
        assert "ERROR: " not in log
        assert log.count("WARNING: HttpxDownloadHandler is experimental") == 2
        assert log.count("WARNING: ") == 2

    def test_reactorless_custom_settings(self):
        """Setting TWISTED_REACTOR_ENABLED=False in spider settings is not
        currently supported, AsyncCrawlerProcess will install a reactor in this
        case.
        """
        log = self.run_script("reactorless_custom_settings.py")
        assert "Spider closed (finished)" not in log
        assert (
            "TWISTED_REACTOR_ENABLED is False but a Twisted reactor is installed."
            in log
        )

    def test_reactorless_datauri(self):
        log = self.run_script("reactorless_datauri.py")
        assert "Not using a Twisted reactor" in log
        assert "Spider closed (finished)" in log
        assert "{'data': 'foo'}" in log
        assert "'item_scraped_count': 1" in log
        assert "ERROR: " not in log
        assert log.count("WARNING: HttpxDownloadHandler is experimental") == 2
        assert log.count("WARNING: ") == 2

    def test_reactorless_import_hook(self):
        log = self.run_script("reactorless_import_hook.py")
        assert "Not using a Twisted reactor" in log
        assert "Spider closed (finished)" in log
        assert "ImportError: Import of twisted.internet.reactor is forbidden" in log

    def test_reactorless_telnetconsole_default(self):
        """By default TWISTED_REACTOR_ENABLED=False silently sets TELNETCONSOLE_ENABLED=False."""
        log = self.run_script("reactorless_simple.py")  # no need for a separate script
        assert "Not using a Twisted reactor" in log
        assert "Spider closed (finished)" in log
        assert "The TelnetConsole extension requires a Twisted reactor" not in log
        assert "scrapy.extensions.telnet.TelnetConsole" not in log

    def test_reactorless_telnetconsole_disabled(self):
        """Explicit TELNETCONSOLE_ENABLED=False, there are no warnings."""
        log = self.run_script("reactorless_telnetconsole_disabled.py")
        assert "Not using a Twisted reactor" in log
        assert "Spider closed (finished)" in log
        assert "The TelnetConsole extension requires a Twisted reactor" not in log
        assert "scrapy.extensions.telnet.TelnetConsole" not in log

    def test_reactorless_telnetconsole_enabled(self):
        """Explicit TELNETCONSOLE_ENABLED=True, the user gets a warning."""
        log = self.run_script("reactorless_telnetconsole_enabled.py")
        assert "Not using a Twisted reactor" in log
        assert "Spider closed (finished)" in log
        assert "The TelnetConsole extension requires a Twisted reactor" in log

    def test_reactorless_reactor(self):
        log = self.run_script("reactorless_reactor.py")
        assert (
            "RuntimeError: TWISTED_REACTOR_ENABLED is False but a Twisted reactor is installed"
            in log
        )

    def test_shutdown_graceful(self) -> None:
        self._test_shutdown_graceful("reactorless_sleeping.py")

    @coroutine_test
    async def test_shutdown_forced(self) -> None:
        await self._test_shutdown_forced("reactorless_sleeping.py")


class TestCrawlerRunnerSubprocessBase(ScriptRunnerMixin):
    """Common tests between CrawlerRunner and AsyncCrawlerRunner,
    with the same file names and expectations.
    """

    def test_simple(self):
        log = self.run_script("simple.py")
        assert "Spider closed (finished)" in log
        assert (
            "Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor"
            in log
        )
        assert "is_reactorless(): False" in log

    def test_multi_parallel(self):
        log = self.run_script("multi_parallel.py")
        assert "Spider closed (finished)" in log
        assert (
            "Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor"
            in log
        )
        assert re.search(
            r"Spider opened.+Spider opened.+Closing spider.+Closing spider",
            log,
            re.DOTALL,
        )

    def test_multi_seq(self):
        log = self.run_script("multi_seq.py")
        assert "Spider closed (finished)" in log
        assert (
            "Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor"
            in log
        )
        assert re.search(
            r"Spider opened.+Closing spider.+Spider opened.+Closing spider",
            log,
            re.DOTALL,
        )

    @pytest.mark.requires_uvloop
    def test_custom_loop_same(self):
        log = self.run_script("custom_loop_same.py")
        assert "Spider closed (finished)" in log
        assert (
            "Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor"
            in log
        )
        assert "Using asyncio event loop: uvloop.Loop" in log

    @pytest.mark.requires_uvloop
    def test_custom_loop_different(self):
        log = self.run_script("custom_loop_different.py")
        assert "Spider closed (finished)" not in log
        assert (
            "does not match the one specified in the ASYNCIO_EVENT_LOOP "
            "setting (uvloop.Loop)"
        ) in log

    def test_no_reactor(self):
        log = self.run_script("no_reactor.py")
        assert "Spider closed (finished)" not in log
        assert (
            "RuntimeError: We expected a Twisted reactor to be installed but it isn't."
            in log
        )


class TestCrawlerRunnerSubprocess(TestCrawlerRunnerSubprocessBase):
    @property
    def script_dir(self) -> Path:
        return self.get_script_dir("CrawlerRunner")

    def test_explicit_default_reactor(self):
        log = self.run_script("explicit_default_reactor.py")
        assert "Spider closed (finished)" in log
        assert (
            "Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor"
            not in log
        )

    def test_response_ip_address(self):
        log = self.run_script("ip_address.py")
        assert "INFO: Spider closed (finished)" in log
        assert "INFO: Host: not.a.real.domain" in log
        assert "INFO: Type: <class 'ipaddress.IPv4Address'>" in log
        assert "INFO: IP address: 127.0.0.1" in log

    def test_change_default_reactor(self):
        log = self.run_script("change_reactor.py")
        assert (
            "DEBUG: Using reactor: twisted.internet.asyncioreactor.AsyncioSelectorReactor"
            in log
        )
        assert "DEBUG: Using asyncio event loop" in log

    def test_reactorless(self):
        log = self.run_script("reactorless.py")
        assert (
            "RuntimeError: CrawlerRunner doesn't support TWISTED_REACTOR_ENABLED=False"
            in log
        )


class TestAsyncCrawlerRunnerSubprocess(TestCrawlerRunnerSubprocessBase):
    @property
    def script_dir(self) -> Path:
        return self.get_script_dir("AsyncCrawlerRunner")

    def test_simple_default_reactor(self):
        log = self.run_script("simple_default_reactor.py")
        assert "Spider closed (finished)" not in log
        assert (
            "RuntimeError: When TWISTED_REACTOR_ENABLED is True, "
            "AsyncCrawlerRunner requires that the installed Twisted reactor"
        ) in log

    def test_reactorless_simple(self):
        log = self.run_script("reactorless_simple.py")
        assert "Not using a Twisted reactor" in log
        assert "Spider closed (finished)" in log
        assert "is_reactorless(): True" in log
        assert "ERROR: " not in log
        assert log.count("WARNING: HttpxDownloadHandler is experimental") == 2
        assert log.count("WARNING: ") == 2

    def test_reactorless_custom_settings(self):
        """Setting TWISTED_REACTOR_ENABLED=False in spider settings is not
        currently supported, AsyncCrawlerRunner will expect a reactor installed
        by the user.
        """
        log = self.run_script("reactorless_custom_settings.py")
        assert "Spider closed (finished)" not in log
        assert "We expected a Twisted reactor to be installed but it isn't." in log

    def test_reactorless_datauri(self):
        log = self.run_script("reactorless_datauri.py")
        assert "Not using a Twisted reactor" in log
        assert "Spider closed (finished)" in log
        assert "{'data': 'foo'}" in log
        assert "'item_scraped_count': 1" in log
        assert "ERROR: " not in log
        assert log.count("WARNING: HttpxDownloadHandler is experimental") == 2
        assert log.count("WARNING: ") == 2

    def test_reactorless_reactor(self):
        log = self.run_script("reactorless_reactor.py")
        assert (
            "RuntimeError: TWISTED_REACTOR_ENABLED is False but a Twisted reactor is installed"
            in log
        )
