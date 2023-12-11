from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Union

from w3lib import html

from scrapy import Request, Spider
from scrapy.crawler import Crawler
from scrapy.exceptions import NotConfigured
from scrapy.http import HtmlResponse, Response
from scrapy.settings import BaseSettings

if TYPE_CHECKING:
    # typing.Self requires Python 3.11
    from typing_extensions import Self

logger = logging.getLogger(__name__)


class AjaxCrawlMiddleware:
    """
    Handle 'AJAX crawlable' pages marked as crawlable via meta tag.
    For more info see https://developers.google.com/webmasters/ajax-crawling/docs/getting-started.
    """

    def __init__(self, settings: BaseSettings):
        if not settings.getbool("AJAXCRAWL_ENABLED"):
            raise NotConfigured

        # XXX: Google parses at least first 100k bytes; scrapy's redirect
        # middleware parses first 4k. 4k turns out to be insufficient
        # for this middleware, and parsing 100k could be slow.
        # We use something in between (32K) by default.
        self.lookup_bytes: int = settings.getint("AJAXCRAWL_MAXSIZE", 32768)

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        return cls(crawler.settings)

    def process_response(
        self, request: Request, response: Response, spider: Spider
    ) -> Union[Request, Response]:
        if not isinstance(response, HtmlResponse) or response.status != 200:
            return response

        if request.method != "GET":
            # other HTTP methods are either not safe or don't have a body
            return response

        if "ajax_crawlable" in request.meta:  # prevent loops
            return response

        if not self._has_ajax_crawlable_variant(response):
            return response

        # scrapy already handles #! links properly
        ajax_crawl_request = request.replace(url=request.url + "#!")
        logger.debug(
            "Downloading AJAX crawlable %(ajax_crawl_request)s instead of %(request)s",
            {"ajax_crawl_request": ajax_crawl_request, "request": request},
            extra={"spider": spider},
        )

        ajax_crawl_request.meta["ajax_crawlable"] = True
        return ajax_crawl_request

    def _has_ajax_crawlable_variant(self, response: Response) -> bool:
        """
        Return True if a page without hash fragment could be "AJAX crawlable"
        according to https://developers.google.com/webmasters/ajax-crawling/docs/getting-started.
        """
        body = response.text[: self.lookup_bytes]
        return _has_ajaxcrawlable_meta(body)


# XXX: move it to w3lib?
_ajax_crawlable_re: re.Pattern[str] = re.compile(
    r'<meta\s+name=["\']fragment["\']\s+content=["\']!["\']/?>'
)


def _has_ajaxcrawlable_meta(text: str) -> bool:
    """
    >>> _has_ajaxcrawlable_meta('<html><head><meta name="fragment"  content="!"/></head><body></body></html>')
    True
    >>> _has_ajaxcrawlable_meta("<html><head><meta name='fragment' content='!'></head></html>")
    True
    >>> _has_ajaxcrawlable_meta('<html><head><!--<meta name="fragment"  content="!"/>--></head><body></body></html>')
    False
    >>> _has_ajaxcrawlable_meta('<html></html>')
    False
    """

    # Stripping scripts and comments is slow (about 20x slower than
    # just checking if a string is in text); this is a quick fail-fast
    # path that should work for most pages.
    if "fragment" not in text:
        return False
    if "content" not in text:
        return False

    text = html.remove_tags_with_content(text, ("script", "noscript"))
    text = html.replace_entities(text)
    text = html.remove_comments(text)
    return _ajax_crawlable_re.search(text) is not None
