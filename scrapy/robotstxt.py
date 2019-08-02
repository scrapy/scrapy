import sys
import logging
from abc import ABCMeta, abstractmethod
from six import with_metaclass

from scrapy.utils.python import to_native_str, to_unicode

logger = logging.getLogger(__name__)


class RobotParser(with_metaclass(ABCMeta)):
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
        :type url: string

        :param user_agent: User agent
        :type user_agent: string
        """
        pass


class PythonRobotParser(RobotParser):
    def __init__(self, robotstxt_body, spider):
        from six.moves.urllib_robotparser import RobotFileParser
        self.spider = spider
        try:
            robotstxt_body = to_native_str(robotstxt_body)
        except UnicodeDecodeError:
            # If we found garbage or robots.txt in an encoding other than UTF-8, disregard it.
            # Switch to 'allow all' state.
            logger.warning("Failure while parsing robots.txt using %(parser)s."
                           " File either contains garbage or is in an encoding other than UTF-8, treating it as an empty file.",
                           {'parser': "RobotFileParser"},
                           exc_info=sys.exc_info(),
                           extra={'spider': self.spider})
            robotstxt_body = ''
        self.rp = RobotFileParser()
        self.rp.parse(robotstxt_body.splitlines())

    @classmethod
    def from_crawler(cls, crawler, robotstxt_body):
        spider = None if not crawler else crawler.spider
        o = cls(robotstxt_body, spider)
        return o

    def allowed(self, url, user_agent):
        user_agent = to_native_str(user_agent)
        url = to_native_str(url)
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
        try:
            robotstxt_body = robotstxt_body.decode('utf-8')
        except UnicodeDecodeError:
            # If we found garbage or robots.txt in an encoding other than UTF-8, disregard it.
            # Switch to 'allow all' state.
            logger.warning("Failure while parsing robots.txt using %(parser)s."
                           " File either contains garbage or is in an encoding other than UTF-8, treating it as an empty file.",
                           {'parser': "RobotExclusionRulesParser"},
                           exc_info=sys.exc_info(),
                           extra={'spider': self.spider})
            robotstxt_body = ''
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
