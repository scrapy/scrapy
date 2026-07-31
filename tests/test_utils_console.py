from __future__ import annotations

import subprocess
import sys
from importlib.util import find_spec
from inspect import signature
from io import BytesIO
from typing import TYPE_CHECKING

import pytest
from pexpect import EOF

from scrapy.utils.console import get_shell_embed_func, start_python_console
from scrapy.utils.test import get_testenv

if TYPE_CHECKING:
    from pathlib import Path

CONSOLE = """
from scrapy.utils.console import start_python_console

start_python_console(banner="SHELL-READY", shells=["ipython"])
"""

CONSOLE_IN_RUNNING_LOOP = """
import asyncio

from scrapy.utils.console import start_python_console


async def main():
    start_python_console(banner="SHELL-READY", shells=["ipython"])


asyncio.run(main())
"""


def test_get_shell_embed_func():
    shell = get_shell_embed_func(["invalid"])
    assert shell is None

    shell = get_shell_embed_func(["invalid", "python"])
    assert callable(shell)
    assert shell.__name__ == "_embed_standard_shell"


def test_get_shell_embed_func_python():
    # the standard shell is always available
    shell = get_shell_embed_func(["python"])
    assert callable(shell)
    assert shell.__name__ == "_embed_standard_shell"


def test_get_shell_embed_func_bpython():
    pytest.importorskip("bpython")
    shell = get_shell_embed_func(["bpython"])
    assert callable(shell)
    assert shell.__name__ == "_embed_bpython_shell"


def test_get_shell_embed_func_ipython():
    pytest.importorskip("IPython")
    shell = get_shell_embed_func(["ipython"])
    assert shell is not None
    assert shell.__name__ == "_embed_ipython_shell"


def test_get_shell_embed_func_ptpython():
    pytest.importorskip("ptpython")
    shell = get_shell_embed_func(["ptpython"])
    assert shell is not None
    assert shell.__name__ == "_embed_ptpython_shell"


def test_get_shell_embed_func_default():
    # with no shells given, the first available shell in preference order
    # (ptpython, ipython, bpython, python) is returned; the standard shell
    # is always available, so the default is never None
    shell = get_shell_embed_func()
    assert shell is not None
    if find_spec("ptpython") is not None:
        expected = "_embed_ptpython_shell"
    elif find_spec("IPython") is not None:
        expected = "_embed_ipython_shell"
    elif find_spec("bpython") is not None:
        expected = "_embed_bpython_shell"
    else:
        expected = "_embed_standard_shell"
    assert shell.__name__ == expected


@pytest.mark.skipif(find_spec("IPython") is None, reason="IPython is not installed")
class TestIPythonShell:
    """Starting an IPython shell, with and without an asyncio event loop already
    running in the calling thread. The latter happens when inspect_response() is
    called from a spider callback while using the asyncio reactor.
    See https://github.com/scrapy/scrapy/issues/5447"""

    @staticmethod
    def _env(tmp_path: Path) -> dict[str, str]:
        env = get_testenv()
        # Keep IPython away from the profile and history of the user running the tests.
        env["IPYTHONDIR"] = str(tmp_path)
        return env

    def test_simple_prompt(self, tmp_path: Path) -> None:
        """IPython falls back to its simple prompt, which needs no event loop,
        when stdin is not a TTY."""
        env = self._env(tmp_path)
        env["IPY_TEST_SIMPLE_PROMPT"] = "1"
        p = subprocess.run(
            [sys.executable, "-c", CONSOLE_IN_RUNNING_LOOP],
            check=False,
            capture_output=True,
            encoding="utf-8",
            timeout=60,
            env=env,
            stdin=subprocess.DEVNULL,
        )
        output = p.stdout + p.stderr
        assert "SHELL-READY" in output, output
        assert p.returncode == 0, output

    @pytest.mark.skipif(
        sys.platform == "win32", reason="requires a POSIX pseudo-terminal"
    )
    @pytest.mark.parametrize(
        "script",
        [CONSOLE, CONSOLE_IN_RUNNING_LOOP],
        ids=["no_running_loop", "running_loop"],
    )
    def test_tty(self, tmp_path: Path, script: str) -> None:
        """IPython uses prompt_toolkit, which needs an event loop of its own,
        when stdin is a TTY."""
        # pexpect only defines spawn, which needs a pseudo-terminal, on POSIX.
        from pexpect import spawn  # noqa: PLC0415
        from prompt_toolkit.shortcuts import PromptSession  # noqa: PLC0415

        # shell.pt_app is a PromptSession, and old prompt_toolkit versions, e.g.
        # the one that IPython 7.1 uses, cannot run the prompt in a thread.
        if "in_thread" not in signature(PromptSession.prompt).parameters:
            pytest.skip("prompt_toolkit cannot run the prompt in a separate thread")

        env = self._env(tmp_path)
        env.pop("IPY_TEST_SIMPLE_PROMPT", None)
        env["TERM"] = "xterm"
        logfile = BytesIO()
        p = spawn(
            sys.executable,
            ["-c", script],
            env=env,
            timeout=60,
        )
        p.logfile_read = logfile
        try:
            # Wait for the prompt, which prompt_toolkit draws once it is done
            # querying the terminal, before typing into it.
            p.expect(r"In \[")
            p.sendline("21*2")
            p.expect_exact("42")
            p.sendline("exit()")
            p.expect(EOF)
        finally:
            p.close()
        output = logfile.getvalue().decode()
        assert "Traceback" not in output, output
        assert p.exitstatus == 0, output


def test_start_python_console_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    def embed(namespace: dict[str, object], banner: str) -> None:
        raise SystemExit

    monkeypatch.setattr(
        "scrapy.utils.console.get_shell_embed_func", lambda shells: embed
    )
    start_python_console()


def test_start_python_console_no_shell(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "scrapy.utils.console.get_shell_embed_func", lambda shells: None
    )
    start_python_console()
