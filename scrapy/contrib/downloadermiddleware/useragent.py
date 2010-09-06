"""Set User-Agent header per spider or use a default value from settings"""

from scrapy.conf import settings
from scrapy.utils.python import WeakKeyCache


class UserAgentMiddleware(object):
    """This middleware allows spiders to override the user_agent"""

    def __init__(self, settings=settings):
        self.cache = WeakKeyCache(self._user_agent)
        self.default_useragent = settings.get('USER_AGENT')

    def _user_agent(self, spider):
        return getattr(spider, 'user_agent', None) or self.default_useragent

    def process_request(self, request, spider):
        ua = self.cache[spider]
        if ua:
            request.headers.setdefault('User-Agent', ua)
