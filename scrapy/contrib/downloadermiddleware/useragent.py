"""Set User-Agent header per spider or use a default value from settings"""

from scrapy.utils.python import WeakKeyCache


class UserAgentMiddleware(object):
    """This middleware allows spiders to override the user_agent"""

    def __init__(self, user_agent='Scrapy'):
        self.cache = WeakKeyCache(self._user_agent)
        self.user_agent = user_agent

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.settings['USER_AGENT'])

    def _user_agent(self, spider):
        if hasattr(spider, 'user_agent'):
            return spider.user_agent
        return self.user_agent

    def process_request(self, request, spider):
        ua = self.cache[spider]
        if ua:
            request.headers.setdefault('User-Agent', ua)
