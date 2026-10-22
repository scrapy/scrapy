from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from scrapy.http import TextResponse
from tests import get_testdata

if TYPE_CHECKING:
    from pytest_codspeed import BenchmarkFixture  # type: ignore[import-not-found]

pytest.importorskip("pytest_codspeed", reason="Benchmarks require pytest-codspeed")

# A real page without its encoding declaration.
_PAGE = (
    get_testdata("books", "listing.html")
    .decode()
    .replace("text/html; charset=UTF-8", "text/html")
)


def _body(text: str, encoding: str) -> bytes:
    """Return :data:`_PAGE` with *text* added, encoded with *encoding*."""
    return _PAGE.replace("</body>", f"<p>{text * 500}</p></body>").encode(encoding)


_JAPANESE = "この本は在庫があります。"
_FRENCH = "Ce livre à prix réduit est déjà épuisé. "


@pytest.mark.parametrize(
    ("body", "encoding"),
    [
        pytest.param(_body(_JAPANESE, "utf-8"), "utf-8", id="utf-8"),
        pytest.param(_body(_JAPANESE, "shift_jis"), "cp932", id="shift_jis"),
        pytest.param(_body(_FRENCH, "cp1252"), "cp1252", id="windows-1252"),
    ],
)
def test_undeclared_encoding(
    benchmark: BenchmarkFixture, body: bytes, encoding: str
) -> None:
    """Decoding a page that declares no encoding."""

    def run() -> None:
        response = TextResponse("https://example.com", body=body)
        assert response.text
        assert response.encoding == encoding

    benchmark(run)
