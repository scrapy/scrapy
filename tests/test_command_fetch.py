from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from tests.utils.bases.commands import TestProjectBase
from tests.utils.cmdline import proc

if TYPE_CHECKING:
    from pathlib import Path

    from tests.mockserver.http import MockServer


class TestFetchCommand:
    @pytest.mark.parametrize("args", [(), ("not-a-url",), ("a:b", "c:d")])
    def test_bad_arguments(self, args: tuple[str, ...]) -> None:
        returncode, out, _ = proc("fetch", *args)
        assert returncode == 2
        assert "Usage" in out

    def test_output(self, mockserver: MockServer) -> None:
        _, out, _ = proc("fetch", mockserver.url("/text"))
        assert out.strip() == "Works"

    def test_redirect_default(self, mockserver: MockServer) -> None:
        _, out, _ = proc("fetch", mockserver.url("/redirect"))
        assert out.strip() == "Redirected here"

    def test_redirect_disabled(self, mockserver: MockServer) -> None:
        _, _, err = proc(
            "fetch", "--no-redirect", mockserver.url("/redirect-no-meta-refresh")
        )
        err = err.strip()
        assert "downloader/response_status_count/302" in err
        assert "downloader/response_status_count/200" not in err

    def test_headers(self, mockserver: MockServer) -> None:
        _, out, _ = proc("fetch", mockserver.url("/text"), "--headers")
        out = out.replace("\r", "")  # required on win32
        assert "Server: TwistedWeb" in out
        assert "Content-Type: text/plain" in out

    def test_no_reactor(self, mockserver: MockServer) -> None:
        _, out, _ = proc(
            "fetch", "-s", "TWISTED_REACTOR_ENABLED=False", mockserver.url("/text")
        )
        assert out.strip() == "Works"

    def test_curl(self, mockserver: MockServer) -> None:
        url = mockserver.url("/echo")
        _, out, _ = proc("fetch", "--curl", f"curl -d a=1 -H 'X-Test: foo' {url}")
        echo = json.loads(out)
        assert echo["body"] == "a=1"
        assert echo["headers"]["X-Test"] == ["foo"]

    def test_curl_with_url(self, mockserver: MockServer) -> None:
        url = mockserver.url("/echo")
        code, _, _ = proc("fetch", "--curl", f"curl {url}", url)
        assert code != 0

    def test_curl_invalid(self) -> None:
        code, _, err = proc("fetch", "--curl", "not-a-curl-command")
        assert code != 0
        assert "curl" in err


class TestFetchCommandWithSpider(TestProjectBase):
    @pytest.fixture(autouse=True)
    def create_files(self, proj_path: Path) -> None:
        (proj_path / self.project_name / "spiders" / "myspider.py").write_text(
            """
import scrapy

class MySpider(scrapy.Spider):
    name = "myspider"
    custom_settings = {"USER_AGENT": "myspider-user-agent"}
""",
            encoding="utf-8",
        )

    def test_spider(self, proj_path: Path, mockserver: MockServer) -> None:
        _, out, err = proc(
            "fetch", "--spider", "myspider", mockserver.url("/echo"), cwd=proj_path
        )
        assert "myspider-user-agent" in out, err
