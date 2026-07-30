from __future__ import annotations

import contextlib
import functools
import os
import shutil
import signal
import socket
import time
from pathlib import Path
from subprocess import DEVNULL, Popen
from urllib.parse import urlsplit, urlunsplit

from .utils import _free_port


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
        # Choose a free port ourselves instead of reading the mitmdump output
        # as there is no easy way to disable stdout buffering for all kinds of
        # mitmdump installs that we support.
        host = "127.0.0.1"
        port = _free_port()
        args = [
            "--listen-host",
            host,
            "--listen-port",
            str(port),
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
        self.proc: Popen[bytes] = Popen(
            [*cmd, *args],
            stdout=DEVNULL,
            stderr=DEVNULL,
            start_new_session=True,  # needed for killpg() to make sense
        )
        scheme = "socks5" if self.mode == "socks5" else "http"
        deadline = time.monotonic() + 60
        while True:
            if self.proc.poll() is not None:
                raise RuntimeError(
                    f"mitmdump exited with code {self.proc.returncode} before it "
                    f"started listening"
                )
            try:
                with socket.create_connection((host, port), timeout=1):
                    return f"{scheme}://{self.auth_user}:{self.auth_pass}@{host}:{port}"
            except OSError:
                if time.monotonic() >= deadline:
                    break
                time.sleep(0.05)
        self.stop()
        raise RuntimeError(f"mitmdump did not start listening on {host}:{port} in time")

    def stop(self) -> None:
        if os.name == "posix":
            # SIGKILL doesn't propagate to the actual process (child of uvx)
            # https://github.com/astral-sh/uv/issues/11817#issuecomment-2688830077
            # https://stackoverflow.com/a/61980200/113586
            with contextlib.suppress(ProcessLookupError):
                os.killpg(os.getpgid(self.proc.pid), signal.SIGKILL)
        else:
            self.proc.kill()
        self.proc.communicate()


def wrong_credentials(proxy_url: str) -> str:
    bad_auth_proxy = list(urlsplit(proxy_url))
    bad_auth_proxy[1] = bad_auth_proxy[1].replace("scrapy:scrapy@", "wrong:wronger@")
    return urlunsplit(bad_auth_proxy)
