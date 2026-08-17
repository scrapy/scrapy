from __future__ import annotations

import subprocess
import sys
from typing import TYPE_CHECKING, Any

import pytest

from scrapy.utils.test import get_testenv

if TYPE_CHECKING:
    from pathlib import Path

    from pexpect.popen_spawn import PopenSpawn


def call(*args: str, **popen_kwargs: Any) -> int:
    args = (sys.executable, "-m", "scrapy.cmdline", *args)
    return subprocess.call(
        args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=get_testenv(),
        **popen_kwargs,
    )


def proc(*args: str, **popen_kwargs: Any) -> tuple[int, str, str]:
    args = (sys.executable, "-m", "scrapy.cmdline", *args)
    try:
        p = subprocess.run(
            args,
            check=False,
            capture_output=True,
            encoding="utf-8",
            timeout=15,
            env=get_testenv(),
            **popen_kwargs,
        )
    except subprocess.TimeoutExpired:
        pytest.fail("Command took too much time to complete")

    return p.returncode, p.stdout, p.stderr


def stop_spawn(p: PopenSpawn[str]) -> None:
    p.sendeof()
    p.wait()  # type: ignore[no-untyped-call]
    # PopenSpawn leaves the subprocess pipes open, which triggers
    # ResourceWarning at an arbitrary garbage collection point.
    for pipe in (p.proc.stdin, p.proc.stdout):
        if pipe:
            pipe.close()


def write_recording_editor(editor: Path) -> None:
    """Create an executable editor script that writes the path it is asked to
    open (its last argument) into the file given as its first argument."""
    editor.write_text('#!/bin/sh\nprintf "%s" "$2" > "$1"\n', encoding="utf-8")
    editor.chmod(0o755)


def write_recording_browser(browser: Path, recorded: Path) -> None:
    """Create an executable browser script that writes the URL it is asked to
    open into *recorded*.

    ``webbrowser`` only passes the URL to the command from the ``BROWSER``
    environment variable, hence the hardcoded output path.
    """
    browser.write_text(
        f'#!/bin/sh\nprintf "%s" "$1" > "{recorded}"\n', encoding="utf-8"
    )
    browser.chmod(0o755)
