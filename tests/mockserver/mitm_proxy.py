from __future__ import annotations

import functools
import os
import re
import shutil
from pathlib import Path
from subprocess import PIPE, Popen
from urllib.parse import urlsplit, urlunsplit


@functools.cache
def mitmdump_cmd() -> list[str] | None:
    """Return the command prefix used to invoke ``mitmdump``, or ``None`` if it
    cannot be resolved.

    We don't want to install ``mitmproxy`` into the test env (it has a lot of
    dependencies that can conflict with some of the Scrapy/test ones, and its
    newer versions may not support older Python versions). So we expect it
    installed externally. We look for the ``mitmdump`` binary in the following
    sources:

    1. the ``MITMDUMP`` environment variable;
    2. a ``mitmdump`` binary on ``PATH``;
    3. using ``uvx --from mitmproxy mitmdump`` if ``uvx`` is available.
    """
    if env := os.environ.get("MITMDUMP"):
        return [env]
    if path := shutil.which("mitmdump"):
        return [path]
    if uvx := shutil.which("uvx"):
        return [uvx, "--from", "mitmproxy", "mitmdump"]
    return None


class MitmProxy:
    auth_user = "scrapy"
    auth_pass = "scrapy"

    def __init__(self, mode: str | None = None) -> None:
        self.mode = mode

    def start(self) -> str:
        cmd = mitmdump_cmd()
        if not cmd:
            raise RuntimeError(
                "mitmdump is not available. Please install mitmproxy or uv."
            )
        cert_path = Path(__file__).parent.parent.resolve() / "keys"
        args = [
            "--listen-host",
            "127.0.0.1",
            "--listen-port",
            "0",
            "--proxyauth",
            f"{self.auth_user}:{self.auth_pass}",
            "--set",
            f"confdir={cert_path}",
            "--ssl-insecure",
            "-s",
            str(Path(__file__).with_name("mitm_proxy_addon.py")),
        ]
        if self.mode:
            args += ["--mode", self.mode]
        self.proc: Popen[str] = Popen(
            [*cmd, *args],
            stdout=PIPE,
            text=True,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
        assert self.proc.stdout is not None
        scheme = "socks5" if self.mode == "socks5" else "http"
        line = ""
        for line in self.proc.stdout:
            m = re.search(r"listening at (?:\w+://)?([^:]+:\d+)", line)
            if m:
                host_port = m.group(1)
                return f"{scheme}://{self.auth_user}:{self.auth_pass}@{host_port}"
        self.stop()
        raise RuntimeError(f"Failed to parse mitmdump output: {line}")

    def stop(self) -> None:
        self.proc.kill()
        self.proc.communicate()


def wrong_credentials(proxy_url: str) -> str:
    bad_auth_proxy = list(urlsplit(proxy_url))
    bad_auth_proxy[1] = bad_auth_proxy[1].replace("scrapy:scrapy@", "wrong:wronger@")
    return urlunsplit(bad_auth_proxy)
