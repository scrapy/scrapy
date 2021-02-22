import sys
import logging
from abc import ABCMeta, abstractmethod

from scrapy.utils.python import to_unicode


logger = logging.getLogger(__name__)


def decode_robotstxt(robotstxt_body, spider, to_native_str_type=False):
    try:
        if to_native_str_type:
            robotstxt_body = to_unicode(robotstxt_body)
        else:
            robotstxt_body = robotstxt_body.decode('utf-8')
    except UnicodeDecodeError:
        # If we found garbage or robots.txt in an encoding other than UTF-8, disregard it.
        # Switch to 'allow all' state.
        logger.warning(
            "Failure while parsing robots.txt. File either contains garbage or "
            "is in an encoding other than UTF-8, treating it as an empty file.",
            exc_info=sys.exc_info(),
            extra={'spider': spider},
        )
        robotstxt_body = ''
    return robotstxt_body


class RobotParser(metaclass=ABCMeta):
    @classmethod
    @abstractmethod
    def from_crawler(cls, crawler, robotstxt_body):
        """Parse the content of a robots.txt_ file as bytes. This must be a class method.
        It must return a new instance of the parser backend.

        :param crawler: crawler which made the request
        :type crawler: :class:`~scrapy.crawler.Crawler` instance

        :param robotstxt_body: content of a robots.txt_ file.
        :type robotstxt_body: bytes
        """
        pass

    @abstractmethod
    def allowed(self, url, user_agent):
        """Return ``True`` if  ``user_agent`` is allowed to crawl ``url``, otherwise return ``False``.

        :param url: Absolute URL
        :type url: str

        :param user_agent: User agent
        :type user_agent: str
        """
        pass


class PythonRobotParser(RobotParser):
    def __init__(self, robotstxt_body, spider):
        from urllib.robotparser import RobotFileParser
        self.spider = spider
        robotstxt_body = decode_robotstxt(robotstxt_body, spider, to_native_str_type=True)
        self.rp = RobotFileParser()
        self.rp.parse(robotstxt_body.splitlines())

    @classmethod
    def from_crawler(cls, crawler, robotstxt_body):
        spider = None if not crawler else crawler.spider
        o = cls(robotstxt_body, spider)
        return o

    def allowed(self, url, user_agent):
        user_agent = to_unicode(user_agent)
        url = to_unicode(url)
        return self.rp.can_fetch(user_agent, url)


class ReppyRobotParser(RobotParser):
    def __init__(self, robotstxt_body, spider):
        from reppy.robots import Robots
        self.spider = spider
        self.rp = Robots.parse('', robotstxt_body)

    @classmethod
    def from_crawler(cls, crawler, robotstxt_body):
        spider = None if not crawler else crawler.spider
        o = cls(robotstxt_body, spider)
        return o

    def allowed(self, url, user_agent):
        return self.rp.allowed(url, user_agent)


class RerpRobotParser(RobotParser):
    def __init__(self, robotstxt_body, spider):
        from robotexclusionrulesparser import RobotExclusionRulesParser
        self.spider = spider
        self.rp = RobotExclusionRulesParser()
        robotstxt_body = decode_robotstxt(robotstxt_body, spider)
        self.rp.parse(robotstxt_body)

    @classmethod
    def from_crawler(cls, crawler, robotstxt_body):
        spider = None if not crawler else crawler.spider
        o = cls(robotstxt_body, spider)
        return o

    def allowed(self, url, user_agent):
        user_agent = to_unicode(user_agent)
        url = to_unicode(url)
        return self.rp.is_allowed(user_agent, url)


class ProtegoRobotParser(RobotParser):
    def __init__(self, robotstxt_body, spider):
        from protego import Protego
        self.spider = spider
        robotstxt_body = decode_robotstxt(robotstxt_body, spider)
        self.rp = Protego.parse(robotstxt_body)

    @classmethod
    def from_crawler(cls, crawler, robotstxt_body):
        spider = None if not crawler else crawler.spider
        o = cls(robotstxt_body, spider)
        return o

    def allowed(self, url, user_agent):
        user_agent = to_unicode(user_agent)
        url = to_unicode(url)
        return self.rp.can_fetch(url, user_agent)
