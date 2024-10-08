from __future__ import annotations

import logging
import re
import gzip
import xml.etree.ElementTree as ET
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    Iterable,
    List,
    Optional,
    Sequence,
    Tuple,
    Union,
    cast,
)

from scrapy.http import Request, Response, XmlResponse
from scrapy.spiders import Spider
from scrapy.utils._compression import _DecompressionMaxSizeExceeded
from scrapy.utils.gz import gunzip, gzip_magic_number
from scrapy.utils.sitemap import Sitemap, sitemap_urls_from_robots
from io import BytesIO

if TYPE_CHECKING:
    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.crawler import Crawler
    from scrapy.http.request import CallbackT

logger = logging.getLogger(__name__)


class SitemapSpider(Spider):
    sitemap_urls: Sequence[str] = ()
    sitemap_rules: Sequence[
        Tuple[Union[re.Pattern[str], str], Union[str, CallbackT]]
    ] = [("", "parse")]
    sitemap_follow: Sequence[Union[re.Pattern[str], str]] = [""]
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
        self._cbs: List[Tuple[re.Pattern[str], CallbackT]] = []
        for r, c in self.sitemap_rules:
            if isinstance(c, str):
                c = cast("CallbackT", getattr(self, c))
            self._cbs.append((regex(r), c))
        self._follow: List[re.Pattern[str]] = [regex(x) for x in self.sitemap_follow]

    def start_requests(self) -> Iterable[Request]:
        for url in self.sitemap_urls:
            yield Request(url, self._parse_sitemap)

    def sitemap_filter(
        self, entries: Iterable[Dict[str, Any]]
    ) -> Iterable[Dict[str, Any]]:
        """This method can be used to filter sitemap entries by their
        attributes, for example, you can filter locs with lastmod greater
        than a given date (see docs).
        """
        yield from entries

    def _parse_sitemap(self, response: Response) -> Iterable[Request]:
    # Try to parse robots.txt for sitemaps if the response is robots.txt
    if response.url.endswith("/robots.txt"):
        for url in sitemap_urls_from_robots(response.text, base_url=response.url):
            yield Request(url, callback=self._parse_sitemap)
        return
    
    # Get the sitemap body (can handle XML, .xml.gz, etc.)
    body = self._get_sitemap_body(response)
    if body is None:
        logger.warning(
            "Ignoring invalid sitemap: %(response)s",
            {"response": response},
            extra={"spider": self},
        )
        return

    # Stream the sitemap if it's an XML sitemap
    if response.url.endswith(".xml") or response.url.endswith(".xml.gz"):
        yield from self._stream_sitemap(body)

    def _stream_sitemap(self, body: bytes) -> Iterable[Request]:
    # Use streaming parsing to handle large sitemaps
    try:
        # Create an incremental XML parser
        context = ET.iterparse(BytesIO(body), events=("start", "end"))
        
        url = None
        for event, elem in context:
            if event == 'end' and elem.tag.endswith("loc"):
                url = elem.text
                elem.clear()  # Free up memory
            if event == 'end' and elem.tag.endswith("url"):
                # Filter and process each <url> element as it's encountered
                if url:
                    for r, c in self._cbs:
                        if r.search(url):
                            yield Request(url, callback=c)
                            break
                elem.clear()
        except ET.ParseError as e:
            logger.error(f"Error parsing sitemap: {e}")

    def _get_sitemap_body(self, response: Response) -> Optional[bytes]:
    """Return the sitemap body contained in the given response,
    or None if the response is not a sitemap.
    """
    if isinstance(response, XmlResponse):
        return response.body
    if gzip_magic_number(response):
        max_size = response.meta.get("download_maxsize", self._max_size)
        return self._decompress_gzip_stream(response.body, max_size)
    if response.url.endswith(".xml") or response.url.endswith(".xml.gz"):
        return response.body
    return None

    def _decompress_gzip_stream(self, data: bytes, max_size: int) -> Optional[bytes]:
    """Decompress gzipped sitemap data in chunks to avoid memory overload."""
    try:
        buffer = BytesIO(data)
        with gzip.GzipFile(fileobj=buffer) as gz_file:
            decompressed_data = BytesIO()
            total_size = 0
            chunk_size = 1024 * 1024  # 1 MB chunks
            
            while True:
                chunk = gz_file.read(chunk_size)
                if not chunk:
                    break
                total_size += len(chunk)
                if total_size > max_size:
                    raise _DecompressionMaxSizeExceeded(
                        f"Sitemap size exceeds maximum allowed size of {max_size} bytes"
                    )
                decompressed_data.write(chunk)
            
            return decompressed_data.getvalue()
        except _DecompressionMaxSizeExceeded as e:
            logger.warning(f"Sitemap exceeds allowed size: {e}")
            return None
        except Exception as e:
            logger.error(f"Error decompressing sitemap: {e}")
            return None

def regex(x: Union[re.Pattern[str], str]) -> re.Pattern[str]:
    if isinstance(x, str):
        return re.compile(x)
    return x

def iterloc(it: Iterable[Dict[str, Any]], alt: bool = False) -> Iterable[str]:
    for d in it:
        yield d["loc"]

        # Also consider alternate URLs (xhtml:link rel="alternate")
        if alt and "alternate" in d:
            yield from d["alternate"]
