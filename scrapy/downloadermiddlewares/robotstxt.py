"""
This is a middleware to respect robots.txt policies. To activate it you must
enable this middleware and enable the ROBOTSTXT_OBEY setting.

"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from twisted.internet.defer import Deferred

from scrapy import signals
from scrapy.exceptions import CloseSpider, IgnoreRequest, NotConfigured
from scrapy.http import Request, Response
from scrapy.http.request import NO_CALLBACK
from scrapy.utils.decorators import _warn_spider_arg
from scrapy.utils.defer import maybe_deferred_to_future
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.misc import build_from_crawler, load_object

if TYPE_CHECKING:
    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy import Spider
    from scrapy.crawler import Crawler
    from scrapy.robotstxt import RobotParser
    from scrapy.statscollectors import StatsCollector


logger = logging.getLogger(__name__)


class RobotsTxtMiddleware:
    """This middleware filters out requests forbidden by the robots.txt
    exclusion standard.

    To make sure Scrapy respects robots.txt make sure the middleware is enabled
    and the :setting:`ROBOTSTXT_OBEY` setting is enabled.

    The :setting:`ROBOTSTXT_USER_AGENT` setting can be used to specify the
    user agent string to use for matching in the robots.txt_ file. If it
    is ``None``, the User-Agent header you are sending with the request or the
    :setting:`USER_AGENT` setting (in that order) will be used for determining
    the user agent to use in the robots.txt_ file.

    This middleware has to be combined with a robots.txt_ parser.

    Scrapy ships with support for the following robots.txt_ parsers:

    * :ref:`Protego <protego-parser>` (default)
    * :ref:`RobotFileParser <python-robotfileparser>`
    * :ref:`Robotexclusionrulesparser <rerp-parser>`

    You can change the robots.txt_ parser with the :setting:`ROBOTSTXT_PARSER`
    setting. Or you can also :ref:`implement support for a new parser
    <support-for-new-robots-parser>`.

    If no :ref:`start request <start-requests>` can be crawled, and robots.txt
    rules denied at least one of them, the crawl stops with the
    ``robotstxt_denied`` :stat:`finish_reason`, as long as
    :class:`~scrapy.spidermiddlewares.start.StartSpiderMiddleware` is enabled.
    """

    DOWNLOAD_PRIORITY: int = 1000

    def __init__(self, crawler: Crawler):
        if not crawler.settings.getbool("ROBOTSTXT_OBEY"):
            raise NotConfigured
        self._start_request_crawled = False
        self._start_request_denied = False
        self._default_useragent: str = crawler.settings["USER_AGENT"]
        self._robotstxt_useragent: str | None = crawler.settings["ROBOTSTXT_USER_AGENT"]
        self.crawler: Crawler = crawler
        self._stats: StatsCollector = crawler.stats
        self._parsers: dict[str, RobotParser | Deferred[RobotParser | None] | None] = {}
        self._parserimpl: RobotParser = load_object(
            crawler.settings.get("ROBOTSTXT_PARSER")
        )

        # check if parser dependencies are met, this should throw an error otherwise.
        build_from_crawler(self._parserimpl, self.crawler, b"")

        crawler.signals.connect(
            self._response_received, signal=signals.response_received
        )
        crawler.signals.connect(self._spider_idle, signal=signals.spider_idle)

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        return cls(crawler)

    def _response_received(self, request: Request) -> None:
        if request.meta.get("is_start_request"):
            self._start_request_crawled = True

    def _spider_idle(self) -> None:
        if self._start_request_crawled or not self._start_request_denied:
            return
        logger.error(
            "Stopping the crawl: no start request could be crawled, and at "
            "least one of them was rejected based on robots.txt rules. See "
            "https://docs.scrapy.org/en/latest/topics/downloader-middleware.html#topics-dlmw-robots"
        )
        raise CloseSpider("robotstxt_denied")

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
            self._stats.inc_value("robotstxt/forbidden")
            if request.meta.get("is_start_request"):
                self._start_request_denied = True
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
            try:
                resp = await self.crawler.engine.download_async(robotsreq)
                await self._parse_robots(resp, netloc, request)
            except Exception as e:
                if not isinstance(e, IgnoreRequest):
                    logger.error(
                        "Error downloading %(request)s: %(f_exception)s",
                        {"request": request, "f_exception": e},
                        exc_info=True,
                        extra={"spider": self.crawler.spider},
                    )
                self._robots_error(e, netloc)
            self._stats.inc_value("robotstxt/request_count")

        parser = self._parsers[netloc]
        if isinstance(parser, Deferred):
            return await maybe_deferred_to_future(parser)
        return parser

    async def _parse_robots(
        self, response: Response, netloc: str, request: Request
    ) -> None:
        self._stats.inc_value("robotstxt/response_count")
        self._stats.inc_value(f"robotstxt/response_status_count/{response.status}")
        rp = build_from_crawler(self._parserimpl, self.crawler, response.body)
        await self.crawler.signals.send_catch_log_async(
            signal=signals.robots_parsed,
            robotparser=rp,
            request=request,
        )
        rp_dfd = self._parsers[netloc]
        assert isinstance(rp_dfd, Deferred)
        self._parsers[netloc] = rp
        rp_dfd.callback(rp)

    def _robots_error(self, exc: Exception, netloc: str) -> None:
        if not isinstance(exc, IgnoreRequest):
            key = f"robotstxt/exception_count/{type(exc)}"
            self._stats.inc_value(key)
        rp_dfd = self._parsers[netloc]
        assert isinstance(rp_dfd, Deferred)
        self._parsers[netloc] = None
        rp_dfd.callback(None)
