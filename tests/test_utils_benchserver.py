from __future__ import annotations

import re
from typing import TYPE_CHECKING, cast

from scrapy.utils.benchserver import Root, _getarg

if TYPE_CHECKING:
    from twisted.web.server import Request


class _Request:
    def __init__(self, **args: bytes) -> None:
        self.args = {name.encode(): [value] for name, value in args.items()}
        self.written: list[bytes] = []

    def write(self, data: bytes) -> None:
        self.written.append(data)


def test_getarg() -> None:
    request = cast("Request", _Request(total=b"5"))
    assert _getarg(request, b"total", 100, int) == 5
    assert _getarg(request, b"show", 100, int) == 100
    assert _getarg(request, b"missing") is None


def test_render() -> None:
    root = Root()  # type: ignore[no-untyped-call]
    request = _Request(total=b"5", show=b"2")
    assert root.getChild("follow", cast("Request", request)) is root
    assert root.render(cast("Request", request)) == b""
    body = b"".join(request.written).decode()
    assert body.startswith("<html><head></head><body>")
    assert body.endswith("</body></html>")
    numbers = re.findall(
        r"<a href='/follow\?total=5&show=2&n=(\d+)'>follow \1</a>", body
    )
    assert len(numbers) == 2
    assert all(1 <= int(number) <= 5 for number in numbers)
