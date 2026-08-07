from __future__ import annotations

import logging
import re

# Iterable is needed at the run time for the SitemapSpider._parse_sitemap() annotation
from collections.abc import AsyncIterator, Iterable, Sequence  # noqa: TC003
from typing import TYPE_CHECKING, Any, cast

from scrapy.http import Request, Response, XmlResponse
from scrapy.spiders import Spider
from scrapy.utils._compression import _DecompressionMaxSizeExceeded
from scrapy.utils.gz import gunzip, gzip_magic_number
from scrapy.utils.sitemap import Sitemap, sitemap_urls_from_robots

if TYPE_CHECKING:
    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.crawler import Crawler
    from scrapy.http.request import CallbackT

logger = logging.getLogger(__name__)


class SitemapSpider(Spider):
    """Spider that crawls a site by discovering its URLs using `sitemaps
    <https://www.sitemaps.org/index.html>`_.

    It supports nested sitemaps and discovering sitemap URLs from `robots.txt
    <https://www.robotstxt.org/>`_.
    """

    #: URLs pointing to the sitemaps whose URLs you want to crawl.
    #:
    #: You can also point to a `robots.txt <https://www.robotstxt.org/>`_ and it
    #: will be parsed to extract sitemap URLs from it.
    sitemap_urls: Sequence[str] = ()

    #: ``(regex, callback)`` tuples where:
    #:
    #: -   ``regex`` is a regular expression to match URLs extracted from
    #:     sitemaps. ``regex`` can be either a str or a compiled regex object.
    #:
    #: -   ``callback`` is the callback to use for processing the URLs that match
    #:     the regular expression. ``callback`` can be a string (indicating the
    #:     name of a spider method) or a callable.
    #:
    #: For example:
    #:
    #: .. code-block:: python
    #:
    #:     sitemap_rules = [("/product/", "parse_product")]
    #:
    #: Rules are applied in order, and only the first one that matches will be
    #: used.
    #:
    #: The default value makes all URLs found in sitemaps be processed with the
    #: :meth:`~scrapy.Spider.parse` callback.
    sitemap_rules: Sequence[tuple[re.Pattern[str] | str, str | CallbackT]] = [
        ("", "parse")
    ]

    #: Regexes of sitemaps that should be followed. This is only for sites that
    #: use `sitemap index files
    #: <https://www.sitemaps.org/protocol.html#index>`_ that point to other
    #: sitemap files.
    #:
    #: By default, all sitemaps are followed.
    sitemap_follow: Sequence[re.Pattern[str] | str] = [""]

    #: Specifies if alternate links for one ``url`` should be followed. These are
    #: links for the same website in another language passed within the same
    #: ``url`` block.
    #:
    #: For example:
    #:
    #: .. code-block:: xml
    #:
    #:     <url>
    #:         <loc>http://example.com/</loc>
    #:         <xhtml:link rel="alternate" hreflang="de" href="http://example.com/de"/>
    #:     </url>
    #:
    #: When enabled, this would retrieve both URLs. When disabled, only
    #: ``http://example.com/`` would be retrieved.
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
        """Yield the sitemap entries from *entries* that should be processed.

        Override it to select sitemap entries based on their attributes. For
        example, given the following sitemap entry:

        .. code-block:: xml

            <url>
                <loc>http://example.com/</loc>
                <lastmod>2005-01-01</lastmod>
            </url>

        You can filter entries by date as follows:

        .. code-block:: python

            from datetime import datetime
            from scrapy.spiders import SitemapSpider


            class FilteredSitemapSpider(SitemapSpider):
                name = "filtered_sitemap_spider"
                allowed_domains = ["example.com"]
                sitemap_urls = ["http://example.com/sitemap.xml"]

                def sitemap_filter(self, entries):
                    for entry in entries:
                        date_time = datetime.strptime(entry["lastmod"], "%Y-%m-%d")
                        if date_time.year >= 2005:
                            yield entry

        This would retrieve only entries modified on 2005 and the following
        years.

        Entries are dict objects extracted from the sitemap document. Usually,
        the key is the tag name and the value is the text inside it.

        It's important to notice that:

        -   as the ``loc`` attribute is required, entries without this tag are
            discarded
        -   alternate links are stored in a list with the key ``alternate``
            (see :attr:`sitemap_alternate_links`)
        -   namespaces are removed, so lxml tags named as ``{namespace}tagname``
            become only ``tagname``

        The default implementation yields all entries, observing other
        attributes and their settings.
        """
        yield from entries

    def _parse_sitemap(self, response: Response) -> Iterable[Request]:
        if response.url.endswith("/robots.txt"):
            urls = list(sitemap_urls_from_robots(response.body, base_url=response.url))
            return (Request(url, callback=self._parse_sitemap) for url in urls)

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
            urls = list(self._get_urls_from_sitemapindex(self.sitemap_filter(s)))
            return (Request(loc, callback=self._parse_sitemap) for loc in urls)

        if s.type == "urlset":
            url_callback_pairs = list(
                self._get_urls_and_callbacks_from_urlset(self.sitemap_filter(s))
            )
            return (Request(loc, callback=c) for loc, c in url_callback_pairs)

        logger.warning(
            "Ignoring invalid sitemap: %(response)s",
            {"response": response},
            extra={"spider": self},
        )

        return ()

    def _get_urls_from_sitemapindex(
        self, it: Iterable[dict[str, Any]]
    ) -> Iterable[str]:
        for loc in iterloc(it, self.sitemap_alternate_links):
            if any(x.search(loc) for x in self._follow):
                yield loc

    def _get_urls_and_callbacks_from_urlset(
        self, it: Iterable[dict[str, Any]]
    ) -> Iterable[tuple[str, CallbackT]]:
        for loc in iterloc(it, self.sitemap_alternate_links):
            for r, c in self._cbs:
                if r.search(loc):
                    yield loc, c
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
    for d in it:
        if loc := d["loc"]:
            yield loc

        # Also consider alternate URLs (xhtml:link rel="alternate")
        if alt and (alt_list := d.get("alternate")):
            yield from alt_list
