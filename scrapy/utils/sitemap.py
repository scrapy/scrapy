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


def _bytes_io_from_anystr(str_or_bytes: str | bytes) -> BytesIO:
    return (
        BytesIO(str_or_bytes)
        if isinstance(str_or_bytes, bytes)
        else BytesIO(str_or_bytes.encode())
    )


class Sitemap:
    """Class to parse Sitemap (type=urlset) and Sitemap Index
    (type=sitemapindex) files"""

    def __init__(self, xmltext: str | bytes):
        self.xmliter = lxml.etree.iterparse(
            _bytes_io_from_anystr(xmltext),
            recover=True,
            remove_comments=True,
            resolve_entities=False,
            remove_blank_text=True,
            collect_ids=False,
            remove_pis=True,
            events=("start", "end"),
        )
        _, elem = next(self.xmliter)
        self.type = self._get_type(elem)

    def __iter__(self) -> Iterator[dict[str, Any]]:
        for _, elem in self.xmliter:
            d: dict[str, Any] = {}
            for el in elem:
                name = self._get_type(el)
                if name == "link":
                    if "href" in el.attrib:
                        d.setdefault("alternate", []).append(el.get("href"))
                else:
                    d[name] = el.text.strip() if el.text else ""
                el.clear()
            if "loc" in d:
                yield d
            elem.clear()

    @staticmethod
    def _get_type(elem: lxml.etree._Element) -> str:
        assert isinstance(elem.tag, str)
        _, _, localname = str(elem.tag).partition("}")
        return localname or elem.tag


def sitemap_urls_from_robots(
    robots_text: str | bytes, base_url: str | None = None
) -> Iterable[str]:
    """Return an iterator over all sitemap urls contained in the given
    robots.txt file
    """
    for line in _bytes_io_from_anystr(robots_text):
        if line.lstrip()[:8].lower() == b"sitemap:":
            url = line.partition(b":")[2].strip()
            yield urljoin(base_url or "", url.decode())
