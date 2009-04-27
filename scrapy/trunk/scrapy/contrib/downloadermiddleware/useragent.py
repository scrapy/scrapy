"""Set User-Agent header per spider or use a default value from settings"""

from scrapy.conf import settings


class UserAgentMiddleware(object):
    """This middleware allows spiders to override the user_agent"""

    default_useragent = settings.get('USER_AGENT')

    def process_request(self, request, spider):
        ua = getattr(spider, 'user_agent', None) or self.default_useragent
        if ua:
            request.headers.setdefault('User-Agent', ua)
