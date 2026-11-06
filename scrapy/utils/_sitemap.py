from __future__ import annotations

import warnings
from io import BytesIO
from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin

import lxml.etree
from protego import Protego

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.robotstxt import decode_robotstxt

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
                    if el.get("rel") == "alternate" and (href := el.get("href")):
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
        tag = elem.tag
        if not isinstance(tag, str):
            return ""
        _, _, localname = tag.partition("}")
        return localname or tag


def sitemap_urls_from_robots(
    robots_text: str | bytes,
    base_url: str | None = None,
) -> Iterable[str]:
    if isinstance(robots_text, bytes):
        robots_text = decode_robotstxt(robots_text)
    else:
        warnings.warn(
            "Passing `str` type as `robots_text` is deprecated, use `bytes`",
            ScrapyDeprecationWarning,
            stacklevel=2,
        )
    for url in Protego.parse(robots_text).sitemaps:
        yield urljoin(base_url or "", url)
