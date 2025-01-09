from __future__ import annotations

import logging
import sys
from abc import ABCMeta, abstractmethod
from typing import TYPE_CHECKING

from scrapy.utils.python import to_unicode

if TYPE_CHECKING:
    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy import Spider
    from scrapy.crawler import Crawler


logger = logging.getLogger(__name__)


def decode_robotstxt(
    robotstxt_body: bytes, spider: Spider | None, to_native_str_type: bool = False
) -> str:
    try:
        if to_native_str_type:
            body_decoded = to_unicode(robotstxt_body)
        else:
            body_decoded = robotstxt_body.decode("utf-8", errors="ignore")
    except UnicodeDecodeError:
        # If we found garbage or robots.txt in an encoding other than UTF-8, disregard it.
        # Switch to 'allow all' state.
        logger.warning(
            "Failure while parsing robots.txt. File either contains garbage or "
            "is in an encoding other than UTF-8, treating it as an empty file.",
            exc_info=sys.exc_info(),
            extra={"spider": spider},
        )
        body_decoded = ""
    return body_decoded


class RobotParser(metaclass=ABCMeta):
    @classmethod
    @abstractmethod
    def from_crawler(cls, crawler: Crawler, robotstxt_body: bytes) -> Self:
        """Parse the content of a robots.txt_ file as bytes. This must be a class method.
        It must return a new instance of the parser backend.

        :param crawler: crawler which made the request
        :type crawler: :class:`~scrapy.crawler.Crawler` instance

        :param robotstxt_body: content of a robots.txt_ file.
        :type robotstxt_body: bytes
        """

    @abstractmethod
    def allowed(self, url: str | bytes, user_agent: str | bytes) -> bool:
        """Return ``True`` if  ``user_agent`` is allowed to crawl ``url``, otherwise return ``False``.

        :param url: Absolute URL
        :type url: str or bytes

        :param user_agent: User agent
        :type user_agent: str or bytes
        """


class PythonRobotParser(RobotParser):
    def __init__(self, robotstxt_body: bytes, spider: Spider | None):
        from urllib.robotparser import RobotFileParser

        self.spider: Spider | None = spider
        body_decoded = decode_robotstxt(robotstxt_body, spider, to_native_str_type=True)
        self.rp: RobotFileParser = RobotFileParser()
        self.rp.parse(body_decoded.splitlines())

    @classmethod
    def from_crawler(cls, crawler: Crawler, robotstxt_body: bytes) -> Self:
        spider = None if not crawler else crawler.spider
        return cls(robotstxt_body, spider)

    def allowed(self, url: str | bytes, user_agent: str | bytes) -> bool:
        user_agent = to_unicode(user_agent)
        url = to_unicode(url)
        return self.rp.can_fetch(user_agent, url)


class RerpRobotParser(RobotParser):
    def __init__(self, robotstxt_body: bytes, spider: Spider | None):
        from robotexclusionrulesparser import RobotExclusionRulesParser

        self.spider: Spider | None = spider
        self.rp: RobotExclusionRulesParser = RobotExclusionRulesParser()
        body_decoded = decode_robotstxt(robotstxt_body, spider)
        self.rp.parse(body_decoded)

    @classmethod
    def from_crawler(cls, crawler: Crawler, robotstxt_body: bytes) -> Self:
        spider = None if not crawler else crawler.spider
        return cls(robotstxt_body, spider)

    def allowed(self, url: str | bytes, user_agent: str | bytes) -> bool:
        user_agent = to_unicode(user_agent)
        url = to_unicode(url)
        return self.rp.is_allowed(user_agent, url)


class ProtegoRobotParser(RobotParser):
    def __init__(self, robotstxt_body: bytes, spider: Spider | None):
        from protego import Protego

        self.spider: Spider | None = spider
        body_decoded = decode_robotstxt(robotstxt_body, spider)
        self.rp = Protego.parse(body_decoded)

    @classmethod
    def from_crawler(cls, crawler: Crawler, robotstxt_body: bytes) -> Self:
        spider = None if not crawler else crawler.spider
        return cls(robotstxt_body, spider)

    def allowed(self, url: str | bytes, user_agent: str | bytes) -> bool:
        user_agent = to_unicode(user_agent)
        url = to_unicode(url)
        return self.rp.can_fetch(url, user_agent)
