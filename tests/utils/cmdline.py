from __future__ import annotations

import subprocess
import sys
from typing import Any

import pytest

from scrapy.utils.test import get_testenv


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
