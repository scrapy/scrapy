from __future__ import annotations

import ast
import shutil
import subprocess
import sys
from types import SimpleNamespace
from typing import Any

import pytest

from scrapy.commands.genrequest import _format_code, _read_clipboard
from scrapy.exceptions import UsageError
from tests.utils.cmdline import proc


def _parse_request_call(code: str) -> dict[str, Any]:
    """Return the keyword arguments of the single ``Request(...)`` call in *code*.

    Optional ruff formatting changes quote style and line wrapping, so tests
    compare the parsed call rather than the raw text.
    """
    call = ast.parse(code, mode="eval").body
    assert isinstance(call, ast.Call)
    return {
        kw.arg: ast.literal_eval(kw.value) for kw in call.keywords if kw.arg is not None
    }


class TestGenRequestCommand:
    def test_get(self) -> None:
        _, out, _ = proc("genrequest", "curl http://example.com/")
        assert _parse_request_call(out) == {
            "method": "GET",
            "url": "http://example.com/",
        }

    def test_post_with_data(self) -> None:
        _, out, _ = proc("genrequest", "curl -d title=hello https://example.com/post")
        assert _parse_request_call(out) == {
            "method": "POST",
            "url": "https://example.com/post",
            "body": "title=hello",
        }

    def test_headers_and_cookies(self) -> None:
        _, out, _ = proc(
            "genrequest",
            "curl -H 'X-Test: 1' -b 'a=1' https://example.com/",
        )
        assert _parse_request_call(out) == {
            "method": "GET",
            "url": "https://example.com/",
            "headers": [("X-Test", "1")],
            "cookies": {"a": "1"},
        }

    def test_too_many_arguments(self) -> None:
        returncode, out, _ = proc("genrequest", "curl http://example.com/", "extra")
        assert returncode == 2
        assert "Usage" in out

    def test_invalid_curl_command(self) -> None:
        returncode, _, err = proc("genrequest", "not a curl command")
        assert returncode == 2
        assert "must start with" in err


class TestReadClipboard:
    def test_pyperclip(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setitem(
            sys.modules, "pyperclip", SimpleNamespace(paste=lambda: "curl a.example ")
        )
        assert _read_clipboard() == "curl a.example"

    def test_pyperclip_not_installed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setitem(sys.modules, "pyperclip", None)
        with pytest.raises(UsageError, match="scrapy\\[clipboard\\]"):
            _read_clipboard()


class TestFormatCode:
    CODE = "Request(method='GET', url='http://example.com/')"

    def test_ruff_not_installed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(shutil, "which", lambda name: None)
        assert _format_code(self.CODE) == self.CODE

    def test_ruff_formats(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/ruff")
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *a, **k: SimpleNamespace(stdout='Request(url="x")\n'),
        )
        assert _format_code(self.CODE) == 'Request(url="x")\n'

    def test_ruff_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/ruff")

        def _raise(*args: Any, **kwargs: Any) -> None:
            raise subprocess.CalledProcessError(1, "ruff")

        monkeypatch.setattr(subprocess, "run", _raise)
        assert _format_code(self.CODE) == self.CODE
