"""
Module for processing Sitemaps.

Note: The main purpose of this module is to provide support for the
SitemapSpider, its API is subject to change without notice.
"""

from __future__ import annotations

import warnings
from io import BytesIO, StringIO
from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin

import lxml.etree

from scrapy.exceptions import ScrapyDeprecationWarning

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator


class Sitemap:
    """Class to parse Sitemap (type=urlset) and Sitemap Index
    (type=sitemapindex) files"""

    __slots__ = ("type", "xmliter")

    def __init__(self, xmltext: str | bytes):
        if isinstance(xmltext, str):
            warnings.warn(
                "Passing `str` type as `xmltext` is deprecated, use `bytes`",
                ScrapyDeprecationWarning,
                stacklevel=2,
            )
            xmltext = xmltext.encode()

        self.xmliter = lxml.etree.iterparse(
            BytesIO(xmltext),
            recover=True,
            remove_comments=True,
            resolve_entities=False,
            remove_blank_text=True,
            collect_ids=False,
            remove_pis=True,
            events=("start", "end"),
        )
        _, root = next(self.xmliter)
        self.type = self._get_tag_name(root)

    def __iter__(self) -> Iterator[dict[str, Any]]:
        for event, elem in self.xmliter:
            if event == "start":
                continue

            if self._get_tag_name(elem) not in {"url", "sitemap"}:
                continue

            if d := self._process_sitemap_element(elem):
                yield d

    def _process_sitemap_element(
        self, elem: lxml.etree._Element
    ) -> dict[str, Any] | None:
        d: dict[str, Any] = {}
        alternate: list[str] = []
        has_loc = False

        for el in elem:
            try:
                tag_name = self._get_tag_name(el)
                if not tag_name:
                    continue

                if tag_name == "link":
                    if href := el.get("href"):
                        alternate.append(href)
                else:
                    d[tag_name] = el.text.strip() if el.text else ""
                    if not has_loc and tag_name == "loc":
                        has_loc = True
            finally:
                el.clear()
        elem.clear()
        parent = elem.getparent()
        if parent is not None:
            while elem.getprevious() is not None:
                del parent[0]

        if not has_loc:
            return None

        if alternate:
            d["alternate"] = alternate

        return d

    @staticmethod
    def _get_tag_name(elem: lxml.etree._Element) -> str:
        if TYPE_CHECKING:
            assert isinstance(elem.tag, str)
        _, _, localname = elem.tag.partition("}")
        return localname or elem.tag


def sitemap_urls_from_robots(
    robots_text: str | bytes,
    base_url: str | None = None,
) -> Iterable[str]:
    if isinstance(robots_text, bytes):
        for line in BytesIO(robots_text):
            if line.lstrip()[:8].lower() == b"sitemap:":
                url = line.partition(b":")[2].strip().decode()
                yield urljoin(base_url or "", url)

    else:
        yield from _sitemap_urls_from_robots_str(robots_text, base_url)


def _sitemap_urls_from_robots_str(
    robots_text: str,
    base_url: str | None = None,
) -> Iterable[str]:
    warnings.warn(
        "Passing `str` type as `robots_text` is deprecated, use `bytes`",
        ScrapyDeprecationWarning,
        stacklevel=2,
    )
    for line in StringIO(robots_text):
        if line.lstrip()[:8].lower() == "sitemap:":
            url = line.partition(":")[2].strip()
            yield urljoin(base_url or "", url)
