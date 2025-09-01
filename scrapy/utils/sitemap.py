"""
Module for processing Sitemaps.

Note: The main purpose of this module is to provide support for the
SitemapSpider, its API is subject to change without notice.
"""

from __future__ import annotations

from io import BytesIO
from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin

import lxml.etree

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator


class Sitemap:
    """Class to parse Sitemap (type=urlset) and Sitemap Index
    (type=sitemapindex) files"""

    def __init__(self, xmltext: bytes):
        self.xmliter = lxml.etree.iterparse(
            BytesIO(xmltext),
            recover=True,
            remove_comments=True,
            resolve_entities=False,
            remove_blank_text=True,
            collect_ids=False,
            remove_pis=True,
            events=("start",),
        )
        _, root = next(self.xmliter)
        self.type = self._get_tag_name(root)

    def __iter__(self) -> Iterator[dict[str, Any]]:
        for _, elem in self.xmliter:
            try:
                tag_name = self._get_tag_name(elem)
                if not tag_name or (tag_name != "url" and tag_name != "sitemap"):  # pylint: disable=consider-using-in # noqa: PLR1714
                    continue

                if d := self._process_sitemap_element(elem):
                    yield d
            finally:
                elem.clear()

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

        if not has_loc:
            return None

        if alternate:
            d["alternate"] = alternate

        return d

    @staticmethod
    def _get_tag_name(elem: lxml.etree._Element) -> str:
        assert isinstance(elem.tag, str)
        _, _, localname = elem.tag.partition("}")
        return localname or elem.tag


def sitemap_urls_from_robots(
    robots_text: bytes, base_url: str | None = None
) -> Iterable[str]:
    """Return an iterator over all sitemap urls contained in the given
    robots.txt file
    """
    for line in robots_text.splitlines():
        if line.lstrip().lower().startswith("sitemap:"):
            url = line.split(":", 1)[1].strip()
            yield urljoin(base_url or "", url)
