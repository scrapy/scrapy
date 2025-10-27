"""
This is a middleware to respect robots.txt policies. To activate it you must
enable this middleware and enable the ROBOTSTXT_OBEY setting.

"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from twisted.internet.defer import Deferred

from scrapy.exceptions import IgnoreRequest, NotConfigured
from scrapy.http import Request, Response
from scrapy.http.request import NO_CALLBACK
from scrapy.utils.decorators import _warn_spider_arg
from scrapy.utils.defer import maybe_deferred_to_future
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.misc import load_object

if TYPE_CHECKING:
    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy import Spider
    from scrapy.crawler import Crawler
    from scrapy.robotstxt import RobotParser


logger = logging.getLogger(__name__)


class RobotsTxtMiddleware:
    DOWNLOAD_PRIORITY: int = 1000

    def __init__(self, crawler: Crawler):
        if not crawler.settings.getbool("ROBOTSTXT_OBEY"):
            raise NotConfigured
        self._default_useragent: str = crawler.settings["USER_AGENT"]
        self._robotstxt_useragent: str | None = crawler.settings["ROBOTSTXT_USER_AGENT"]
        self.crawler: Crawler = crawler
        self._parsers: dict[str, RobotParser | Deferred[RobotParser | None] | None] = {}
        self._parserimpl: RobotParser = load_object(
            crawler.settings.get("ROBOTSTXT_PARSER")
        )

        # check if parser dependencies are met, this should throw an error otherwise.
        self._parserimpl.from_crawler(self.crawler, b"")

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        return cls(crawler)

    @_warn_spider_arg
    async def process_request(
        self, request: Request, spider: Spider | None = None
    ) -> None:
        if request.meta.get("dont_obey_robotstxt"):
            return
        if request.url.startswith("data:") or request.url.startswith("file:"):
            return
        rp = await self.robot_parser(request)
        self.process_request_2(rp, request)

    def process_request_2(self, rp: RobotParser | None, request: Request) -> None:
        if rp is None:
            return

        useragent: str | bytes | None = self._robotstxt_useragent
        if not useragent:
            useragent = request.headers.get(b"User-Agent", self._default_useragent)
            assert useragent is not None
        if not rp.allowed(request.url, useragent):
            logger.debug(
                "Forbidden by robots.txt: %(request)s",
                {"request": request},
                extra={"spider": self.crawler.spider},
            )
            assert self.crawler.stats
            self.crawler.stats.inc_value("robotstxt/forbidden")
            raise IgnoreRequest("Forbidden by robots.txt")

    async def robot_parser(self, request: Request) -> RobotParser | None:
        url = urlparse_cached(request)
        netloc = url.netloc

        if netloc not in self._parsers:
            self._parsers[netloc] = Deferred()
            robotsurl = f"{url.scheme}://{url.netloc}/robots.txt"
            robotsreq = Request(
                robotsurl,
                priority=self.DOWNLOAD_PRIORITY,
                meta={"dont_obey_robotstxt": True},
                callback=NO_CALLBACK,
            )
            assert self.crawler.engine
            assert self.crawler.stats
            try:
                resp = await self.crawler.engine.download_async(robotsreq)
                self._parse_robots(resp, netloc)
            except Exception as e:
                if not isinstance(e, IgnoreRequest):
                    logger.error(
                        "Error downloading %(request)s: %(f_exception)s",
                        {"request": request, "f_exception": e},
                        exc_info=True,
                        extra={"spider": self.crawler.spider},
                    )
                self._robots_error(e, netloc)
            self.crawler.stats.inc_value("robotstxt/request_count")

        parser = self._parsers[netloc]
        if isinstance(parser, Deferred):
            return await maybe_deferred_to_future(parser)
        return parser

    def _parse_robots(self, response: Response, netloc: str) -> None:
        assert self.crawler.stats
        self.crawler.stats.inc_value("robotstxt/response_count")
        self.crawler.stats.inc_value(
            f"robotstxt/response_status_count/{response.status}"
        )
        rp = self._parserimpl.from_crawler(self.crawler, response.body)
        rp_dfd = self._parsers[netloc]
        assert isinstance(rp_dfd, Deferred)
        self._parsers[netloc] = rp
        rp_dfd.callback(rp)

    def _robots_error(self, exc: Exception, netloc: str) -> None:
        if not isinstance(exc, IgnoreRequest):
            key = f"robotstxt/exception_count/{type(exc)}"
            assert self.crawler.stats
            self.crawler.stats.inc_value(key)
        rp_dfd = self._parsers[netloc]
        assert isinstance(rp_dfd, Deferred)
        self._parsers[netloc] = None
        rp_dfd.callback(None)
