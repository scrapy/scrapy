from six.moves.urllib_robotparser import RobotFileParser

class PythonRobotParser():
    def __init__(self, content):
        self.rp = RobotFileParser()
        self.rp.parse(content.splitlines()) 

    def allowed(self, url, useragent):
        return self.rp.can_fetch(useragent, url)

    def sitemaps(self):
        """RobotFileParser does not support Sitemaps directive."""
        return None

    def crawl_delay(self, useragent):
        """RobotFileParser does not support Crawl-delay directive for version < Python 3.6 ."""
        if hasattr(self.rp, 'crawl_delay'):
            return self.rp.crawl_delay(useragent)
        return None

    def preferred_host(self):
        """RobotFileParser does not support Host directive."""
        return None
