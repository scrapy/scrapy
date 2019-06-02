from six.moves.urllib_robotparser import RobotFileParser

from scrapy.utils.python import to_native_str

class PythonRobotParser():
    def __init__(self, content):
        content = to_native_str(content)
        self.rp = RobotFileParser()
        self.rp.parse(content.splitlines()) 

    def allowed(self, url, useragent):
        return self.rp.can_fetch(useragent, url)

    def sitemaps(self):
        """RobotFileParser does not support Sitemaps directive."""
        return (sitemap for sitemap in [])

    def crawl_delay(self, useragent):
        """RobotFileParser does not support Crawl-delay directive for Python version < 3.6 ."""
        if hasattr(self.rp, 'crawl_delay'):
            delay = self.rp.crawl_delay(useragent)
            return None if delay is None else float(delay)
        return None

    def preferred_host(self):
        """RobotFileParser does not support Host directive."""
        return None

class ReppyRobotParser():
    def __init__(self, content):
        from reppy.robots import Robots
        self.rp = Robots.parse('', content)

    def allowed(self, url, useragent):
        return self.rp.allowed(url, useragent)

    def sitemaps(self):
        return (sitemap for sitemap in self.rp.sitemaps)

    def crawl_delay(self, useragent):
        return self.rp.agent(useragent).delay

    def preferred_host(self):
        """Reppy does not support Host directive."""
        return None

class RerpRobotParser():
    def __init__(self, content):
        from robotexclusionrulesparser import RobotExclusionRulesParser
        self.rp = RobotExclusionRulesParser()
        self.rp.parse(to_native_str(content)) 

    def allowed(self, url, useragent):
        return self.rp.is_allowed(useragent, url)

    def sitemaps(self):
        return (sitemap for sitemap in self.rp.sitemaps)

    def crawl_delay(self, useragent):
        return self.rp.get_crawl_delay(useragent)

    def preferred_host(self):
        """Robotexclusionrulesparser does not support Host directive."""
        return None
