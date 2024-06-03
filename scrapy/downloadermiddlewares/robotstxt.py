"""
This is a middleware to respect robots.txt policies. To activate it you must
enable this middleware and enable the ROBOTSTXT_OBEY setting.

"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, Optional, Set, Union

from twisted.internet.defer import Deferred, maybeDeferred
from twisted.python.failure import Failure

from scrapy import Spider, signals
from scrapy.crawler import Crawler
from scrapy.exceptions import IgnoreRequest, NotConfigured
from scrapy.http import Request, Response
from scrapy.http.request import NO_CALLBACK
from scrapy.robotstxt import RobotParser
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.log import failure_to_exc_info
from scrapy.utils.misc import load_object

if TYPE_CHECKING:
    # typing.Self requires Python 3.11
    from typing_extensions import Self


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
    * :ref:`Reppy <reppy-parser>` (deprecated)

    You can change the robots.txt_ parser with the :setting:`ROBOTSTXT_PARSER`
    setting. Or you can also :ref:`implement support for a new parser
    <support-for-new-robots-parser>`.

    If all start requests from a spider are ignored due to robots.txt rules,
    the spider close reason becomes ``robotstxt_denied``.
    """

    DOWNLOAD_PRIORITY: int = 1000

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        return cls(crawler)

    def __init__(self, crawler: Crawler):
        self._forbidden_start_request_count = 0
        self._total_start_request_count = 0
        self._pending_start_request_fingerprints: Set[bytes] = set()
        self._exhausted_start_requests = False
        if not crawler.settings.getbool("ROBOTSTXT_OBEY"):
            raise NotConfigured
        self._default_useragent: str = crawler.settings.get("USER_AGENT", "Scrapy")
        self._robotstxt_useragent: Optional[str] = crawler.settings.get(
            "ROBOTSTXT_USER_AGENT", None
        )
        self.crawler: Crawler = crawler
        self._parsers: Dict[str, Union[RobotParser, Deferred, None]] = {}
        self._parserimpl: RobotParser = load_object(
            crawler.settings.get("ROBOTSTXT_PARSER")
        )

        # check if parser dependencies are met, this should throw an error otherwise.
        self._parserimpl.from_crawler(self.crawler, b"")
        assert crawler.request_fingerprinter is not None
        self._fingerprinter = crawler.request_fingerprinter

        crawler.signals.connect(
            self._start_request_returned, signal=signals.start_request_returned
        )
        crawler.signals.connect(
            self._start_requests_exhausted, signal=signals.start_requests_exhausted
        )

    def _start_request_returned(self, request):
        self._total_start_request_count += 1
        fingerprint = self._fingerprinter.fingerprint(request)
        self._pending_start_request_fingerprints.add(fingerprint)

    def _start_requests_exhausted(self):
        self._exhausted_start_requests = True
        self._maybe_close()

    def process_request(self, request: Request, spider: Spider) -> Optional[Deferred]:
        fingerprint = self._fingerprinter.fingerprint(request)
        if fingerprint in self._pending_start_request_fingerprints:
            self._pending_start_request_fingerprints.remove(fingerprint)
            is_start_request = True
        else:
            is_start_request = False

        if request.meta.get("dont_obey_robotstxt"):
            return None
        if request.url.startswith("data:") or request.url.startswith("file:"):
            return None
        d: Deferred = maybeDeferred(self.robot_parser, request, spider)
        if is_start_request:
            self._pending_start_request_fingerprints.add(fingerprint)
        d.addCallback(self.process_request_2, request, spider)
        return d

    def process_request_2(
        self, rp: Optional[RobotParser], request: Request, spider: Spider
    ) -> None:
        fingerprint = self._fingerprinter.fingerprint(request)
        if fingerprint in self._pending_start_request_fingerprints:
            self._pending_start_request_fingerprints.remove(fingerprint)
            is_start_request = True
        else:
            is_start_request = False

        if rp is None:
            return

        useragent: Union[str, bytes, None] = self._robotstxt_useragent
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

            if is_start_request:
                self._forbidden_start_request_count += 1
                self._maybe_close()

            raise IgnoreRequest("Forbidden by robots.txt")

    def robot_parser(
        self, request: Request, spider: Spider
    ) -> Union[RobotParser, Deferred, None]:
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
            d: Deferred = Deferred()

            def cb(result: Any) -> Any:
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

    def _maybe_close(self):
        if (
            not self._exhausted_start_requests
            or self._pending_start_request_fingerprints
        ):
            return
        if self._forbidden_start_request_count < self._total_start_request_count:
            return
        logger.error(
            "Stopping the spider, all start requests failed because they "
            "were rejected based on robots.txt rules. See "
            "https://docs.scrapy.org/en/latest/topics/downloader-middleware.html#topics-dlmw-robots"
        )
        self.crawler.engine.close_spider(self.crawler.spider, "robotstxt_denied")
