from __future__ import annotations

from typing import TYPE_CHECKING

from tests.utils.cmdline import proc

if TYPE_CHECKING:
    from tests.mockserver.http import MockServer


class TestFetchCommand:
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
