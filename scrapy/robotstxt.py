import sys
import logging

from scrapy.utils.python import to_native_str, to_unicode

logger = logging.getLogger(__name__)


class PythonRobotParser:
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

    def sitemaps(self):
        """RobotFileParser does not support Sitemaps directive."""
        logger.warning("Failure while retrieving sitemaps using %(parser)s."
                       " %(parser)s does not support Sitemaps directive.",
                       {'parser': "RobotFileParser"},
                       exc_info=sys.exc_info(),
                       extra={'spider': self.spider})
        return
        yield

    def crawl_delay(self, user_agent):
        """RobotFileParser does not support Crawl-delay directive for Python version < 3.6 ."""
        user_agent = to_native_str(user_agent)
        if hasattr(self.rp, 'crawl_delay'):
            delay = self.rp.crawl_delay(user_agent)
            return None if delay is None else float(delay)
        return None

    def preferred_host(self):
        """RobotFileParser does not support Host directive."""
        logger.warning("Failure while retrieving preferred host using %(parser)s."
                       " %(parser)s does not support Host directive.",
                       {'parser': "RobotFileParser"},
                       exc_info=sys.exc_info(),
                       extra={'spider': self.spider})
        return None


class ReppyRobotParser:
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

    def sitemaps(self):
        return (sitemap for sitemap in self.rp.sitemaps)

    def crawl_delay(self, user_agent):
        return self.rp.agent(user_agent).delay

    def preferred_host(self):
        """Reppy does not support Host directive."""
        logger.warning("Failure while retrieving preferred host using %(parser)s."
                       " %(parser)s does not support Host directive.",
                       {'parser': "Reppy parser"},
                       exc_info=sys.exc_info(),
                       extra={'spider': self.spider})
        return None


class RerpRobotParser:
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

    def sitemaps(self):
        return (sitemap for sitemap in self.rp.sitemaps)

    def crawl_delay(self, user_agent):
        user_agent = to_unicode(user_agent)
        return self.rp.get_crawl_delay(user_agent)

    def preferred_host(self):
        """Robotexclusionrulesparser does not support Host directive."""
        logger.warning("Failure while retrieving preferred host using %(parser)s."
                       " %(parser)s does not support Host directive.",
                       {'parser': "RobotExclusionRulesParser"},
                       exc_info=sys.exc_info(),
                       extra={'spider': self.spider})
        return None
