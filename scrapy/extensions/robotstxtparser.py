from urllib.robotparser import RobotFileParser

from scrapy.utils.python import to_native_str

class BaseRobotsTxtParser():
    def __init__(self, robotstxt_url):
        raise NotImplementedError

    def parse(self, robotstxt_body):
        """Parse content of robots.txt file."""
        raise NotImplementedError

    def allowed(self, url, useragent):
        """Return True if url is allowed for crawling, otherwise return False."""
        raise NotImplementedError

    def sitemaps(self):
        """Return a list of links of sitemaps on the website. If there is no sitemap specified in robots.txt, return None."""
        raise NotImplementedError

    def crawl_delay(self, useragent):
        """Return time specified with Crawl-delay directive. If nothing is specified, return None."""
        raise NotImplementedError

    def preferred_host(self):
        """Return preferred domain specified with Host directive. If nothing is specified, return None.""" 
        raise NotImplementedError

class PythonRobotParser(BaseRobotsTxtParser):
    def __init__(self, robotstxt_url):
        self.robotstxt_url = robotstxt_url
        self.rp = RobotFileParser(robotstxt_url) 

    def parse(self, robotstxt_body):
        self.rp.parse(to_native_str(robotstxt_body).splitlines())

    def allowed(self, url, useragent):
        return self.rp.can_fetch(to_native_str(useragent), url)

    def sitemaps(self):
        """RobotFileParser does not support Sitemaps directive."""
        return None

    def crawl_delay(self, useragent):
        return self.rp.crawl_delay(to_native_str(useragent))

    def preferred_host(self):
        """RobotFileParser does not support Host directive."""
        return None
