from __future__ import annotations

import re
import sys
from pathlib import Path
from subprocess import PIPE, Popen
from urllib.parse import urlsplit, urlunsplit


class MitmProxy:
    auth_user = "scrapy"
    auth_pass = "scrapy"

    def start(self) -> str:
        script = """
import sys
from mitmproxy.tools.main import mitmdump
sys.argv[0] = "mitmdump"
sys.exit(mitmdump())
        """
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
        self.proc: Popen[str] = Popen(
            [
                sys.executable,
                "-u",
                "-c",
                script,
                *args,
            ],
            stdout=PIPE,
            text=True,
        )
        assert self.proc.stdout is not None
        line = ""
        for line in self.proc.stdout:
            m = re.search(r"listening at (?:http://)?([^:]+:\d+)", line)
            if m:
                host_port = m.group(1)
                return f"http://{self.auth_user}:{self.auth_pass}@{host_port}"
        self.stop()
        raise RuntimeError(f"Failed to parse mitmdump output: {line}")

    def stop(self) -> None:
        self.proc.kill()
        self.proc.communicate()


def wrong_credentials(proxy_url: str) -> str:
    bad_auth_proxy = list(urlsplit(proxy_url))
    bad_auth_proxy[1] = bad_auth_proxy[1].replace("scrapy:scrapy@", "wrong:wronger@")
    return urlunsplit(bad_auth_proxy)
