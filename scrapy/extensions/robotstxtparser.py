from six.moves.urllib_robotparser import RobotFileParser

from scrapy.utils.python import to_native_str, to_unicode

class PythonRobotParser():
    def __init__(self, content):
        try:
            content = to_native_str(content)
        except UnicodeDecodeError:
            # If we found garbage or robots.txt in an encoding other than UTF-8, disregard it.
            # Switch to 'allow all' state.
            content = ''
        self.rp = RobotFileParser()
        self.rp.parse(content.splitlines()) 

    def allowed(self, url, useragent):
        try:
            useragent = to_native_str(useragent)
            url = to_native_str(url)
        except UnicodeDecodeError:
            return False
        return self.rp.can_fetch(useragent, url)

    def sitemaps(self):
        """RobotFileParser does not support Sitemaps directive."""
        def _get_empty_generator():
            return
            yield
        return _get_empty_generator()

    def crawl_delay(self, useragent):
        """RobotFileParser does not support Crawl-delay directive for Python version < 3.6 ."""
        try:
            useragent = to_native_str(useragent)
        except UnicodeDecodeError:
            return None

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
        try:
            content = to_native_str(content)
        except UnicodeDecodeError:
            # If we found garbage or robots.txt in an encoding other than UTF-8, disregard it.
            # Switch to 'allow all' state.
            content = ''
        self.rp.parse(content) 

    def allowed(self, url, useragent):
        try:
            useragent = to_unicode(useragent)
            url = to_unicode(url)
        except UnicodeDecodeError:
            return False
        return self.rp.is_allowed(useragent, url)

    def sitemaps(self):
        return (sitemap for sitemap in self.rp.sitemaps)

    def crawl_delay(self, useragent):
        try:
            useragent = to_unicode(useragent)
        except UnicodeDecodeError:
            return None
        return self.rp.get_crawl_delay(useragent)

    def preferred_host(self):
        """Robotexclusionrulesparser does not support Host directive."""
        return None
