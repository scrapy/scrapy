from __future__ import annotations

import logging
import re
import warnings

# Iterable is needed at the run time for the SitemapSpider._parse_sitemap() annotation
from collections.abc import AsyncIterator, Iterable, Sequence  # noqa: TC003
from typing import TYPE_CHECKING, Any, Literal, cast

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.http import Request, Response, XmlResponse
from scrapy.spiders import Spider
from scrapy.utils._compression import (
    _DecompressionMaxSizeExceeded,
    gunzip,
    gzip_magic_number,
)
from scrapy.utils._sitemap import Sitemap, sitemap_urls_from_robots

if TYPE_CHECKING:
    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.crawler import Crawler
    from scrapy.http.request import CallbackT

logger = logging.getLogger(__name__)


class SitemapSpider(Spider):
    sitemap_urls: Sequence[str] = ()
    sitemap_rules: Sequence[tuple[re.Pattern[str] | str, str | CallbackT]] = [
        ("", "parse")
    ]
    sitemap_follow: Sequence[re.Pattern[str] | str] = [""]
    sitemap_alternate_links: bool = False
    _max_size: int
    _warn_size: int

    @classmethod
    def from_crawler(cls, crawler: Crawler, *args: Any, **kwargs: Any) -> Self:
        spider = super().from_crawler(crawler, *args, **kwargs)
        spider._max_size = getattr(
            spider, "download_maxsize", spider.settings.getint("DOWNLOAD_MAXSIZE")
        )
        spider._warn_size = getattr(
            spider, "download_warnsize", spider.settings.getint("DOWNLOAD_WARNSIZE")
        )
        return spider

    def __init__(self, *a: Any, **kw: Any):
        super().__init__(*a, **kw)
        self._cbs: list[tuple[re.Pattern[str], CallbackT]] = []
        for r, c in self.sitemap_rules:
            if isinstance(c, str):
                c = cast("CallbackT", getattr(self, c))  # noqa: PLW2901
            self._cbs.append((regex(r), c))
        self._follow: list[re.Pattern[str]] = [regex(x) for x in self.sitemap_follow]

    async def start(self) -> AsyncIterator[Any]:
        for url in self.sitemap_urls:
            yield Request(url, self._parse_sitemap)

    def sitemap_filter(
        self, entries: Iterable[dict[str, Any]]
    ) -> Iterable[dict[str, Any]]:
        """This method can be used to filter sitemap entries by their
        attributes, for example, you can filter locs with lastmod greater
        than a given date (see docs).
        """
        yield from entries

    def sitemap_request(
        self,
        loc: str,
        callback: CallbackT,
        entry: dict[str, Any],
        *,
        source: Literal["robotstxt", "sitemapindex", "urlset"],
        response: Response,
    ) -> Request:
        """Return the request for the *loc* URL of the sitemap *entry*, to be
        parsed with *callback*.

        .. versionadded:: VERSION

        Override this method to build those requests differently, e.g. to
        carry sitemap data and request metadata over to *callback*:

        .. code-block:: python

            def sitemap_request(self, loc, callback, entry, *, source, response):
                meta = {**response.meta, "lastmod": entry.get("lastmod")}
                return Request(loc, callback, meta=meta)

        *entry* is the sitemap entry that *loc* comes from, as described in
        :meth:`sitemap_filter`. When :attr:`sitemap_alternate_links` is
        enabled, the same entry is used for every alternate URL.

        *source* tells where *loc* comes from: ``"urlset"`` for a URL to
        crawl, ``"sitemapindex"`` for a sitemap linked from a sitemap index,
        and ``"robotstxt"`` for a sitemap linked from a :file:`robots.txt`
        file, where *entry* only has ``loc``.

        *response* is the response that *entry* was read from.
        """
        return Request(loc, callback=callback)

    def _parse_sitemap(self, response: Response) -> Iterable[Request]:
        if response.url.endswith("/robots.txt"):
            urls = [
                url
                for url in sitemap_urls_from_robots(
                    response.body, base_url=response.url
                )
                if any(x.search(url) for x in self._follow)
            ]
            return (
                self.sitemap_request(
                    url,
                    self._parse_sitemap,
                    {"loc": url},
                    source="robotstxt",
                    response=response,
                )
                for url in urls
            )

        body = self._get_sitemap_body(response)
        if not body:
            logger.warning(
                "Ignoring invalid sitemap: %(response)s",
                {"response": response},
                extra={"spider": self},
            )
            return ()

        s = Sitemap(body)

        if s.type == "sitemapindex":
            index_entries = list(
                self._get_urls_from_sitemapindex(self.sitemap_filter(s))
            )
            return (
                self.sitemap_request(
                    loc,
                    self._parse_sitemap,
                    entry,
                    source="sitemapindex",
                    response=response,
                )
                for loc, entry in index_entries
            )

        if s.type == "urlset":
            urlset_entries = list(
                self._get_urls_and_callbacks_from_urlset(self.sitemap_filter(s))
            )
            return (
                self.sitemap_request(loc, c, entry, source="urlset", response=response)
                for loc, c, entry in urlset_entries
            )

        logger.warning(
            "Ignoring invalid sitemap: %(response)s",
            {"response": response},
            extra={"spider": self},
        )

        return ()

    def _get_urls_from_sitemapindex(
        self, it: Iterable[dict[str, Any]]
    ) -> Iterable[tuple[str, dict[str, Any]]]:
        for loc, entry in _iterlocs(it, self.sitemap_alternate_links):
            if any(x.search(loc) for x in self._follow):
                yield loc, entry

    def _get_urls_and_callbacks_from_urlset(
        self, it: Iterable[dict[str, Any]]
    ) -> Iterable[tuple[str, CallbackT, dict[str, Any]]]:
        for loc, entry in _iterlocs(it, self.sitemap_alternate_links):
            for r, c in self._cbs:
                if r.search(loc):
                    yield loc, c, entry
                    break

    def _get_sitemap_body(self, response: Response) -> bytes | None:
        """Return the sitemap body contained in the given response,
        or None if the response is not a sitemap.
        """
        if isinstance(response, XmlResponse):
            return response.body
        if gzip_magic_number(response):
            uncompressed_size = len(response.body)
            max_size = response.meta.get("download_maxsize", self._max_size)
            warn_size = response.meta.get("download_warnsize", self._warn_size)
            try:
                body = gunzip(response.body, max_size=max_size)
            except _DecompressionMaxSizeExceeded:
                return None
            if uncompressed_size < warn_size <= len(body):
                logger.warning(
                    f"{response} body size after decompression ({len(body)} B) "
                    f"is larger than the download warning size ({warn_size} B)."
                )
            return body
        # actual gzipped sitemap files are decompressed above ;
        # if we are here (response body is not gzipped)
        # and have a response for .xml.gz,
        # it usually means that it was already gunzipped
        # by HttpCompression middleware,
        # the HTTP response being sent with "Content-Encoding: gzip"
        # without actually being a .xml.gz file in the first place,
        # merely XML gzip-compressed on the fly,
        # in other word, here, we have plain XML
        if response.url.endswith(".xml") or response.url.endswith(".xml.gz"):
            return response.body
        return None


def regex(x: re.Pattern[str] | str) -> re.Pattern[str]:
    if isinstance(x, str):
        return re.compile(x)
    return x


def iterloc(it: Iterable[dict[str, Any]], alt: bool = False) -> Iterable[str]:
    warnings.warn(
        "scrapy.spiders.sitemap.iterloc() is deprecated.",
        ScrapyDeprecationWarning,
        stacklevel=2,
    )
    return (loc for loc, _ in _iterlocs(it, alt))


def _iterlocs(
    it: Iterable[dict[str, Any]], alt: bool = False
) -> Iterable[tuple[str, dict[str, Any]]]:
    for d in it:
        if loc := d["loc"]:
            yield loc, d

        # Also consider alternate URLs (xhtml:link rel="alternate")
        if alt and (alt_list := d.get("alternate")):
            for loc in alt_list:
                yield loc, d
