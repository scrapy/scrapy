from __future__ import annotations

from html import escape
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from scrapy import Request
from scrapy.http import HtmlResponse
from scrapy.linkextractors import LinkExtractor
from scrapy.utils.request import fingerprint

if TYPE_CHECKING:
    from pytest_codspeed import BenchmarkFixture  # type: ignore[import-not-found]

pytest.importorskip("pytest_codspeed", reason="Benchmarks require pytest-codspeed")

RESPONSE_URL = "https://www.example.com/catalogue/page-1.html"

# Links that each scenario returns for the benchmark page. They are fewer than
# the anchors of the page because links to images, to other non-crawlable files
# and to schemes that Scrapy cannot download are rejected, and, except in the
# scenario that keeps duplicates, because the links that the navigation repeats
# are collapsed.
LINKS = 64
DUPLICATE_LINKS = 89
CANONICAL_LINKS = 61
FILTERED_LINKS = 45

# Requests built from LINKS links that point to a different resource.
# Canonicalization maps the rest to one that another link already covers, e.g.
# two fragments of a page, or two spellings of one percent-escape.
FINGERPRINTS = 61


def _read_corpus() -> tuple[list[str], list[str]]:
    """Return the URLs of ``urls.txt``, and its first group of URLs.

    The first group is the site navigation, which the benchmark page repeats.
    """
    groups: list[list[str]] = [[]]
    for line in (Path(__file__).parent / "urls.txt").read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            if groups[-1]:
                groups.append([])
            continue
        groups[-1].append(line)
    urls = [url for group in groups for url in group]
    return urls, groups[0]


def _build_page(urls: list[str], navigation: list[str]) -> bytes:
    """Return an HTML page that links to *urls*.

    Every link is surrounded by the markup of a product listing, so that
    benchmarks also cover walking over the elements and attributes that a real
    page puts between links.
    """

    def item(index: int, url: str) -> str:
        href = escape(url)
        return (
            f'<li class="product" data-index="{index}">'
            f'<img src="/media/thumbnail-{index}.jpg" alt="Product {index}" '
            f'width="128" height="128">'
            f'<h3><a href="{href}">Product {index}</a></h3>'
            f'<p class="description">A description of product {index}.</p>'
            f"</li>"
        )

    def nav(urls: list[str]) -> str:
        links = "".join(f'<a href="{escape(url)}">{escape(url)}</a>' for url in urls)
        return f'<nav class="site">{links}</nav>'

    items = "".join(item(index, url) for index, url in enumerate(urls))
    return (
        "<!DOCTYPE html><html><head><title>Catalogue</title>"
        f'<base href="{RESPONSE_URL}"></head><body>'
        f'{nav(navigation)}<ul class="products">{items}</ul>{nav(navigation)}'
        "</body></html>"
    ).encode()


URLS, NAVIGATION = _read_corpus()
BODY = _build_page(URLS, NAVIGATION)


def _response() -> HtmlResponse:
    return HtmlResponse(RESPONSE_URL, body=BODY, encoding="utf-8")


@pytest.mark.parametrize(
    ("kwargs", "links"),
    [
        pytest.param({}, LINKS, id="default"),
        pytest.param({"unique": False}, DUPLICATE_LINKS, id="duplicates"),
        pytest.param({"canonicalize": True}, CANONICAL_LINKS, id="canonicalize"),
        pytest.param(
            {
                "allow": r"/catalogue/",
                "deny": r"/legal/",
                "allow_domains": ["example.com", "www.example.com"],
            },
            FILTERED_LINKS,
            id="filtered",
        ),
    ],
)
def test_extract_links(
    benchmark: BenchmarkFixture, kwargs: dict[str, Any], links: int
) -> None:
    """Extraction of every link of a page.

    The scenarios cover the choices that change which work dominates:
    deduplication and canonicalization both build a key for every link, and the
    filters of a configured extractor reject links before the later checks,
    which the default extractor reaches for every link.
    """
    link_extractor = LinkExtractor(**kwargs)

    def run() -> None:
        assert len(link_extractor.extract_links(_response())) == links

    benchmark(run)


EXTRACTED_URLS = [link.url for link in LinkExtractor().extract_links(_response())]


def test_requests(benchmark: BenchmarkFixture) -> None:
    """Building a request for every link of a page."""

    def run() -> None:
        assert len([Request(url) for url in EXTRACTED_URLS]) == LINKS

    benchmark(run)


def test_fingerprints(benchmark: BenchmarkFixture) -> None:
    """Fingerprinting the request of every link of a page.

    Requests are built here as well, and not once for all rounds, because
    fingerprints are cached per request object.
    """

    def run() -> None:
        assert (
            len({fingerprint(Request(url)) for url in EXTRACTED_URLS}) == FINGERPRINTS
        )

    benchmark(run)
