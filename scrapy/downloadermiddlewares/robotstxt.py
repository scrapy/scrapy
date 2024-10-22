"""
This is a middleware to respect robots.txt policies. To activate it you must
enable this middleware and enable the ROBOTSTXT_OBEY setting.

"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, TypeVar

from twisted.internet.defer import Deferred, maybeDeferred

from scrapy.exceptions import IgnoreRequest, NotConfigured
from scrapy.http import Request, Response
from scrapy.http.request import NO_CALLBACK
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.log import failure_to_exc_info
from scrapy.utils.misc import load_object

if TYPE_CHECKING:
    from twisted.python.failure import Failure

    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy import Spider
    from scrapy.crawler import Crawler
    from scrapy.robotstxt import RobotParser


logger = logging.getLogger(__name__)

_T = TypeVar("_T")


class RobotsTxtMiddleware:
    DOWNLOAD_PRIORITY: int = 1000

    def __init__(self, crawler: Crawler):
        if not crawler.settings.getbool("ROBOTSTXT_OBEY"):
            raise NotConfigured
        self._default_useragent: str = crawler.settings.get("USER_AGENT", "Scrapy")
        self._robotstxt_useragent: str | None = crawler.settings.get(
            "ROBOTSTXT_USER_AGENT", None
        )
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

    def process_request(
        self, request: Request, spider: Spider
    ) -> Deferred[None] | None:
        if request.meta.get("dont_obey_robotstxt"):
            return None
        if request.url.startswith("data:") or request.url.startswith("file:"):
            return None
        d: Deferred[RobotParser | None] = maybeDeferred(
            self.robot_parser, request, spider  # type: ignore[call-overload]
        )
        d2: Deferred[None] = d.addCallback(self.process_request_2, request, spider)
        return d2

    def process_request_2(
        self, rp: RobotParser | None, request: Request, spider: Spider
    ) -> None:
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
                extra={"spider": spider},
            )
            assert self.crawler.stats
            self.crawler.stats.inc_value("robotstxt/forbidden")
            raise IgnoreRequest("Forbidden by robots.txt")

    def robot_parser(
        self, request: Request, spider: Spider
    ) -> RobotParser | Deferred[RobotParser | None] | None:
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
            dfd = self.crawler.engine.download(robotsreq)
            dfd.addCallback(self._parse_robots, netloc, spider)
            dfd.addErrback(self._logerror, robotsreq, spider)
            dfd.addErrback(self._robots_error, netloc)
            self.crawler.stats.inc_value("robotstxt/request_count")

        parser = self._parsers[netloc]
        if isinstance(parser, Deferred):
            d: Deferred[RobotParser | None] = Deferred()

            def cb(result: RobotParser | None) -> RobotParser | None:
                d.callback(result)
                return result

            parser.addCallback(cb)
            return d
        return parser

    def _logerror(self, failure: Failure, request: Request, spider: Spider) -> Failure:
        if failure.type is not IgnoreRequest:
            logger.error(
                "Error downloading %(request)s: %(f_exception)s",
                {"request": request, "f_exception": failure.value},
                exc_info=failure_to_exc_info(failure),
                extra={"spider": spider},
            )
        return failure

    def _parse_robots(self, response: Response, netloc: str, spider: Spider) -> None:
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

    def _robots_error(self, failure: Failure, netloc: str) -> None:
        if failure.type is not IgnoreRequest:
            key = f"robotstxt/exception_count/{failure.type}"
            assert self.crawler.stats
            self.crawler.stats.inc_value(key)
        rp_dfd = self._parsers[netloc]
        assert isinstance(rp_dfd, Deferred)
        self._parsers[netloc] = None
        rp_dfd.callback(None)
