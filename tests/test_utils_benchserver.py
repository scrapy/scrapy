from __future__ import annotations

import re
from typing import Any

from twisted.web.test.requesthelper import DummyRequest

from scrapy.utils.benchserver import Root, _getarg


def _request(**args: bytes) -> Any:
    request = DummyRequest([b""])
    request.args = {name.encode(): [value] for name, value in args.items()}
    return request


def test_getarg() -> None:
    request = _request(total=b"5")
    assert _getarg(request, b"total", 100, int) == 5
    assert _getarg(request, b"show", 100, int) == 100
    assert _getarg(request, b"missing") is None


def test_render() -> None:
    root = Root()  # type: ignore[no-untyped-call]
    request = _request(total=b"5", show=b"2")
    assert root.getChild("follow", request) is root
    assert root.render(request) == b""
    body = b"".join(request.written).decode()
    assert body.startswith("<html><head></head><body>")
    assert body.endswith("</body></html>")
    numbers = re.findall(
        r"<a href='/follow\?total=5&show=2&n=(\d+)'>follow \1</a>", body
    )
    assert len(numbers) == 2
    assert all(1 <= int(number) <= 5 for number in numbers)
